from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, View, ListView, DetailView, CreateView, UpdateView, FormView, DeleteView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum, Count, F
from accounts.decorators import landlord_required
from django.utils.decorators import method_decorator
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Prefetch, Subquery, Exists, OuterRef
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from accounts.models import User
from .models import (
    Amenity, LandlordProfile, Property, PropertyImage, Tenant, RentalApplication,
    LeaseAgreement, MaintenanceRequest, Payment, Expense, Conversation, Message, CommunityPost, CommunityReply
)
from .forms import (
    LandlordProfileForm, PropertyForm, TenantForm, RentalApplicationForm,
    LeaseAgreementForm, MaintenanceRequestForm, PaymentForm, ExpenseForm, CommunityPostForm, CommunityReplyForm
)

@method_decorator(landlord_required, name='dispatch')
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/dashboard.html'
    
    def get_properties_cache_key(self):
        return f'user_{self.request.user.id}_properties'
    
    def get_occupied_count(self, properties):
        return sum(1 for p in properties if p.is_occupied)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Cache properties for 5 minutes
        cache_key = self.get_properties_cache_key()
        properties = cache.get(cache_key)
        
        if not properties:
            properties = list(user.owned_properties.prefetch_related(
                'leases',
                'payments',
                'maintenance_requests'
            ).all())
            cache.set(cache_key, properties, 300)
        
        occupied_count = self.get_occupied_count(properties)
        
        context.update({
            'properties': properties,
            'total_properties': len(properties),
            'occupied_properties': occupied_count,
            'vacant_properties': len(properties) - occupied_count,
            'total_rent': Payment.objects.filter(
                property__landlord=user,
                payment_date__month=timezone.now().month
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'total_expenses': Expense.objects.filter(
                property__landlord=user,
                date__month=timezone.now().month
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'active_requests': MaintenanceRequest.objects.filter(
                property__landlord=user,
                status__in=['open', 'in_progress']
            ).count(),
            'recent_payments': Payment.objects.filter(
                property__landlord=user
            ).select_related('tenant', 'property').order_by('-payment_date')[:5],
            'recent_applications': RentalApplication.objects.filter(
                property__landlord=user
            ).select_related('applicant', 'property').order_by('-application_date')[:5],
            'recent_maintenance': MaintenanceRequest.objects.filter(
                property__landlord=user
            ).select_related('tenant', 'property').order_by('-created_at')[:5],
        })
        return context

@method_decorator(landlord_required, name='dispatch')
class PropertyListView(LoginRequiredMixin, ListView):
    model = Property
    template_name = 'landlords/properties/list.html'
    context_object_name = 'properties'
    paginate_by = 10
    
    def get_queryset(self):
        return self.request.user.owned_properties.prefetch_related(
            'leases'
        ).order_by('-created_at')
    
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
        return self.request.user.owned_properties.prefetch_related(
            'leases',
            'payments',
            'maintenance_requests',
            'expenses',
            'images'
    )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        property = self.object
        
        context.update({
            'current_tenant': property.get_current_tenant(),
            'payment_history': property.payments.order_by('-payment_date')[:12],
            'maintenance_history': property.maintenance_requests.order_by('-created_at')[:10],
            'expense_history': property.expenses.order_by('-date')[:10],
            'active_leases': property.leases.filter(
                is_active=True,
                start_date__lte=timezone.now().date(),
                end_date__gte=timezone.now().date()
            ).order_by('start_date')[:5],
            'images': property.images.all() 
        })
        return context

@method_decorator(landlord_required, name='dispatch')
class PropertyCreateView(LoginRequiredMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/create.html'
    success_url = reverse_lazy('landlords:properties')
    
    def form_valid(self, form):
        form.instance.landlord = self.request.user
        form.instance.is_published = True
        response = super().form_valid(form)
        
         
        messages.success(self.request, 'Property published to marketplace!')
        return response
    
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {'is_published': True}  # Default to published
        return kwargs

@method_decorator(landlord_required, name='dispatch')
class PropertyEditView(LoginRequiredMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/edit.html'
    context_object_name = 'property'
    
    def get_success_url(self):
        return reverse_lazy('landlords:property_detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['amenities'] = Amenity.objects.all().order_by('name')
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Property updated successfully!')
        return super().form_valid(form)
    
    def get_queryset(self):
        return super().get_queryset().filter(landlord=self.request.user)
    
@method_decorator(landlord_required, name='dispatch')
class PropertyUpdateView(LoginRequiredMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'landlords/properties/edit.html'
    success_url = reverse_lazy('landlords:properties')
    
    def get_queryset(self):
        return self.request.user.owned_properties.all()
    
    def form_valid(self, form):
        if 'is_published' in form.changed_data:
            status = "published" if form.instance.is_published else "unpublished"
            messages.success(self.request, f'Property {status} from marketplace!')
        return super().form_valid(form)

# landlords/views.py
@method_decorator(landlord_required, name='dispatch')
class TenantListView(LoginRequiredMixin, ListView):
    template_name = 'landlords/tenants/list.html'
    context_object_name = 'tenants'
    paginate_by = 10
    
    def get_queryset(self):
        # Get conversations where landlord is participant
        conversations = Conversation.objects.filter(
            participants=self.request.user,
            property__landlord=self.request.user,
            conversation_type='property'
        ).prefetch_related(
            Prefetch('participants', queryset=User.objects.all()),
            'property',
            Prefetch('messages', queryset=Message.objects.order_by('-created_at'))
        ).distinct()
        
        tenant_data = []
        for conversation in conversations:
            seeker = conversation.get_other_participant(self.request.user)
            if seeker:
                # Check if this seeker is already a tenant for this specific property
                is_already_tenant = Tenant.objects.filter(
                    property=conversation.property,
                    email=seeker.email  # Check by email since no user relation
                ).exists()
                
                if not is_already_tenant:
                    recent_message = conversation.messages.first()
                    message_count = conversation.messages.count()
                    first_message = conversation.messages.last()
                    
                    tenant_data.append({
                        'seeker': seeker,
                        'property': conversation.property,
                        'recent_message': recent_message,
                        'conversation': conversation,
                        'message_count': message_count,
                        'conversation_start': first_message.created_at if first_message else conversation.created_at,
                        'unread_count': conversation.messages.filter(
                            recipient=self.request.user,
                            read=False
                        ).count(),
                        'is_already_tenant': is_already_tenant
                    })
        
        return sorted(tenant_data, 
                     key=lambda x: x['recent_message'].created_at if x['recent_message'] else x['conversation_start'], 
                     reverse=True)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['properties'] = self.request.user.owned_properties.all()
        context['existing_tenants'] = Tenant.objects.filter(
            landlord=self.request.user
        ).select_related('property')
        return context
    
# landlords/views.py
@method_decorator(landlord_required, name='dispatch')
class TenantCreateView(LoginRequiredMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'landlords/tenants/create.html'
    
    def get_success_url(self):
        return reverse_lazy('landlords:tenants')
    
    def get_initial(self):
        initial = super().get_initial()
        seeker_id = self.request.GET.get('seeker_id')
        
        # Pre-fill with seeker data if provided
        if seeker_id:
            try:
                seeker = User.objects.get(id=seeker_id)
                initial.update({
                    'full_name': seeker.get_full_name() or seeker.username,
                    'email': seeker.email,
                    'phone': seeker.phone_number or '',
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
        
        # Set property from URL
        property_id = self.kwargs.get('property_id')
        if property_id:
            form.instance.property = get_object_or_404(
                Property, 
                pk=property_id,
                landlord=self.request.user
            )
        
        # Check for existing tenant with same email and property
        if Tenant.objects.filter(
            property=form.instance.property,
            email=form.instance.email
        ).exists():
            form.add_error('email', 'A tenant with this email already exists for this property!')
            return self.form_invalid(form)
        
        messages.success(self.request, 'Tenant added successfully!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        print("Form errors:", form.errors)  # Debug output
        return super().form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add property to context for template display
        property_id = self.kwargs.get('property_id')
        if property_id:
            context['property'] = get_object_or_404(
                Property, 
                pk=property_id,
                landlord=self.request.user
            )
        # Add debug info
        context['debug'] = True  # Set to False in production
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

@method_decorator(landlord_required, name='dispatch')
class RentalApplicationListView(LoginRequiredMixin, ListView):
    model = RentalApplication
    template_name = 'landlords/applications/list.html'
    context_object_name = 'applications'
    paginate_by = 10
    
    def get_queryset(self):
        status = self.request.GET.get('status', 'all')
        queryset = RentalApplication.objects.filter(
            property__landlord=self.request.user
        ).select_related('property', 'applicant')
        
        if status != 'all':
            queryset = queryset.filter(status=status)
            
        return queryset.order_by('-application_date')
    
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

@method_decorator(landlord_required, name='dispatch')
class LeaseAgreementCreateView(LoginRequiredMixin, CreateView):
    model = LeaseAgreement
    form_class = LeaseAgreementForm
    template_name = 'landlords/leases/create.html'
    success_url = reverse_lazy('landlords:tenants')
    
    def get_initial(self):
        tenant = get_object_or_404(
            Tenant, 
            pk=self.kwargs.get('tenant_id'),
            property__landlord=self.request.user
        )
        return {
            'tenant': tenant,
            'property': tenant.property,
            'monthly_rent': tenant.rent_amount,
            'security_deposit': tenant.security_deposit,
        }
    
    def form_valid(self, form):
        tenant = get_object_or_404(
            Tenant, 
            pk=self.kwargs.get('tenant_id'),
            property__landlord=self.request.user
        )
        form.instance.tenant = tenant
        form.instance.property = tenant.property
        messages.success(self.request, 'Lease agreement created successfully!')
        return super().form_valid(form)

@method_decorator(landlord_required, name='dispatch')
class MaintenanceRequestListView(LoginRequiredMixin, ListView):
    model = MaintenanceRequest
    template_name = 'landlords/maintenance/list.html'
    context_object_name = 'requests'
    paginate_by = 10
    
    def get_queryset(self):
        status = self.request.GET.get('status', 'all')
        queryset = MaintenanceRequest.objects.filter(
            property__landlord=self.request.user
        ).select_related('property', 'tenant')
        
        if status != 'all':
            queryset = queryset.filter(status=status)
            
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        return context

@method_decorator(landlord_required, name='dispatch')
class MaintenanceRequestDetailView(LoginRequiredMixin, UpdateView):
    model = MaintenanceRequest
    form_class = MaintenanceRequestForm
    template_name = 'landlords/maintenance/detail.html'
    success_url = reverse_lazy('landlords:maintenance')
    
    def get_queryset(self):
        return MaintenanceRequest.objects.filter(property__landlord=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, 'Maintenance request updated successfully!')
        return super().form_valid(form)

@method_decorator(landlord_required, name='dispatch')
class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'landlords/payments/list.html'
    context_object_name = 'payments'
    paginate_by = 10
    
    def get_queryset(self):
        year = self.request.GET.get('year', timezone.now().year)
        month = self.request.GET.get('month', timezone.now().month)
        
        return Payment.objects.filter(
            property__landlord=self.request.user,
            payment_date__year=year,
            payment_date__month=month
        ).select_related('property', 'tenant').order_by('-payment_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_year'] = int(self.request.GET.get('year', timezone.now().year))
        context['selected_month'] = int(self.request.GET.get('month', timezone.now().month))
        return context

@method_decorator(landlord_required, name='dispatch')
class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'landlords/payments/create.html'
    success_url = reverse_lazy('landlords:payments')
    
    def get_initial(self):
        tenant = get_object_or_404(
            Tenant, 
            pk=self.kwargs.get('tenant_id'),
            property__landlord=self.request.user
        )
        return {
            'tenant': tenant,
            'property': tenant.property,
            'amount': tenant.rent_amount,
        }
    
    def form_valid(self, form):
        tenant = get_object_or_404(
            Tenant, 
            pk=self.kwargs.get('tenant_id'),
            property__landlord=self.request.user
        )
        form.instance.tenant = tenant
        form.instance.property = tenant.property
        messages.success(self.request, 'Payment recorded successfully!')
        return super().form_valid(form)

@method_decorator(landlord_required, name='dispatch')
class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = 'landlords/expenses/list.html'
    context_object_name = 'expenses'
    paginate_by = 10
    
    def get_queryset(self):
        year = self.request.GET.get('year', timezone.now().year)
        month = self.request.GET.get('month', timezone.now().month)
        
        return Expense.objects.filter(
            property__landlord=self.request.user,
            date__year=year,
            date__month=month
        ).select_related('property').order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_year'] = int(self.request.GET.get('year', timezone.now().year))
        context['selected_month'] = int(self.request.GET.get('month', timezone.now().month))
        
        expenses = self.get_queryset()
        context['category_totals'] = expenses.values('category').annotate(
            total=Sum('amount')
        ).order_by('-total')
        
        return context

@method_decorator(landlord_required, name='dispatch')
class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'landlords/expenses/create.html'
    success_url = reverse_lazy('landlords:expenses')
    
    def get_initial(self):
        property = get_object_or_404(
            Property, 
            pk=self.kwargs.get('property_id'),
            landlord=self.request.user
        )
        return {
            'property': property,
        }
    
    def form_valid(self, form):
        property = get_object_or_404(
            Property, 
            pk=self.kwargs.get('property_id'),
            landlord=self.request.user
        )
        form.instance.property = property
        messages.success(self.request, 'Expense recorded successfully!')
        return super().form_valid(form)

@method_decorator(landlord_required, name='dispatch')
class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/profile/profile.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Safely get the profile (returns None if it doesn't exist)
        profile = getattr(user, 'landlord_profile', None)
        
        # If profile doesn't exist, you might want to create it or redirect
        if not profile:
            # Option 1: Create the profile automatically
            profile, created = LandlordProfile.objects.get_or_create(user=user)
            
            # Option 2: Redirect to profile creation page
            # return redirect('landlords:create_profile')
        
        properties_count = user.owned_properties.count() if hasattr(user, 'owned_properties') else 0
        tenant_count = Tenant.objects.filter(property__landlord=user).count() if hasattr(user, 'owned_properties') else 0
        
        context.update({
            'user': user,
            'profile': profile,
            'properties_count': properties_count,
            'tenant_count': tenant_count,
        })
        return context

@method_decorator(landlord_required, name='dispatch')
class ProfileEditView(LoginRequiredMixin, UpdateView):
    template_name = 'landlords/profile/edit.html'
    form_class = LandlordProfileForm
    success_url = reverse_lazy('landlords:profile')
    
    def get_object(self):
        profile, created = LandlordProfile.objects.get_or_create(user=self.request.user)
        if created:
            profile.phone_number = self.request.user.phone_number
            profile.save()
        return profile
    
    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        profile = self.get_object()
        initial.update({
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_number': profile.phone_number or user.phone_number,
            'bio': profile.bio,
            'company_name': profile.company_name,
            'business_address': profile.business_address,
            'social_facebook': profile.social_facebook,
            'social_twitter': profile.social_twitter,
            'social_linkedin': profile.social_linkedin,
            'social_instagram': profile.social_instagram,
        })
        return initial
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # First save the form to handle the profile instance
        response = super().form_valid(form)
        
        # Update user model
        user = self.request.user
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        user.phone_number = form.cleaned_data.get('phone_number', '')
        user.save()
        
        # Get the updated profile
        profile = self.object
        
        # Update all profile fields
        profile_fields = [
            'phone_number', 'bio', 'company_name', 'business_address',
            'social_facebook', 'social_twitter', 'social_linkedin', 'social_instagram'
        ]
        for field in profile_fields:
            setattr(profile, field, form.cleaned_data.get(field))
        
        # Handle profile picture
        if form.cleaned_data.get('profile_picture'):
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = form.cleaned_data['profile_picture']
        elif form.cleaned_data.get('profile_picture-clear'):
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

@method_decorator(landlord_required, name='dispatch')
class FinancesView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/finances.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        payments = Payment.objects.filter(property__landlord=user).order_by('-payment_date')
        expenses = Expense.objects.filter(property__landlord=user).order_by('-date')
        context.update({
            'payments': payments,
            'expenses': expenses,
            'total_payments': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'total_expenses': expenses.aggregate(total=Sum('amount'))['total'] or 0,
        })
        return context

@method_decorator(landlord_required, name='dispatch')
class MessagesView(LoginRequiredMixin, View):
    template_name = 'landlords/messages/messages.html'
    
    def get(self, request, *args, **kwargs):
        # Get conversations where landlord is a participant
        conversations = Conversation.objects.filter(
            participants=request.user
        ).prefetch_related('participants', 'property', 'messages')
        
        # Prepare conversations data
        conversations_with_data = []
        for conversation in conversations:
            last_message = conversation.messages.order_by('-created_at').first()
            other_participant = conversation.get_other_participant(request.user)
            
            if last_message and other_participant:
                unread_count = conversation.messages.filter(
                    recipient=request.user,
                    read=False
                ).count()
                
                conversations_with_data.append({
                    'conversation': conversation,
                    'last_message': last_message,
                    'unread_count': unread_count,
                    'other_participant': other_participant,
                })
        
        # Sort by last message time
        conversations_with_data.sort(
            key=lambda x: x['last_message'].created_at if x['last_message'] else x['conversation'].created_at, 
            reverse=True
        )
        
        # Handle active conversation
        active_conversation = None
        conversation_id = request.GET.get('conversation')
        if conversation_id:
            try:
                conversation = Conversation.objects.get(
                    id=conversation_id, 
                    participants=request.user
                )
                
                # Mark messages as read
                Message.objects.filter(
                    conversation=conversation,
                    recipient=request.user,
                    read=False
                ).update(read=True)
                
                # Get messages with decrypted content
                messages_list = conversation.messages.all().order_by('created_at')
                for message in messages_list:
                    message.decrypted_content = message.get_decrypted_content()
                
                active_conversation = {
                    'conversation': conversation,
                    'messages': messages_list,
                    'other_participant': conversation.get_other_participant(request.user),
                }
                
            except Conversation.DoesNotExist:
                messages.error(request, 'Conversation not found')
        
        context = {
            'conversations_with_messages': conversations_with_data,
            'active_conversation': active_conversation,
        }
        
        return render(request, self.template_name, context)


@method_decorator(landlord_required, name='dispatch')
class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'landlords/settings/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

@landlord_required
@login_required
def send_message(request):
    if request.method == 'POST':
        conversation_id = request.POST.get('conversation_id')
        content = request.POST.get('content', '').strip()

        if conversation_id and content:
            conversation = get_object_or_404(
                Conversation, 
                id=conversation_id, 
                participants=request.user
            )
            
            other_participant = conversation.get_other_participant(request.user)
            
            if not other_participant:
                messages.error(request, 'No recipient found for this conversation.')
                return redirect('landlords:messages')

            # Create the message
            Message.objects.create(
                sender=request.user,
                recipient=other_participant,
                conversation=conversation,
                property=conversation.property,
                content=content,
                message_type=conversation.conversation_type
            )
            
            # Update conversation timestamp
            conversation.updated_at = timezone.now()
            conversation.save()
            
            messages.success(request, 'Message sent!')

        return redirect(f"{reverse('landlords:messages')}?conversation={conversation_id}")
    return redirect('landlords:messages')


@landlord_required
@login_required
def mark_as_read(request, conversation_id):
    if request.method == 'POST':
        conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
        
        # Mark messages as read from both models
        from landlords.models import Message as LandlordMessage
        from seekers.models import Message as SeekerMessage
        
        # Mark landlord messages as read
        LandlordMessage.objects.filter(
            conversation=conversation,
            recipient=request.user,
            read=False
        ).update(read=True)
        
        # Mark seeker messages as read
        SeekerMessage.objects.filter(
            conversation=conversation,
            recipient=request.user,
            read=False
        ).update(read=True)
        
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

@landlord_required
@login_required
def new_conversation(request):
    User = get_user_model()  # Get the custom user model
    
    if request.method == 'POST':
        # Get the selected property and participant from the form
        property_id = request.POST.get('property')
        participant_id = request.POST.get('participant')
        
        property = get_object_or_404(Property, id=property_id)
        participant = get_object_or_404(User, id=participant_id)
        
        # Check if conversation already exists
        conversation = Conversation.objects.filter(
            property=property,
            participants=request.user
        ).filter(participants=participant).first()
        
        if not conversation:
            conversation = Conversation.objects.create(property=property)
            conversation.participants.add(request.user, participant)
        
        return redirect('landlords:messages') + f'?conversation={conversation.id}'
    
    # For GET requests, show a form to select property and participant
    properties = Property.objects.filter(landlord=request.user)
    
    # Get the actual User model class
    UserModel = get_user_model()
    
    # Filter potential participants - adjust this logic as needed
    potential_participants = UserModel.objects.filter(
        # Example: tenants of the landlord's properties
        tenant_properties__landlord=request.user
    ).distinct()

    return render(request, 'landlords/messages/new_conversation.html', {
        'properties': properties,
        'participants': potential_participants
    })

@method_decorator(landlord_required, name='dispatch')
class CommunityView(LoginRequiredMixin, ListView):
    model = CommunityPost
    template_name = 'landlords/community/list.html'
    context_object_name = 'discussions'
    paginate_by = 10
    
    def get_queryset(self):
        queryset = CommunityPost.objects.filter(
            Q(visibility='all') | 
            Q(visibility='landlords', author__landlord_profile__isnull=False)
        ).order_by('-created_at')
        
        # If user is a landlord, show all their own posts plus public ones
        if hasattr(self.request.user, 'landlord_profile'):
            queryset = CommunityPost.objects.filter(
                Q(visibility='all') | 
                Q(visibility='landlords') |
                Q(author=self.request.user)
            ).order_by('-created_at')
        
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        return queryset.distinct()

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
class PostDetailView(LoginRequiredMixin, DetailView, FormView):
    template_name = 'landlords/community/detail.html'
    form_class = CommunityReplyForm
    model = CommunityPost
    context_object_name = 'post'
    
    def get_success_url(self):
        return reverse_lazy('landlords:community_detail', kwargs={'pk': self.kwargs['pk']})
    
    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Check if user can view this post
        if not self.object.can_view(request.user):
            messages.warning(request, "You don't have permission to view this post.")
            return redirect('landlords:community')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        
        # Increment view count - only on GET requests (not form submissions)
        if self.request.method == 'GET':
            CommunityPost.objects.filter(pk=post.pk).update(views=F('views') + 1)
            post.refresh_from_db()
        
        context.update({
            'replies': post.landlords_replies.all().order_by('created_at'),  # Changed to landlords_replies
            'can_reply': post.visibility == 'all' or hasattr(self.request.user, 'landlord_profile'),
        })
        return context
    
    def form_valid(self, form):
        post = self.object
        
        # Check if user can reply to this post
        if not (post.visibility == 'all' or hasattr(self.request.user, 'landlord_profile')):
            messages.warning(self.request, "You don't have permission to reply to this post.")
            return redirect('landlords:community_detail', pk=post.pk)
        
        # Create the reply using the form's save method
        reply = form.save(commit=False)
        reply.post = post
        reply.author = self.request.user
        reply.save()
        
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

@method_decorator(landlord_required, name='dispatch')
class CommunityReplyView(LoginRequiredMixin, CreateView):
    model = CommunityReply
    form_class = CommunityReplyForm
    template_name = 'landlords/community/reply.html'

    def get_success_url(self):
        return reverse_lazy('landlords:community_detail', kwargs={'pk': self.kwargs['post_id']})

    def dispatch(self, request, *args, **kwargs):
        self.post = get_object_or_404(CommunityPost, pk=self.kwargs['post_id'])
        # Check if user can reply to this post
        if not (self.post.visibility == 'all' or hasattr(request.user, 'landlord_profile')):
            messages.warning(request, "You don't have permission to reply to this post.")
            return redirect('seekers:community')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        reply = form.save(commit=False)
        reply.author = self.request.user
        reply.post = self.post
        reply.save()
        messages.success(self.request, 'Your reply has been posted!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['post'] = self.post
        return context

@method_decorator(landlord_required, name='dispatch')
class EditPostView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CommunityPost
    form_class = CommunityPostForm
    template_name = 'landlords/community/edit.html'
    
    def test_func(self):
        # Only allow post author to edit
        post = self.get_object()
        return post.author == self.request.user
    
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
        # Only allow post author to delete
        post = self.get_object()
        return post.author == self.request.user
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Post deleted successfully!')
        return super().delete(request, *args, **kwargs)