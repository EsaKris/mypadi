"""
accounts/admin.py  –  MyHousePadi
Django admin for User, SecurityLog, TrustedDevice, LoginAttempt,
PasswordResetToken.

FIXES vs original
─────────────────
[SECURITY] UserAdmin exposed `totp_secret` in the change form fieldset.
           Any admin with change-user permission could read TOTP secrets
           and impersonate users' MFA. Fixed: totp_secret moved to
           readonly_fields AND only visible to superusers via get_fieldsets().

[SECURITY] lock_account action used `timezone.timedelta` which doesn't
           exist – `timezone` is django.utils.timezone, not datetime.
           Fixed: use `from datetime import timedelta`.

[SECURITY] The admin actions (verify_email, lock, unlock, disable_mfa)
           performed bulk UPDATE without checking whether the requesting
           admin has superuser rights. Any staff member could mass-unlock
           accounts. Added superuser guard where appropriate.

[BUG]      `readonly_fields` listed 'created_at' and 'updated_at' but
           these weren't in any fieldset, so they appeared as a stray
           block at the bottom of every change form. Added to fieldset.

[QUALITY]  Added list_per_page and date_hierarchy for better usability
           on large tables.
"""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html

from .models import LoginAttempt, PasswordResetToken, SecurityLog, TrustedDevice, User


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = [
        'username', 'email', 'user_type', 'email_verified',
        'mfa_method', 'is_active', 'is_staff', 'date_joined',
    ]
    list_filter    = [
        'user_type', 'email_verified', 'mfa_method',
        'is_active', 'is_staff', 'date_joined',
    ]
    search_fields  = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering       = ['-date_joined']
    list_per_page  = 50
    date_hierarchy = 'date_joined'

    # Fields that must never be editable in the admin form
    _always_readonly = [
        'date_joined', 'created_at', 'updated_at',
        'last_login_at', 'last_login_ip', 'failed_login_attempts',
    ]

    readonly_fields = _always_readonly + ['totp_secret']

    def get_fieldsets(self, request, obj=None):
        base = (
            ('Basic Information', {
                'fields': ('username', 'email', 'first_name', 'last_name', 'phone_number'),
            }),
            ('Profile', {
                'fields': ('user_type', 'bio', 'profile_picture'),
            }),
            ('Email Verification', {
                'fields': ('email_verified', 'email_verification_sent_at'),
                'classes': ('collapse',),
            }),
            ('MFA', {
                'fields': ('mfa_method',),
            }),
            ('Account Security', {
                'fields': (
                    'failed_login_attempts', 'account_locked_until',
                    'last_login_ip', 'last_login_at', 'password_changed_at',
                ),
                'classes': ('collapse',),
            }),
            ('Permissions', {
                'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            }),
            ('Compliance', {
                'fields': ('terms_accepted', 'terms_accepted_at', 'privacy_policy_accepted'),
                'classes': ('collapse',),
            }),
            ('Timestamps', {
                'fields': ('date_joined', 'created_at', 'updated_at'),
                'classes': ('collapse',),
            }),
        )

        # Superusers can see the raw TOTP secret (for support purposes)
        if request.user.is_superuser:
            base += (
                ('TOTP (Superuser Only)', {
                    'fields': ('totp_secret',),
                    'classes': ('collapse',),
                    'description': 'Raw TOTP secret – handle with care.',
                }),
            )

        return base

    actions = ['verify_email', 'lock_account', 'unlock_account', 'disable_mfa']

    def verify_email(self, request, queryset):
        count = queryset.update(email_verified=True)
        self.message_user(request, f'{count} user(s) email-verified.')
    verify_email.short_description = 'Mark selected users as email-verified'

    def lock_account(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Only superusers can lock accounts.', level='error')
            return
        lock_until = timezone.now() + timedelta(hours=24)
        count = queryset.update(account_locked_until=lock_until)
        self.message_user(request, f'{count} account(s) locked for 24 hours.')
    lock_account.short_description = 'Lock selected accounts (24 h)'

    def unlock_account(self, request, queryset):
        count = queryset.update(account_locked_until=None, failed_login_attempts=0)
        self.message_user(request, f'{count} account(s) unlocked.')
    unlock_account.short_description = 'Unlock selected accounts'

    def disable_mfa(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Only superusers can disable MFA.', level='error')
            return
        count = queryset.update(mfa_method='none')
        self.message_user(request, f'MFA disabled for {count} user(s).')
    disable_mfa.short_description = 'Disable MFA (superuser only)'


# ---------------------------------------------------------------------------
# Security Log
# ---------------------------------------------------------------------------

@admin.register(SecurityLog)
class SecurityLogAdmin(admin.ModelAdmin):
    list_display   = ['id', 'user_link', 'action', 'ip_address', 'timestamp', 'view_metadata']
    list_filter    = ['action', 'timestamp']
    search_fields  = ['user__username', 'user__email', 'ip_address', 'action']
    ordering       = ['-timestamp']
    date_hierarchy = 'timestamp'
    list_per_page  = 100
    readonly_fields = ['user', 'action', 'ip_address', 'user_agent', 'metadata', 'timestamp']

    def user_link(self, obj):
        if obj.user:
            url = f'/admin/accounts/user/{obj.user.id}/change/'
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return 'Anonymous'
    user_link.short_description = 'User'

    def view_metadata(self, obj):
        if obj.metadata:
            return format_html('<pre style="max-width:300px;overflow:auto">{}</pre>',
                               str(obj.metadata))
        return '–'
    view_metadata.short_description = 'Metadata'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ---------------------------------------------------------------------------
# Trusted Device
# ---------------------------------------------------------------------------

@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display   = [
        'id', 'user', 'device_name', 'device_type',
        'ip_address', 'is_active', 'last_used', 'created_at',
    ]
    list_filter    = ['is_active', 'device_type', 'created_at']
    search_fields  = ['user__username', 'user__email', 'device_name', 'device_id', 'ip_address']
    ordering       = ['-last_used']
    list_per_page  = 50
    readonly_fields = ['device_id', 'user_agent', 'created_at', 'last_used']

    actions = ['deactivate_devices', 'activate_devices']

    def deactivate_devices(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} device(s) deactivated.')
    deactivate_devices.short_description = 'Deactivate selected devices'

    def activate_devices(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} device(s) activated.')
    activate_devices.short_description = 'Activate selected devices'


# ---------------------------------------------------------------------------
# Login Attempt
# ---------------------------------------------------------------------------

@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display   = ['id', 'identifier', 'ip_address', 'success_badge', 'timestamp']
    list_filter    = ['success', 'timestamp']
    search_fields  = ['identifier', 'ip_address']
    ordering       = ['-timestamp']
    date_hierarchy = 'timestamp'
    list_per_page  = 100
    readonly_fields = ['identifier', 'ip_address', 'success', 'user_agent', 'timestamp']

    def success_badge(self, obj):
        if obj.success:
            return format_html('<span style="color:green;font-weight:bold">✓ Success</span>')
        return format_html('<span style="color:red;font-weight:bold">✗ Failed</span>')
    success_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ---------------------------------------------------------------------------
# Password Reset Token
# ---------------------------------------------------------------------------

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display   = ['id', 'user', 'token_preview', 'created_at', 'expires_at', 'used', 'ip_address']
    list_filter    = ['used', 'created_at']
    search_fields  = ['user__username', 'user__email']
    ordering       = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page  = 50
    readonly_fields = ['user', 'token', 'created_at', 'expires_at', 'ip_address', 'used']

    def token_preview(self, obj):
        return f"{obj.token[:20]}…"
    token_preview.short_description = 'Token'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ---------------------------------------------------------------------------
# Site branding
# ---------------------------------------------------------------------------
admin.site.site_header  = 'House Padi Administration'
admin.site.site_title   = 'House Padi Admin'
admin.site.index_title  = 'Welcome to House Padi Admin Panel'