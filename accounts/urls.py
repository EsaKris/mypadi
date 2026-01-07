from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

app_name = 'accounts'

urlpatterns = [
    # Core Authentication URLs
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    
    # Email Verification URLs
    # path('verify-email/<str:token>/', verify_email, name='verify_email'),
    path('email-verification/pending/', email_verification_pending, name='email_verification_pending'),
    path('verify-email-required/', verify_email_required, name='verify_email_required'),
    path('resend-verification/', resend_verification_email, name='resend_verification'),
    
    # Multi-Factor Authentication URLs
    path('mfa/select/', select_mfa_method, name='select_mfa_method'),
    path('mfa/setup/authenticator/', setup_authenticator, name='setup_authenticator'),
    path('mfa/verify/', mfa_verify_view, name='mfa_verify'),
    
    # Security Management URLs
    path('security/devices/', manage_devices, name='manage_devices'),
    path('security/devices/remove/<int:device_id>/', remove_device, name='remove_device'),
    path('security/logs/', security_logs, name='security_logs'),
    
    # Password Reset URLs (your original configuration)
    path('password-reset/', 
         CustomPasswordResetView.as_view(
             template_name='accounts/password_reset.html',
             email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             success_url=reverse_lazy('accounts:password_reset_done')
         ), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html'
         ), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         CustomPasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete')
         ), 
         name='password_reset_confirm'),
    path('password-reset/complete/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
]