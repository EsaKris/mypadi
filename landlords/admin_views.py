# landlords/admin_views.py
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.views.generic import ListView, TemplateView, UpdateView, View, DetailView, CreateView
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from .models import LandlordProfile, Notification, Property, RentalApplication
from .forms import AdminProfileForm, AdminSettingsForm, PropertyVerificationForm, LandlordVerificationForm, LandlordProfileForm, AdminCreationForm, AdminAuthenticationForm

User = get_user_model()

def admin_check(user):
    """Check if user is admin/staff"""
    return user.is_staff or user.is_superuser

class AdminLoginView(LoginView):
    template_name = 'landlords/admin/login.html'
    authentication_form = AdminAuthenticationForm
    redirect_authenticated_user = True  

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_staff:
                return redirect('landlords_admin:dashboard')
            messages.error(request, "Only staff members can access this area")
            return redirect('landlords_admin:login')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:
            messages.error(self.request, "Only staff members can access this area")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('landlords_admin:dashboard')  

class AdminLogoutView(LogoutView):
    template_name = 'landlords/admin/logout.html'
    next_page = reverse_lazy('landlords_admin:login')

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        messages.success(request, "You have been successfully logged out")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        # Handle GET requests by redirecting to POST
        return self.post(request, *args, **kwargs)


class PromoteToSuperAdminView(UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser
    
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_superuser = True
        user.save()
        messages.success(request, f"{user.username} promoted to Super Admin")
        return redirect('landlords_admin:admin_list')

class AdminDetailView(UserPassesTestMixin, DetailView):
    model = User
    template_name = 'landlords/admin/admin_detail.html'
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['default_password'] = 'Padiassist123'
        return context
    
class AdminListView(UserPassesTestMixin, ListView):
    template_name = 'landlords/admin/admin_list.html'
    model = User
    context_object_name = 'admins'
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_queryset(self):
        return User.objects.filter(is_staff=True).order_by('date_joined')
        
class CreateAdminView(UserPassesTestMixin, CreateView):
    template_name = 'landlords/admin/create_admin.html'
    form_class = AdminCreationForm
    success_url = reverse_lazy('landlords_admin:admin_list')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Admin {self.object.username} created with default password 'Padiassist123'"
        )
        return response


class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Admin dashboard overview"""
    template_name = 'landlords/admin/dashboard.html'
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'pending_properties': Property.objects.filter(is_verified=False).count(),
            'pending_landlords': LandlordProfile.objects.filter(is_verified=False).count(),
            'pending_applications': RentalApplication.objects.filter(status='pending').count(),
            'recent_properties': Property.objects.order_by('-created_at')[:5],
            'recent_landlords': LandlordProfile.objects.order_by('-created_at')[:5],
        })
        return context

class PropertyApprovalListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List properties needing approval"""
    model = Property
    template_name = 'landlords/admin/property_approvals.html'
    context_object_name = 'properties'
    paginate_by = 10
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        status = self.request.GET.get('status', 'pending')
        queryset = Property.objects.all()
        
        if status == 'pending':
            queryset = queryset.filter(is_verified=False)
        elif status == 'verified':
            queryset = queryset.filter(is_verified=True)
            
        return queryset.select_related('landlord').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'pending')
        return context

@login_required
@user_passes_test(admin_check)
def property_approval_detail(request, pk):
    """Detail view for property approval"""
    property = get_object_or_404(Property, pk=pk)
    
    if request.method == 'POST':
        form = PropertyVerificationForm(request.POST, instance=property)
        if form.is_valid():
            form.save()
            messages.success(request, 'Property verification updated!')
            return redirect('landlords_admin:property_approvals')
    else:
        form = PropertyVerificationForm(instance=property)
    
    return render(request, 'landlords/admin/property_approval_detail.html', {
        'property': property,
        'form': form
    })

class LandlordVerificationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List landlords needing verification"""
    model = LandlordProfile
    template_name = 'landlords/admin/landlord_verifications.html'
    context_object_name = 'landlords'
    paginate_by = 10
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        status = self.request.GET.get('status', 'pending')
        queryset = LandlordProfile.objects.all()
        
        if status == 'pending':
            queryset = queryset.filter(is_verified=False)
        elif status == 'verified':
            queryset = queryset.filter(is_verified=True)
            
        return queryset.select_related('user').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'pending')
        return context

@login_required
@user_passes_test(admin_check)
def landlord_verification_detail(request, pk):
    """Detail view for landlord verification"""
    landlord = get_object_or_404(LandlordProfile, pk=pk)
    
    if request.method == 'POST':
        form = LandlordVerificationForm(request.POST, instance=landlord)
        if form.is_valid():
            form.save()
            messages.success(request, 'Landlord verification updated!')
            return redirect('landlords_admin:landlord_verifications')
    else:
        form = LandlordVerificationForm(instance=landlord)
    
    return render(request, 'landlords/admin/landlord_verification_detail.html', {
        'landlord': landlord,
        'form': form
    })

class DocumentVerificationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List landlords with documents needing verification"""
    template_name = 'landlords/admin/document_verifications.html'
    context_object_name = 'landlords'
    paginate_by = 10
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        return LandlordProfile.objects.exclude(verification_documents='').filter(
            Q(is_verified=False) | Q(verification_documents__isnull=False)
        ).select_related('user').order_by('-created_at')

@login_required
@user_passes_test(admin_check)
def verify_documents(request, pk):
    """Handle document verification actions"""
    landlord = get_object_or_404(LandlordProfile, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            landlord.is_verified = True
            messages.success(request, 'Documents approved!')
        elif action == 'reject':
            landlord.verification_documents.delete(save=False)
            landlord.verification_documents = None
            messages.warning(request, 'Documents rejected!')
        
        landlord.save()
        return redirect('landlords_admin:document_verifications')
    
    return render(request, 'landlords/admin/document_verification_detail.html', {
        'landlord': landlord
    })

class LandlordListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all landlords"""
    model = User
    template_name = 'landlords/admin/landlord_list.html'
    context_object_name = 'landlords'
    paginate_by = 20
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        queryset = User.objects.filter(
            Q(landlord_profile__isnull=False) | Q(is_staff=True) | Q(is_superuser=True)
        ).distinct().order_by('-date_joined')
        
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(landlord_profile__company_name__icontains=search_query)
            )
            
        status = self.request.GET.get('status', 'all')
        if status == 'verified':
            queryset = queryset.filter(landlord_profile__is_verified=True)
        elif status == 'unverified':
            queryset = queryset.filter(landlord_profile__is_verified=False)
        elif status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
            
        return User.objects.filter(landlord_profile__isnull=False).order_by('-date_joined')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'all')
        context['search_query'] = self.request.GET.get('search', '')
        return context

class LandlordDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Read-only detail view for landlord management"""
    model = User
    template_name = 'landlords/admin/landlord_detail.html'
    context_object_name = 'landlord_user'
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_object(self, queryset=None):
        user = super().get_object(queryset)
        if not hasattr(user, 'landlord_profile'):
            LandlordProfile.objects.get_or_create(user=user)
        return user
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        profile = user.landlord_profile
        
        profile_data = {
            # Personal Information
            'full_name': user.get_full_name(),
            'email': user.email,
            'date_joined': user.date_joined.strftime('%Y-%m-%d'),
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never',
            
            # Profile Information
            'company_name': profile.company_name or 'Not provided',
            'phone_number': profile.phone_number or 'Not provided',
            'business_address': profile.business_address or 'Not provided',
            'bio': profile.bio or 'Not provided',
            
            # Verification Information
            'is_verified': profile.is_verified,
            'verification_documents': bool(profile.verification_documents),
            'phone_verified': profile.phone_verified,
            'phone_verified_date': profile.phone_verified_date.strftime('%Y-%m-%d') if profile.phone_verified_date else 'Not verified',
            'verification_notes': profile.verification_notes or 'No notes',
            
            # Social Media
            'social_facebook': profile.social_facebook,
            'social_twitter': profile.social_twitter,
            'social_linkedin': profile.social_linkedin,
            'social_instagram': profile.social_instagram,
            
            # Profile Picture
            'has_profile_picture': bool(profile.profile_picture),
        }
        
        context.update({
            'landlord_profile': profile,
            'properties': Property.objects.filter(landlord=user).order_by('-created_at')[:5],
            'properties_count': Property.objects.filter(landlord=user).count(),
            'active_properties': Property.objects.filter(landlord=user, is_active=True).count(),
            'profile_data': profile_data
        })
        return context

@login_required
@user_passes_test(admin_check)
def toggle_landlord_status(request, pk):
    """Toggle landlord active status"""
    landlord_user = get_object_or_404(User, pk=pk)
    
    if not hasattr(landlord_user, 'landlord_profile'):
        LandlordProfile.objects.get_or_create(user=landlord_user)
    
    if landlord_user == request.user:
        messages.error(request, "You cannot deactivate your own account!")
        return redirect('landlords_admin:landlord_detail', pk=landlord_user.pk)

    landlord_user.is_active = not landlord_user.is_active
    landlord_user.save()
    
    action = "activated" if landlord_user.is_active else "deactivated"
    messages.success(request, f"Landlord account has been {action}!")
    return redirect('landlords_admin:landlord_detail', pk=landlord_user.pk)


class AdminProfileView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    template_name = 'landlords/admin/profile.html'
    form_class = AdminProfileForm
    success_url = reverse_lazy('landlords_admin:admin_profile')
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_object(self):
        return self.request.user
    
    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully!')
        return super().form_valid(form)

class AdminSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'landlords/admin/settings.html'
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get(self, request):
        initial_data = {
            'dark_mode': request.session.get('dark_mode', False),
            'notifications_enabled': request.session.get('notifications_enabled', True),
            'items_per_page': request.session.get('items_per_page', 20),
        }
        form = AdminSettingsForm(initial=initial_data)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = AdminSettingsForm(request.POST)
        if form.is_valid():
            request.session['dark_mode'] = form.cleaned_data['dark_mode']
            request.session['notifications_enabled'] = form.cleaned_data['notifications_enabled']
            request.session['items_per_page'] = form.cleaned_data['items_per_page']
            messages.success(request, 'Settings updated successfully!')
            return redirect('landlords_admin:admin_settings')
        
        return render(request, self.template_name, {'form': form})

# landlords/admin_views.py
class CombinedAnalyticsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Combined analytics dashboard for seekers and landlords"""
    template_name = 'landlords/admin/combined_analytics.html'
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Seeker statistics
        seekers = User.objects.filter(seeker_profile__isnull=False)
        context['total_seekers'] = seekers.count()
        context['verified_seekers'] = seekers.filter(seeker_profile__verified=True).count()
        context['active_seekers'] = seekers.filter(is_active=True).count()
        context['seeker_registration_trend'] = self.get_registration_trend(seekers)
        
        # Landlord statistics
        landlords = User.objects.filter(landlord_profile__isnull=False)
        context['total_landlords'] = landlords.count()
        context['verified_landlords'] = landlords.filter(landlord_profile__is_verified=True).count()
        context['active_landlords'] = landlords.filter(is_active=True).count()
        context['landlord_registration_trend'] = self.get_registration_trend(landlords)
        
        # Property statistics
        context['total_properties'] = Property.objects.count()
        context['verified_properties'] = Property.objects.filter(is_verified=True).count()
        context['active_properties'] = Property.objects.filter(is_active=True).count()
        
        # Application statistics
        context['total_applications'] = RentalApplication.objects.count()
        context['pending_applications'] = RentalApplication.objects.filter(status='pending').count()
        context['approved_applications'] = RentalApplication.objects.filter(status='approved').count()
        context['rejected_applications'] = RentalApplication.objects.filter(status='rejected').count()
        
        return context
    
    def get_registration_trend(self, queryset):
        """Get registration trend for the last 6 months"""
        from django.db.models.functions import TruncMonth
        from django.db.models import Count
        from datetime import datetime, timedelta
        
        six_months_ago = datetime.now() - timedelta(days=180)
        
        return (
            queryset
            .filter(date_joined__gte=six_months_ago)
            .annotate(month=TruncMonth('date_joined'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )

@login_required
@user_passes_test(admin_check)
def export_combined_report(request):
    """Export combined report as CSV"""
    from django.http import HttpResponse
    import csv
    from datetime import datetime
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="combined_report_{datetime.now().date()}.csv"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow(['Report Type', 'Total', 'Verified', 'Active', 'Pending', 'Approved', 'Rejected'])
    
    # Seeker data
    seekers = User.objects.filter(seeker_profile__isnull=False)
    writer.writerow([
        'Seekers',
        seekers.count(),
        seekers.filter(seeker_profile__verified=True).count(),
        seekers.filter(is_active=True).count(),
        '', '', ''  # Empty columns for application stats
    ])
    
    # Landlord data
    landlords = User.objects.filter(landlord_profile__isnull=False)
    writer.writerow([
        'Landlords',
        landlords.count(),
        landlords.filter(landlord_profile__is_verified=True).count(),
        landlords.filter(is_active=True).count(),
        '', '', ''  # Empty columns for application stats
    ])
    
    # Property data
    writer.writerow([
        'Properties',
        Property.objects.count(),
        Property.objects.filter(is_verified=True).count(),
        Property.objects.filter(is_active=True).count(),
        '', '', ''  # Empty columns for application stats
    ])
    
    # Application data
    writer.writerow([
        'Applications',
        RentalApplication.objects.count(),
        '', '',  # Empty columns for verification/active stats
        RentalApplication.objects.filter(status='pending').count(),
        RentalApplication.objects.filter(status='approved').count(),
        RentalApplication.objects.filter(status='rejected').count()
    ])
    
    return response

class NotificationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all notifications"""
    model = Notification
    template_name = 'landlords/admin/notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unread_count'] = Notification.objects.filter(recipient=self.request.user, is_read=False).count()
        return context

@login_required
@user_passes_test(admin_check)
def mark_notification_as_read(request, pk):
    """Mark a notification as read"""
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.mark_as_read()
    return redirect(notification.related_url) if notification.related_url else redirect('landlords_admin:notifications')

@login_required
@user_passes_test(admin_check)
def mark_all_notifications_as_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read")
    return redirect('landlords_admin:notifications')

class CreateNotificationView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new notification"""
    model = Notification
    fields = ['recipient', 'title', 'message', 'notification_type', 'related_url']
    template_name = 'landlords/admin/notifications/create.html'
    success_url = reverse_lazy('landlords_admin:notifications')
    
    def test_func(self):
        return admin_check(self.request.user)
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Notification sent successfully")
        return response