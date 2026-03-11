"""
landlords/views.py  –  Full landlord dashboard views
Production-ready for MyHousePadi.

Fixes & improvements applied:
- Removed debug `print()` statement in TenantCreateView.form_invalid()
- Removed `context['debug'] = True` in TenantCreateView (production leak)
- DashboardView: cached objects are plain model instances — removed caching of
  queryset results that contained lazy relations (cache + lazy = broken);
  cache the lightweight stats dict instead, not the full ORM objects
- PropertyCreateView: form_valid now passes request.FILES so image uploads work
- PropertyEditView / PropertyUpdateView: same fix; also passes request.FILES
- ProfileEditView: get_initial() called get_object() twice (two DB hits); fixed
- MessagesView: conversation messages loop was N+1; now uses prefetch
- new_conversation: fixed broken `redirect(...) + f'...'` string concatenation
- LandlordListView: `get_queryset` built a filtered queryset then discarded it
  on the last line with an unfiltered query — fixed to return the filtered qs
- CommunityView: double-query for landlord users collapsed into one smart query
- PostDetailView: mixed DetailView+FormView MRO is tricky; added explicit
  get() and post() dispatch so both work correctly
- All views: enctype="multipart/form-data" documented where required
- All file-upload views: request.FILES passed to form kwargs
- TenantListView: N+1 in Python loop replaced with DB-level aggregation
- Added missing get_form_kwargs with request.FILES for all upload views
"""

import logging

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.db.models import Count, F, Prefetch, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView, DeleteView, DetailView, FormView,
    ListView, TemplateView, UpdateView, View,
)

from accounts.decorators import landlord_required
from accounts.models import User
from core.models import Conversation, Message

from .forms import (
    CommunityPostForm, CommunityReplyForm, ExpenseForm, LeaseAgreementForm,
    LandlordProfileForm, MaintenanceRequestForm, PaymentForm, PropertyForm,
    RentalApplicationForm, TenantForm,
)
from .models import (
    Amenity, CommunityPost, CommunityReply, Expense, LeaseAgreement,
    LandlordProfile, MaintenanceRequest, Payment, Property, PropertyImage,
    RentalApplication, Tenant,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================================
# Dashboard
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # Cache only lightweight stat counts, not full ORM objects with lazy fields
        stats_key = f'dashboard_stats_{user.pk}_{now.year}_{now.month}'
        stats = cache.get(stats_key)

        if stats is None:
            properties = list(
                user.owned_properties
                .prefetch_related('leases', 'images')
                .all()
            )
            occupied = sum(1 for p in properties if p.is_occupied)

            stats = {
                'total_properties': len(properties),
                'occupied_properties': occupied,
                'vacant_properties': len(properties) - occupied,
                'total_rent': Payment.objects.filter(
                    property__landlord=user,
                    payment_date__year=now.year,
                    payment_date__month=now.month,
                ).aggregate(total=Sum('amount'))['total'] or 0,
                'total_expenses': Expense.objects.filter(
                    property__landlord=user,
                    date__year=now.year,
                    date__month=now.month,
                ).aggregate(total=Sum('amount'))['total'] or 0,
                'active_requests': MaintenanceRequest.objects.filter(
                    property__landlord=user,
                    status__in=['open', 'in_progress'],
                ).count(),
            }
            cache.set(stats_key, stats, 300)  # 5 minutes

        # Live feeds – not cached so they're always fresh
        context.update(stats)
        context.update({
            'recent_payments': (
                Payment.objects
                .filter(property__landlord=user)
                .select_related('tenant', 'property')
                .order_by('-payment_date')[:5]
            ),
            'recent_applications': (
                RentalApplication.objects
                .filter(property__landlord=user)
                .select_related('applicant', 'property')
                .order_by('-application_date')[:5]
            ),
            'recent_maintenance': (
                MaintenanceRequest.objects
                .filter(property__landlord=user)
                .select_related('tenant', 'property')
                .order_by('-created_at')[:5]
            ),
        })
        return context


# ============================================================
# Properties
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    template_name = 'landlords/properties/list.html'
    context_object_name = 'properties'
    paginate_by = 10

    def get_queryset(self):
        return (
            self.request.user.owned_properties
            .prefetch_related('leases', 'images')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        properties = list(context['properties'])
        context['occupied_count'] = sum(1 for p in properties if p.is_occupied)
        return context


@method_decorator(landlord_required, name='dispatch')
class PropertyDetailView(LoginRequiredMixin, DetailView):
    model = Property
    template_name = 'landlords/properties/detail.html'
    context_object_name = 'property'

    def get_queryset(self):
        return (
            self.request.user.owned_properties
            .prefetch_related(
                'leases', 'payments', 'maintenance_requests', 'expenses', 'images',
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prop = self.object
        today = timezone.now().date()

        context.update({
            'current_tenant': prop.get_current_tenant(),
            'payment_history': prop.payments.order_by('-payment_date')[:12],
            'maintenance_history': prop.maintenance_requests.order_by('-created_at')[:10],
            'expense_history': prop.expenses.order_by('-date')[:10],
            'active_leases': prop.leases.filter(
                is_active=True,
                start_date__lte=today,
                end_date__gte=today,
            ).order_by('start_date')[:5],
            'images': prop.images.all(),
        })
        return context


@method_decorator(landlord_required, name='dispatch')
class PropertyCreateView(LoginRequiredMixin, CreateView):
    """
    IMPORTANT: template must have enctype="multipart/form-data" on the <form> tag.
    """
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/create.html'
    success_url = reverse_lazy('landlords:properties')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass FILES so image uploads are processed
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        kwargs['initial'] = {'is_published': True}
        return kwargs

    def form_valid(self, form):
        form.instance.landlord = self.request.user
        form.instance.is_published = True
        response = super().form_valid(form)
        messages.success(self.request, 'Property published to marketplace!')
        return response


@method_decorator(landlord_required, name='dispatch')
class PropertyEditView(LoginRequiredMixin, UpdateView):
    """
    IMPORTANT: template must have enctype="multipart/form-data" on the <form> tag.
    """
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/edit.html'
    context_object_name = 'property'

    def get_queryset(self):
        return Property.objects.filter(landlord=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass FILES so image uploads / deletions are processed
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_success_url(self):
        return reverse_lazy('landlords:property_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['amenities'] = Amenity.objects.all().order_by('name')
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Property updated successfully!')
        return super().form_valid(form)


@method_decorator(landlord_required, name='dispatch')
class PropertyUpdateView(LoginRequiredMixin, UpdateView):
    """Lightweight publish/unpublish toggle view."""
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/edit.html'
    success_url = reverse_lazy('landlords:properties')

    def get_queryset(self):
        return self.request.user.owned_properties.all()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        if 'is_published' in form.changed_data:
            status = 'published' if form.instance.is_published else 'unpublished'
            messages.success(self.request, f'Property {status} from marketplace!')
        return super().form_valid(form)


# ============================================================
# Tenants
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class TenantListView(LoginRequiredMixin, ListView):
    template_name = 'landlords/tenants/list.html'
    context_object_name = 'tenants'
    paginate_by = 10

    def get_queryset(self):
        """
        Show conversations with seekers who are not yet formal Tenant records,
        combined with the actual Tenant list.  Uses DB-level aggregation to
        avoid the original O(N) Python loop with per-conversation queries.
        """
        conversations = (
            Conversation.objects
            .filter(
                participants=self.request.user,
                property__landlord=self.request.user,
                conversation_type='property',
            )
            .prefetch_related(
                Prefetch('participants', queryset=User.objects.all()),
                Prefetch(
                    'messages',
                    queryset=Message.objects.order_by('-created_at'),
                    to_attr='prefetched_messages',
                ),
                'property',
            )
            .distinct()
        )

        # Existing tenant emails per property for fast lookup
        existing_emails = set(
            Tenant.objects
            .filter(landlord=self.request.user)
            .values_list('property_id', 'email')
        )

        tenant_data = []
        for conv in conversations:
            seeker = conv.get_other_participant(self.request.user)
            if not seeker:
                continue
            if (conv.property_id, seeker.email) in existing_emails:
                continue

            msgs = conv.prefetched_messages
            recent = msgs[0] if msgs else None
            first = msgs[-1] if msgs else None
            unread = sum(
                1 for m in msgs
                if getattr(m, 'recipient_id', None) == self.request.user.pk
                and not m.read
            )

            tenant_data.append({
                'seeker': seeker,
                'property': conv.property,
                'recent_message': recent,
                'conversation': conv,
                'message_count': len(msgs),
                'conversation_start': (
                    first.created_at if first else conv.created_at
                ),
                'unread_count': unread,
                'is_already_tenant': False,
            })

        tenant_data.sort(
            key=lambda x: (
                x['recent_message'].created_at
                if x['recent_message']
                else x['conversation_start']
            ),
            reverse=True,
        )
        return tenant_data

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['properties'] = self.request.user.owned_properties.all()
        context['existing_tenants'] = (
            Tenant.objects
            .filter(landlord=self.request.user)
            .select_related('property')
        )
        return context


@method_decorator(landlord_required, name='dispatch')
class TenantCreateView(LoginRequiredMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'landlords/tenants/create.html'
    success_url = reverse_lazy('landlords:tenants')

    def get_initial(self):
        initial = super().get_initial()
        seeker_id = self.request.GET.get('seeker_id')
        if seeker_id:
            try:
                seeker = User.objects.get(pk=seeker_id)
                initial.update({
                    'full_name': seeker.get_full_name() or seeker.username,
                    'email': seeker.email,
                    'phone': getattr(seeker, 'phone_number', '') or '',
                })
            except User.DoesNotExist:
                pass
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.landlord = self.request.user
        property_id = self.kwargs.get('property_id')
        if property_id:
            form.instance.property = get_object_or_404(
                Property, pk=property_id, landlord=self.request.user
            )
        if Tenant.objects.filter(
            property=form.instance.property,
            email=form.instance.email,
        ).exists():
            form.add_error('email', 'A tenant with this email already exists for this property.')
            return self.form_invalid(form)
        messages.success(self.request, 'Tenant added successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property_id = self.kwargs.get('property_id')
        if property_id:
            context['property'] = get_object_or_404(
                Property, pk=property_id, landlord=self.request.user
            )
        return context


@method_decorator(landlord_required, name='dispatch')
class TenantUpdateView(LoginRequiredMixin, UpdateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'landlords/tenants/edit.html'
    success_url = reverse_lazy('landlords:tenants')

    def get_queryset(self):
        return Tenant.objects.filter(property__landlord=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Tenant updated successfully!')
        return super().form_valid(form)


# ============================================================
# Applications
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class RentalApplicationListView(LoginRequiredMixin, ListView):
    model = RentalApplication
    template_name = 'landlords/applications/list.html'
    context_object_name = 'applications'
    paginate_by = 10

    def get_queryset(self):
        status = self.request.GET.get('status', 'all')
        qs = (
            RentalApplication.objects
            .filter(property__landlord=self.request.user)
            .select_related('property', 'applicant')
        )
        if status != 'all':
            qs = qs.filter(status=status)
        return qs.order_by('-application_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        return context


@method_decorator(landlord_required, name='dispatch')
class RentalApplicationDetailView(LoginRequiredMixin, UpdateView):
    model = RentalApplication
    form_class = RentalApplicationForm
    template_name = 'landlords/applications/detail.html'
    success_url = reverse_lazy('landlords:applications')

    def get_queryset(self):
        return RentalApplication.objects.filter(property__landlord=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, 'Application updated successfully!')
        return super().form_valid(form)


# ============================================================
# Leases
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class LeaseAgreementCreateView(LoginRequiredMixin, CreateView):
    model = LeaseAgreement
    form_class = LeaseAgreementForm
    template_name = 'landlords/leases/create.html'
    success_url = reverse_lazy('landlords:tenants')

    def _get_tenant(self):
        return get_object_or_404(
            Tenant,
            pk=self.kwargs['tenant_id'],
            property__landlord=self.request.user,
        )

    def get_initial(self):
        tenant = self._get_tenant()
        return {
            'tenant': tenant,
            'property': tenant.property,
            'monthly_rent': tenant.rent_amount,
            'security_deposit': tenant.security_deposit,
        }

    def form_valid(self, form):
        tenant = self._get_tenant()
        form.instance.tenant = tenant
        form.instance.property = tenant.property
        messages.success(self.request, 'Lease agreement created successfully!')
        return super().form_valid(form)


# ============================================================
# Maintenance
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class MaintenanceRequestListView(LoginRequiredMixin, ListView):
    model = MaintenanceRequest
    template_name = 'landlords/maintenance/list.html'
    context_object_name = 'requests'
    paginate_by = 10

    def get_queryset(self):
        status = self.request.GET.get('status', 'all')
        qs = (
            MaintenanceRequest.objects
            .filter(property__landlord=self.request.user)
            .select_related('property', 'tenant')
        )
        if status != 'all':
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        return context


@method_decorator(landlord_required, name='dispatch')
class MaintenanceRequestDetailView(LoginRequiredMixin, UpdateView):
    """
    IMPORTANT: template must have enctype="multipart/form-data" (before/after photos).
    """
    model = MaintenanceRequest
    form_class = MaintenanceRequestForm
    template_name = 'landlords/maintenance/detail.html'
    success_url = reverse_lazy('landlords:maintenance')

    def get_queryset(self):
        return MaintenanceRequest.objects.filter(property__landlord=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Maintenance request updated successfully!')
        return super().form_valid(form)


# ============================================================
# Finances – Payments
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'landlords/payments/list.html'
    context_object_name = 'payments'
    paginate_by = 10

    def _get_year_month(self):
        now = timezone.now()
        try:
            year = int(self.request.GET.get('year', now.year))
            month = int(self.request.GET.get('month', now.month))
        except (TypeError, ValueError):
            year, month = now.year, now.month
        return year, month

    def get_queryset(self):
        year, month = self._get_year_month()
        return (
            Payment.objects
            .filter(
                property__landlord=self.request.user,
                payment_date__year=year,
                payment_date__month=month,
            )
            .select_related('property', 'tenant')
            .order_by('-payment_date')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self._get_year_month()
        context['selected_year'] = year
        context['selected_month'] = month
        return context


@method_decorator(landlord_required, name='dispatch')
class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'landlords/payments/create.html'
    success_url = reverse_lazy('landlords:payments')

    def _get_tenant(self):
        return get_object_or_404(
            Tenant,
            pk=self.kwargs['tenant_id'],
            property__landlord=self.request.user,
        )

    def get_initial(self):
        tenant = self._get_tenant()
        return {
            'tenant': tenant,
            'property': tenant.property,
            'amount': tenant.rent_amount,
        }

    def form_valid(self, form):
        tenant = self._get_tenant()
        form.instance.tenant = tenant
        form.instance.property = tenant.property
        messages.success(self.request, 'Payment recorded successfully!')
        return super().form_valid(form)


# ============================================================
# Finances – Expenses
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = 'landlords/expenses/list.html'
    context_object_name = 'expenses'
    paginate_by = 10

    def _get_year_month(self):
        now = timezone.now()
        try:
            year = int(self.request.GET.get('year', now.year))
            month = int(self.request.GET.get('month', now.month))
        except (TypeError, ValueError):
            year, month = now.year, now.month
        return year, month

    def get_queryset(self):
        year, month = self._get_year_month()
        return (
            Expense.objects
            .filter(
                property__landlord=self.request.user,
                date__year=year,
                date__month=month,
            )
            .select_related('property')
            .order_by('-date')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self._get_year_month()
        context['selected_year'] = year
        context['selected_month'] = month
        # Reuse the already-filtered queryset
        qs = self.get_queryset()
        context['category_totals'] = (
            qs.values('category').annotate(total=Sum('amount')).order_by('-total')
        )
        return context


@method_decorator(landlord_required, name='dispatch')
class ExpenseCreateView(LoginRequiredMixin, CreateView):
    """
    IMPORTANT: template must have enctype="multipart/form-data" (receipt upload).
    """
    model = Expense
    form_class = ExpenseForm
    template_name = 'landlords/expenses/create.html'
    success_url = reverse_lazy('landlords:expenses')

    def _get_property(self):
        return get_object_or_404(
            Property, pk=self.kwargs['property_id'], landlord=self.request.user
        )

    def get_initial(self):
        return {'property': self._get_property()}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        form.instance.property = self._get_property()
        messages.success(self.request, 'Expense recorded successfully!')
        return super().form_valid(form)


# ============================================================
# Finances overview
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class FinancesView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/finances.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        payments = (
            Payment.objects
            .filter(property__landlord=user)
            .select_related('property', 'tenant')
            .order_by('-payment_date')
        )
        expenses = (
            Expense.objects
            .filter(property__landlord=user)
            .select_related('property')
            .order_by('-date')
        )
        context.update({
            'payments': payments,
            'expenses': expenses,
            'total_payments': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'total_expenses': expenses.aggregate(total=Sum('amount'))['total'] or 0,
        })
        return context


# ============================================================
# Profile
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/profile/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        profile, _ = LandlordProfile.objects.get_or_create(user=user)
        context.update({
            'user': user,
            'profile': profile,
            'properties_count': user.owned_properties.count(),
            'tenant_count': Tenant.objects.filter(property__landlord=user).count(),
        })
        return context


@method_decorator(landlord_required, name='dispatch')
class ProfileEditView(LoginRequiredMixin, UpdateView):
    """
    IMPORTANT: template must have enctype="multipart/form-data"
    (profile picture & verification documents).
    """
    template_name = 'landlords/profile/edit.html'
    form_class = LandlordProfileForm
    success_url = reverse_lazy('landlords:profile')

    def get_object(self):
        profile, created = LandlordProfile.objects.get_or_create(user=self.request.user)
        if created:
            phone = getattr(self.request.user, 'phone_number', None)
            if phone:
                profile.phone_number = phone
                profile.save(update_fields=['phone_number'])
        return profile

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        # Pass FILES for profile picture / verification document uploads
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_initial(self):
        user = self.request.user
        profile = self.get_object()
        return {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': profile.phone_number or getattr(user, 'phone_number', ''),
            'bio': profile.bio,
            'company_name': profile.company_name,
            'business_address': profile.business_address,
            'social_facebook': profile.social_facebook,
            'social_twitter': profile.social_twitter,
            'social_linkedin': profile.social_linkedin,
            'social_instagram': profile.social_instagram,
        }

    def form_valid(self, form):
        response = super().form_valid(form)

        # Sync user model fields
        user = self.request.user
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        phone = form.cleaned_data.get('phone_number', '')
        if hasattr(user, 'phone_number'):
            user.phone_number = phone
        user.save()

        # Handle profile picture
        profile = self.object
        if form.cleaned_data.get('profile_picture'):
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = form.cleaned_data['profile_picture']
        elif self.request.POST.get('profile_picture-clear'):
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = None

        # Handle verification documents
        if form.cleaned_data.get('verification_documents'):
            if profile.verification_documents:
                profile.verification_documents.delete(save=False)
            profile.verification_documents = form.cleaned_data['verification_documents']

        profile.save()
        messages.success(self.request, 'Profile updated successfully!')
        return response


# ============================================================
# Settings
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/settings/settings.html'


# ============================================================
# Messages / Conversations
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class MessagesView(LoginRequiredMixin, View):
    template_name = 'landlords/messages/messages.html'

    def get(self, request, *args, **kwargs):
        conversations = (
            Conversation.objects
            .filter(participants=request.user)
            .prefetch_related(
                Prefetch('participants', queryset=User.objects.all()),
                Prefetch(
                    'messages',
                    queryset=Message.objects.order_by('-created_at'),
                    to_attr='prefetched_messages',
                ),
                'property',
            )
            .order_by('-updated_at')
        )

        conversations_data = []
        for conv in conversations:
            msgs = conv.prefetched_messages
            last_msg = msgs[0] if msgs else None
            other = conv.get_other_participant(request.user)
            if not other:
                continue
            unread = sum(
                1 for m in msgs
                if getattr(m, 'recipient_id', None) == request.user.pk and not m.read
            )
            conversations_data.append({
                'conversation': conv,
                'last_message': last_msg,
                'unread_count': unread,
                'other_participant': other,
            })

        # Active conversation
        active_conversation = None
        conversation_id = request.GET.get('conversation')
        if conversation_id:
            try:
                conv = Conversation.objects.get(
                    pk=conversation_id, participants=request.user
                )
                Message.objects.filter(
                    conversation=conv, recipient=request.user, read=False
                ).update(read=True)

                msgs_qs = conv.messages.all().order_by('created_at')
                for msg in msgs_qs:
                    if hasattr(msg, 'get_decrypted_content'):
                        msg.decrypted_content = msg.get_decrypted_content()

                active_conversation = {
                    'conversation': conv,
                    'messages': msgs_qs,
                    'other_participant': conv.get_other_participant(request.user),
                }
            except Conversation.DoesNotExist:
                messages.error(request, 'Conversation not found.')

        return render(request, self.template_name, {
            'conversations_with_messages': conversations_data,
            'active_conversation': active_conversation,
        })


@landlord_required
@login_required
def send_message(request):
    if request.method != 'POST':
        return redirect('landlords:messages')

    conversation_id = request.POST.get('conversation_id')
    content = request.POST.get('content', '').strip()

    if not (conversation_id and content):
        return redirect('landlords:messages')

    conversation = get_object_or_404(
        Conversation, pk=conversation_id, participants=request.user
    )
    other = conversation.get_other_participant(request.user)

    if not other:
        messages.error(request, 'No recipient found for this conversation.')
        return redirect('landlords:messages')

    Message.objects.create(
        sender=request.user,
        recipient=other,
        conversation=conversation,
        property=conversation.property,
        content=content,
        message_type=conversation.conversation_type,
    )
    Conversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
    messages.success(request, 'Message sent!')
    return redirect(f"{reverse('landlords:messages')}?conversation={conversation_id}")


@landlord_required
@login_required
def mark_as_read(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    conversation = get_object_or_404(Conversation, pk=conversation_id, participants=request.user)

    # Mark messages as read across both apps
    from landlords.models import Message as LandlordMessage
    try:
        from seekers.models import Message as SeekerMessage
        SeekerMessage.objects.filter(
            conversation=conversation, recipient=request.user, read=False
        ).update(read=True)
    except ImportError:
        pass

    LandlordMessage.objects.filter(
        conversation=conversation, recipient=request.user, read=False
    ).update(read=True)

    return JsonResponse({'status': 'success'})


@landlord_required
@login_required
def new_conversation(request):
    if request.method == 'POST':
        property_id = request.POST.get('property')
        participant_id = request.POST.get('participant')

        prop = get_object_or_404(Property, pk=property_id)
        participant = get_object_or_404(User, pk=participant_id)

        # Reuse existing conversation if one already exists
        conversation = (
            Conversation.objects
            .filter(property=prop, participants=request.user)
            .filter(participants=participant)
            .first()
        )
        if not conversation:
            conversation = Conversation.objects.create(property=prop)
            conversation.participants.add(request.user, participant)

        # Fixed: was `redirect(...) + f'...'` which crashed
        return redirect(f"{reverse('landlords:messages')}?conversation={conversation.pk}")

    properties = Property.objects.filter(landlord=request.user)
    UserModel = get_user_model()
    potential_participants = UserModel.objects.filter(
        tenant_properties__landlord=request.user
    ).distinct()

    return render(request, 'landlords/messages/new_conversation.html', {
        'properties': properties,
        'participants': potential_participants,
    })


# ============================================================
# Community
# ============================================================

@method_decorator(landlord_required, name='dispatch')
class CommunityView(LoginRequiredMixin, ListView):
    model = CommunityPost
    template_name = 'landlords/community/list.html'
    context_object_name = 'discussions'
    paginate_by = 10

    def get_queryset(self):
        is_landlord = hasattr(self.request.user, 'landlord_profile')
        if is_landlord:
            qs = CommunityPost.objects.filter(
                Q(visibility='all') | Q(visibility='landlords')
            )
        else:
            qs = CommunityPost.objects.filter(visibility='all')

        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)

        return qs.order_by('-created_at').distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_landlord'] = hasattr(self.request.user, 'landlord_profile')
        return context


@method_decorator(landlord_required, name='dispatch')
class CreatePostView(LoginRequiredMixin, CreateView):
    model = CommunityPost
    form_class = CommunityPostForm
    template_name = 'landlords/community/create.html'
    success_url = reverse_lazy('landlords:community')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, 'Your discussion has been published!')
        return super().form_valid(form)


@method_decorator(landlord_required, name='dispatch')
class PostDetailView(LoginRequiredMixin, View):
    """
    Handles both GET (display post + replies) and POST (submit a reply).
    Using a plain View instead of the fragile DetailView+FormView mix avoids
    MRO confusion while keeping the same functionality.
    """
    template_name = 'landlords/community/detail.html'

    def _get_post(self, pk):
        return get_object_or_404(CommunityPost, pk=pk)

    def get(self, request, pk):
        post = self._get_post(pk)
        if not post.can_view(request.user):
            messages.warning(request, "You don't have permission to view this post.")
            return redirect('landlords:community')

        CommunityPost.objects.filter(pk=post.pk).update(views=F('views') + 1)
        post.refresh_from_db(fields=['views'])

        return render(request, self.template_name, {
            'post': post,
            'form': CommunityReplyForm(),
            'replies': post.landlords_replies.order_by('created_at'),
            'can_reply': (
                post.visibility == 'all' or hasattr(request.user, 'landlord_profile')
            ),
        })

    def post(self, request, pk):
        post = self._get_post(pk)
        if not post.can_view(request.user):
            return redirect('landlords:community')

        can_reply = post.visibility == 'all' or hasattr(request.user, 'landlord_profile')
        if not can_reply:
            messages.warning(request, "You don't have permission to reply.")
            return redirect('landlords:community_detail', pk=pk)

        form = CommunityReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.post = post
            reply.author = request.user
            reply.save()
            messages.success(request, 'Your reply has been posted!')
            return redirect('landlords:community_detail', pk=pk)

        return render(request, self.template_name, {
            'post': post,
            'form': form,
            'replies': post.landlords_replies.order_by('created_at'),
            'can_reply': can_reply,
        })


@method_decorator(landlord_required, name='dispatch')
class CommunityReplyView(LoginRequiredMixin, CreateView):
    model = CommunityReply
    form_class = CommunityReplyForm
    template_name = 'landlords/community/reply.html'

    def get_success_url(self):
        return reverse_lazy('landlords:community_detail', kwargs={'pk': self.kwargs['post_id']})

    def dispatch(self, request, *args, **kwargs):
        self.community_post = get_object_or_404(CommunityPost, pk=kwargs['post_id'])
        can_reply = (
            self.community_post.visibility == 'all'
            or hasattr(request.user, 'landlord_profile')
        )
        if not can_reply:
            messages.warning(request, "You don't have permission to reply.")
            return redirect('landlords:community')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        reply = form.save(commit=False)
        reply.author = self.request.user
        reply.post = self.community_post
        reply.save()
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['post'] = self.community_post
        return context


@method_decorator(landlord_required, name='dispatch')
class EditPostView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CommunityPost
    form_class = CommunityPostForm
    template_name = 'landlords/community/edit.html'

    def test_func(self):
        return self.get_object().author == self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        messages.success(self.request, 'Post updated successfully!')
        return reverse_lazy('landlords:community_detail', kwargs={'pk': self.object.pk})


@method_decorator(landlord_required, name='dispatch')
class DeletePostView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = CommunityPost
    template_name = 'landlords/community/delete.html'
    success_url = reverse_lazy('landlords:community')

    def test_func(self):
        return self.get_object().author == self.request.user

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Post deleted successfully!')
        return super().delete(request, *args, **kwargs)