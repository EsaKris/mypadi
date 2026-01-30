"""
Production-Ready URL Configuration
Comprehensive URL patterns for authentication system
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from . import views
from .views import (
    mfa_verify_view, select_mfa_method, setup_authenticator,
    manage_devices, remove_device, security_logs, logout_view,
    verify_email_required, custom_permission_denied_view,
    check_username, check_email, check_phone, regenerate_backup_codes
)

app_name = 'accounts'

urlpatterns = [
    # ===========================
    # CORE AUTHENTICATION
    # ===========================
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    
    # ===========================
    # EMAIL VERIFICATION
    # ===========================
    path(
        'email-verification/pending/', 
        views.email_verification_pending, 
        name='email_verification_pending'
    ),
    path(
        'email-verification/required/', 
        verify_email_required, 
        name='verify_email_required'
    ),
    path(
        'resend-verification/', 
        views.resend_verification_email, 
        name='resend_verification'
    ),
    
    # ===========================
    # MULTI-FACTOR AUTHENTICATION
    # ===========================
    path('mfa/verify/', mfa_verify_view, name='mfa_verify'),
    path('mfa/select/', select_mfa_method, name='select_mfa_method'),
    path('mfa/setup/authenticator/', setup_authenticator, name='setup_authenticator'),
    path('mfa/backup-codes/regenerate/', regenerate_backup_codes, name='regenerate_backup_codes'),
    
    # ===========================
    # SECURITY MANAGEMENT
    # ===========================
    path('security/devices/', manage_devices, name='manage_devices'),
    path('security/devices/remove/<int:device_id>/', remove_device, name='remove_device'),
    path('security/logs/', security_logs, name='security_logs'),
    
    # ===========================
    # PASSWORD RESET
    # ===========================
    path(
        'password-reset/', 
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset.html',
            email_template_name='accounts/emails/password_reset_email.html',
            subject_template_name='accounts/emails/password_reset_subject.txt',
            success_url=reverse_lazy('accounts:password_reset_done'),
            html_email_template_name='accounts/emails/password_reset_email.html',
        ), 
        name='password_reset'
    ),
    path(
        'password-reset/done/', 
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html'
        ), 
        name='password_reset_done'
    ),
    path(
        'password-reset-confirm/<uidb64>/<token>/', 
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete')
        ), 
        name='password_reset_confirm'
    ),
    path(
        'password-reset/complete/', 
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html'
        ), 
        name='password_reset_complete'
    ),
    
    # ===========================
    # PASSWORD CHANGE (for logged-in users)
    # ===========================
    path(
        'password-change/',
        auth_views.PasswordChangeView.as_view(
            template_name='accounts/password_change.html',
            success_url=reverse_lazy('accounts:password_change_done')
        ),
        name='password_change'
    ),
    path(
        'password-change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='accounts/password_change_done.html'
        ),
        name='password_change_done'
    ),
    
    # ===========================
    # AJAX / API ENDPOINTS
    # ===========================
    path('api/check-username/', check_username, name='check_username'),
    path('api/check-email/', check_email, name='check_email'),
    path('api/check-phone/', check_phone, name='check_phone'),
]

# Error Handlers
handler403 = custom_permission_denied_view