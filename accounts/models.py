from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
import pyotp
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('tenant', 'Tenant'),
        ('landlord', 'Landlord'),
        ('both', 'Both'),
        ('admin', 'Admin'),
    )
    
    MFA_METHOD_CHOICES = (
        ('none', 'None'),
        ('email', 'Email'),
        ('google_authenticator', 'Google Authenticator'),
    )
    
    phone_number = models.CharField(max_length=20, blank=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='tenant')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True)
    email_verified = models.BooleanField(default=False)
    
    # Enhanced Security Fields (from first model)
    mfa_method = models.CharField(max_length=20, choices=MFA_METHOD_CHOICES, default='none')
    totp_secret = models.CharField(max_length=32, blank=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(blank=True, null=True)
    
    # Add methods to safely access profiles
    def get_landlord_profile(self):
        from landlords.models import LandlordProfile
        profile, created = LandlordProfile.objects.get_or_create(user=self)
        return profile
        
    def get_user_profile(self):
        from seekers.models import SeekerProfile  # Assuming this is the correct import
        profile, created = SeekerProfile.objects.get_or_create(user=self)
        return profile
    
    def __str__(self):
        return self.username
    
    def is_tenant(self):
        if not hasattr(self, 'user_type'):  # Safety check
            return False
        return self.user_type == 'tenant'
        
    def is_landlord(self):
        if not hasattr(self, 'user_type'):
            return False
        return self.user_type == 'landlord'
        
    def is_admin(self):
        if not hasattr(self, 'is_staff'):
            return False
        return self.is_staff or getattr(self, 'user_type', None) == 'admin'
    
    # Security methods (from first model)
    def is_account_locked(self):
        """Check if the user's account is currently locked"""
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False
    
    def increment_failed_login(self):
        """Increment failed login attempts and lock account if threshold is reached"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:  # Lock after 5 failed attempts
            self.account_locked_until = timezone.now() + timedelta(minutes=30)
        self.save()
    
    def reset_failed_logins(self):
        """Reset failed login attempts and unlock account"""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.save()
    
    def generate_totp_secret(self):
        """Generate a new TOTP secret for Google Authenticator"""
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
            self.save()
        return self.totp_secret
    
    def verify_totp(self, otp):
        """Verify TOTP code for Google Authenticator"""
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(otp, valid_window=1)  # Allow 30-second drift
    
    def requires_mfa(self):
        """Check if user requires MFA verification"""
        return self.mfa_method != 'none' and self.email_verified
    
    def get_display_mfa_method(self):
        """Get display name for MFA method"""
        return dict(self.MFA_METHOD_CHOICES).get(self.mfa_method, 'None')


class SecurityLog(models.Model):
    """Log security-related events for audit trail"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='security_logs')
    action = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Security Log'
        verbose_name_plural = 'Security Logs'
    
    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.timestamp}"


class TrustedDevice(models.Model):
    """Store trusted devices for MFA bypass"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    device_id = models.CharField(max_length=64)
    device_name = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'device_id']
        verbose_name = 'Trusted Device'
        verbose_name_plural = 'Trusted Devices'
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name or self.device_id[:10]}"