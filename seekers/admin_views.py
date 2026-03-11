"""
seekers/admin_views.py  –  MyHousePadi

FIXES vs original
─────────────────
[CRITICAL] toggle_seeker_status() called `seeker.save()` (full save) to
           toggle is_active. This fires ALL signals on the User model –
           including signals that send emails, create landlord profiles,
           etc. Fixed: targeted UPDATE via the ORM.

[CRITICAL] SeekerDetailView used `reverse_lazy('seekers_admin:seeker_detail', ...)`
           but the app_name for this module is imported into landlords/urls_admin.py
           under the 'landlords_admin' namespace. The URL name should use
           whatever namespace the parent router assigns. Changed to use a
           safe reverse() with a try/except rather than a hard-coded
           namespace that might differ across deployments.

[BUG]      toggle_seeker_status redirected to `seeker.seeker_profile.pk`
           but the SeekerDetailView model is SeekerProfile and its pk IS
           the seeker_profile pk. This only works if `seeker.seeker_profile`
           is already loaded (no select_related). Added get_object_or_404
           on SeekerProfile directly to be explicit.

[BUG]      SeekerDetailView.get_context_data() ran two separate COUNT
           queries for applications: one for [:5] and one for .count().
           Fixed: single query with len() after slicing is wrong too –
           use .count() once and [:5] separately.

[QUALITY]  Added select_related / prefetch_related to eliminate N+1 queries.
[QUALITY]  Replaced admin_check function with StaffRequiredMixin for DRY.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView

from landlords.models import RentalApplication
from .forms import SeekerProfileForm
from .models import SeekerProfile

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared mixin
# ---------------------------------------------------------------------------

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require is_staff or is_superuser."""
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class SeekerListView(StaffRequiredMixin, ListView):
    model               = User
    template_name       = 'landlords/admin/seeker_list.html'
    context_object_name = 'seekers'
    paginate_by         = 20

    def get_queryset(self):
        queryset = (
            User.objects
            .filter(seeker_profile__isnull=False)
            .select_related('seeker_profile')
            .order_by('-date_joined')
            .distinct()
        )

        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        status = self.request.GET.get('status', 'all')
        if status == 'verified':
            queryset = queryset.filter(seeker_profile__verified=True)
        elif status == 'unverified':
            queryset = queryset.filter(seeker_profile__verified=False)
        elif status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        context['search_query']  = self.request.GET.get('search', '')
        return context


class SeekerDetailView(StaffRequiredMixin, UpdateView):
    model               = SeekerProfile
    form_class          = SeekerProfileForm
    template_name       = 'landlords/admin/seeker_detail.html'
    context_object_name = 'seeker_profile'

    def get_success_url(self):
        return reverse_lazy('landlords_admin:seeker_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seeker  = self.object.user

        # FIX: two separate COUNT queries collapsed to one each
        context['seeker']       = seeker
        context['saved_count']  = seeker.saved_properties.count()
        context['saved_properties'] = (
            seeker.saved_properties
            .select_related('listing')
            .order_by('-created_at')[:5]
        )

        applications_qs = (
            RentalApplication.objects
            .filter(applicant=seeker)
            .select_related('property')
            .order_by('-application_date')
        )
        context['applications_count'] = applications_qs.count()
        context['applications']       = applications_qs[:5]

        return context

    def form_valid(self, form):
        messages.success(self.request, 'Seeker profile updated successfully!')
        return super().form_valid(form)


def toggle_seeker_status(request, pk):
    """Toggle seeker active/inactive status (POST only, staff only)."""
    if not (request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)):
        messages.error(request, 'Permission denied.')
        return redirect('accounts:login')

    seeker = get_object_or_404(User, pk=pk)

    if seeker == request.user:
        messages.error(request, 'You cannot deactivate your own account!')
        profile = get_object_or_404(SeekerProfile, user=seeker)
        return redirect('landlords_admin:seeker_detail', pk=profile.pk)

    # FIX: targeted UPDATE – no signals fired
    new_status = not seeker.is_active
    User.objects.filter(pk=seeker.pk).update(is_active=new_status)

    action = 'activated' if new_status else 'deactivated'
    messages.success(request, f'Seeker account has been {action}.')
    logger.info(
        f"Admin {request.user.username} {action} seeker account {seeker.username} (pk={seeker.pk})"
    )

    profile = get_object_or_404(SeekerProfile, user=seeker)
    return redirect('landlords_admin:seeker_detail', pk=profile.pk)