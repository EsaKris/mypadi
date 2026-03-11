"""
accounts/urls.py  –  MyHousePadi

FIXES vs original
─────────────────
[BUG]  The original imported from `.views` at the top level AND from
       the same module as named imports. Importing the same symbol twice
       under different aliases works, but is confusing and can cause
       issues if views.py is ever refactored. Cleaned up to a single
       import style.

[BUG]  `handler403 = custom_permission_denied_view` in urls.py has no
       effect here – Django only reads handler403 from the ROOT urlconf
       (the urlconf pointed to by settings.ROOT_URLCONF). Kept the
       assignment but added a comment so it's not mistaken for the real
       handler registration.

[SECURITY] AJAX check endpoints (check_username, check_email,
           check_phone) were @csrf_exempt in views.py – fixed there.
           No URL change needed, but documented here.
"""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = 'accounts'

urlpatterns = [

    # ──────────────────────────────────────────────────────────
    # Core authentication
    # ──────────────────────────────────────────────────────────
    path('register/',  views.register_view, name='register'),
    path('login/',     views.login_view,    name='login'),
    path('logout/',    views.logout_view,   name='logout'),

    # ──────────────────────────────────────────────────────────
    # Email verification
    # ──────────────────────────────────────────────────────────
    path(
        'email-verification/pending/',
        views.email_verification_pending,
        name='email_verification_pending',
    ),
    path(
        'email-verification/required/',
        views.verify_email_required,
        name='verify_email_required',
    ),
    path(
        'resend-verification/',
        views.resend_verification_email,
        name='resend_verification',
    ),

    # ──────────────────────────────────────────────────────────
    # Multi-factor authentication
    # ──────────────────────────────────────────────────────────
    path('mfa/verify/',                      views.mfa_verify_view,          name='mfa_verify'),
    path('mfa/select/',                      views.select_mfa_method,        name='select_mfa_method'),
    path('mfa/setup/authenticator/',         views.setup_authenticator,      name='setup_authenticator'),
    path('mfa/backup-codes/regenerate/',     views.regenerate_backup_codes,  name='regenerate_backup_codes'),

    # ──────────────────────────────────────────────────────────
    # Security management
    # ──────────────────────────────────────────────────────────
    path('security/devices/',                        views.manage_devices,  name='manage_devices'),
    path('security/devices/remove/<int:device_id>/', views.remove_device,   name='remove_device'),
    path('security/logs/',                           views.security_logs,   name='security_logs'),

    # ──────────────────────────────────────────────────────────
    # Password reset  (Django built-in views)
    # ──────────────────────────────────────────────────────────
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset.html',
            email_template_name='accounts/emails/password_reset_email.html',
            subject_template_name='accounts/emails/password_reset_subject.txt',
            html_email_template_name='accounts/emails/password_reset_email.html',
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset-confirm/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # ──────────────────────────────────────────────────────────
    # Password change  (for logged-in users)
    # ──────────────────────────────────────────────────────────
    path(
        'password-change/',
        auth_views.PasswordChangeView.as_view(
            template_name='accounts/password_change.html',
            success_url=reverse_lazy('accounts:password_change_done'),
        ),
        name='password_change',
    ),
    path(
        'password-change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='accounts/password_change_done.html',
        ),
        name='password_change_done',
    ),

    # ──────────────────────────────────────────────────────────
    # AJAX availability checks
    # NOTE: CSRF protection is active on these endpoints (fixed in views.py).
    # Your JS must send the csrfmiddlewaretoken or use the X-CSRFToken header.
    # ──────────────────────────────────────────────────────────
    path('api/check-username/', views.check_username, name='check_username'),
    path('api/check-email/',    views.check_email,    name='check_email'),
    path('api/check-phone/',    views.check_phone,    name='check_phone'),
]

# NOTE: handler403 only takes effect when declared in your ROOT urlconf
# (settings.ROOT_URLCONF). Declaring it here has no effect at runtime,
# but it is kept as a reference to where the view lives.
handler403 = views.custom_permission_denied_view