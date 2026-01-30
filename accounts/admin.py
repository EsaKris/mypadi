"""
Production-Ready Django Admin Configuration
Enhanced admin interface with security features
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils import timezone
from .models import User, SecurityLog, TrustedDevice, LoginAttempt, PasswordResetToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced User admin interface"""
    
    list_display = [
        'username', 'email', 'user_type', 'email_verified', 
        'mfa_method', 'is_active', 'is_staff', 'date_joined'
    ]
    list_filter = [
        'user_type', 'email_verified', 'mfa_method', 
        'is_active', 'is_staff', 'date_joined'
    ]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    ordering = ['-date_joined']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('username', 'email', 'first_name', 'last_name', 'phone_number')
        }),
        ('Profile', {
            'fields': ('user_type', 'bio', 'profile_picture')
        }),
        ('Security', {
            'fields': (
                'email_verified', 'mfa_method', 'totp_secret',
                'failed_login_attempts', 'account_locked_until',
                'last_login_ip', 'last_login_at'
            )
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Compliance', {
            'fields': ('terms_accepted', 'terms_accepted_at', 'privacy_policy_accepted')
        }),
        ('Important Dates', {
            'fields': ('date_joined', 'created_at', 'updated_at', 'password_changed_at')
        }),
    )
    
    readonly_fields = [
        'date_joined', 'created_at', 'updated_at', 'last_login_at', 
        'last_login_ip', 'failed_login_attempts'
    ]
    
    actions = ['verify_email', 'lock_account', 'unlock_account', 'disable_mfa']
    
    def verify_email(self, request, queryset):
        """Manually verify user emails"""
        count = queryset.update(email_verified=True)
        self.message_user(request, f'{count} user(s) verified successfully.')
    verify_email.short_description = 'Verify selected users'
    
    def lock_account(self, request, queryset):
        """Lock user accounts"""
        lock_until = timezone.now() + timezone.timedelta(hours=24)
        count = queryset.update(account_locked_until=lock_until)
        self.message_user(request, f'{count} account(s) locked for 24 hours.')
    lock_account.short_description = 'Lock selected accounts'
    
    def unlock_account(self, request, queryset):
        """Unlock user accounts"""
        count = queryset.update(
            account_locked_until=None,
            failed_login_attempts=0
        )
        self.message_user(request, f'{count} account(s) unlocked successfully.')
    unlock_account.short_description = 'Unlock selected accounts'
    
    def disable_mfa(self, request, queryset):
        """Disable MFA for selected users"""
        count = queryset.update(mfa_method='none')
        self.message_user(request, f'MFA disabled for {count} user(s).')
    disable_mfa.short_description = 'Disable MFA'


@admin.register(SecurityLog)
class SecurityLogAdmin(admin.ModelAdmin):
    """Security Log admin interface"""
    
    list_display = [
        'id', 'user_link', 'action', 'ip_address', 'timestamp', 'view_metadata'
    ]
    list_filter = ['action', 'timestamp']
    search_fields = ['user__username', 'user__email', 'ip_address', 'action']
    ordering = ['-timestamp']
    readonly_fields = ['user', 'action', 'ip_address', 'user_agent', 'metadata', 'timestamp']
    
    def user_link(self, obj):
        """Link to user in admin"""
        if obj.user:
            url = f'/admin/accounts/user/{obj.user.id}/change/'
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return 'Anonymous'
    user_link.short_description = 'User'
    
    def view_metadata(self, obj):
        """Display metadata in a readable format"""
        if obj.metadata:
            return format_html('<pre>{}</pre>', str(obj.metadata))
        return '-'
    view_metadata.short_description = 'Metadata'
    
    def has_add_permission(self, request):
        """Disable manual addition"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete logs"""
        return request.user.is_superuser


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    """Trusted Device admin interface"""
    
    list_display = [
        'id', 'user', 'device_name', 'device_type', 
        'ip_address', 'is_active', 'last_used', 'created_at'
    ]
    list_filter = ['is_active', 'device_type', 'created_at']
    search_fields = ['user__username', 'user__email', 'device_name', 'device_id', 'ip_address']
    ordering = ['-last_used']
    readonly_fields = ['device_id', 'user_agent', 'created_at', 'last_used']
    
    fieldsets = (
        ('Device Information', {
            'fields': ('user', 'device_id', 'device_name', 'device_type')
        }),
        ('Network Information', {
            'fields': ('ip_address', 'user_agent')
        }),
        ('Status', {
            'fields': ('is_active', 'expires_at', 'created_at', 'last_used')
        }),
    )
    
    actions = ['deactivate_devices', 'activate_devices']
    
    def deactivate_devices(self, request, queryset):
        """Deactivate selected devices"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} device(s) deactivated.')
    deactivate_devices.short_description = 'Deactivate selected devices'
    
    def activate_devices(self, request, queryset):
        """Activate selected devices"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} device(s) activated.')
    activate_devices.short_description = 'Activate selected devices'


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Login Attempt admin interface"""
    
    list_display = [
        'id', 'identifier', 'ip_address', 'success', 
        'timestamp', 'success_badge'
    ]
    list_filter = ['success', 'timestamp']
    search_fields = ['identifier', 'ip_address']
    ordering = ['-timestamp']
    readonly_fields = ['identifier', 'ip_address', 'success', 'user_agent', 'timestamp']
    
    def success_badge(self, obj):
        """Display success as colored badge"""
        if obj.success:
            return format_html('<span style="color: green;">✓ Success</span>')
        return format_html('<span style="color: red;">✗ Failed</span>')
    success_badge.short_description = 'Status'
    
    def has_add_permission(self, request):
        """Disable manual addition"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Disable editing"""
        return False


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Password Reset Token admin interface"""
    
    list_display = [
        'id', 'user', 'token_preview', 'created_at', 
        'expires_at', 'used', 'ip_address'
    ]
    list_filter = ['used', 'created_at', 'expires_at']
    search_fields = ['user__username', 'user__email', 'token']
    ordering = ['-created_at']
    readonly_fields = ['user', 'token', 'created_at', 'expires_at', 'ip_address', 'used']
    
    def token_preview(self, obj):
        """Show truncated token"""
        return f"{obj.token[:20]}..."
    token_preview.short_description = 'Token'
    
    def has_add_permission(self, request):
        """Disable manual addition"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Disable editing"""
        return False


# Admin site customization
admin.site.site_header = 'House Padi Administration'
admin.site.site_title = 'House Padi Admin'
admin.site.index_title = 'Welcome to House Padi Admin Panel'