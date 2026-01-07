# seekers/admin_views.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.generic import ListView, UpdateView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import SeekerProfile
from .forms import SeekerProfileForm
from landlords.models import RentalApplication

User = get_user_model()

def admin_check(user):
    """Check if user is admin/staff"""
    return user.is_staff or user.is_superuser

class SeekerListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all seekers"""
    model = User
    template_name = 'landlords/admin/seeker_list.html'
    context_object_name = 'seekers'
    paginate_by = 20
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        queryset = User.objects.filter(
            seeker_profile__isnull=False
        ).distinct().order_by('-date_joined')
        
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
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
            
        return queryset.select_related('seeker_profile')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        context['search_query'] = self.request.GET.get('search', '')
        return context

class SeekerDetailView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Detail view for seeker management"""
    model = SeekerProfile
    form_class = SeekerProfileForm
    template_name = 'landlords/admin/seeker_detail.html'
    context_object_name = 'seeker_profile'
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('seekers_admin:seeker_detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seeker = self.object.user
        context['seeker'] = seeker
        context['saved_properties'] = seeker.saved_properties.all().select_related('property')[:5]
        context['saved_count'] = seeker.saved_properties.count()
        context['applications'] = RentalApplication.objects.filter(applicant=seeker).order_by('-application_date')[:5]
        context['applications_count'] = RentalApplication.objects.filter(applicant=seeker).count()
        return context
    
    def form_valid(self, form):
        messages.success(self.request, 'Seeker profile updated successfully!')
        return super().form_valid(form)

@login_required
@user_passes_test(admin_check)
def toggle_seeker_status(request, pk):
    """Toggle seeker active status"""
    seeker = get_object_or_404(User, pk=pk)
    
    if seeker == request.user:
        messages.error(request, "You cannot deactivate your own account!")
        return redirect('seekers_admin:seeker_detail', pk=seeker.seeker_profile.pk)
    
    seeker.is_active = not seeker.is_active
    seeker.save()
    
    action = "activated" if seeker.is_active else "deactivated"
    messages.success(request, f"Seeker account has been {action}!")
    return redirect('seekers_admin:seeker_detail', pk=seeker.seeker_profile.pk)