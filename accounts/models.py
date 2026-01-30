"""
Production-Ready Django Authentication Models
Includes: User management, Security logging, Device tracking, Rate limiting
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
import pyotp
from datetime import timedelta
import secrets


class User(AbstractUser):
    """Enhanced User model with security features"""
    
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
    
    # Phone number validator
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    
    # User Profile Fields
    phone_number = models.CharField(
        validators=[phone_regex], 
        max_length=20, 
        blank=True,
        db_index=True  # Index for faster lookups
    )
    user_type = models.CharField(
        max_length=10, 
        choices=USER_TYPE_CHOICES, 
        default='tenant',
        db_index=True
    )
    profile_picture = models.ImageField(
        upload_to='profile_pics/', 
        blank=True, 
        null=True
    )
    bio = models.TextField(blank=True, max_length=500)
    
    # Email Verification
    email_verified = models.BooleanField(default=False, db_index=True)
    email_verification_token = models.CharField(max_length=255, blank=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)
    
    # Multi-Factor Authentication
    mfa_method = models.CharField(
        max_length=20, 
        choices=MFA_METHOD_CHOICES, 
        default='none'
    )
    totp_secret = models.CharField(max_length=32, blank=True)
    mfa_backup_codes = models.JSONField(default=list, blank=True)  # Store hashed backup codes
    
    # Security Fields
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(blank=True, null=True, db_index=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)
    
    # Privacy & Compliance
    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(blank=True, null=True)
    privacy_policy_accepted = models.BooleanField(default=False)
    
    # Soft Delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['email', 'email_verified']),
            models.Index(fields=['phone_number']),
            models.Index(fields=['user_type']),
            models.Index(fields=['account_locked_until']),
        ]
        verbose_name = _('User')
        verbose_name_plural = _('Users')
    
    def __str__(self):
        return self.username
    
    def save(self, *args, **kwargs):
        """Override save to ensure email is lowercase"""
        if self.email:
            self.email = self.email.lower().strip()
        super().save(*args, **kwargs)
    
    # Role Check Methods
    def is_tenant(self):
        """Check if user is a tenant or has both roles"""
        return self.user_type in ['tenant', 'both']
    
    def is_landlord(self):
        """Check if user is a landlord or has both roles"""
        return self.user_type in ['landlord', 'both']
    
    def is_admin_user(self):
        """Check if user is admin or staff"""
        return self.is_staff or self.user_type == 'admin'
    
    # Profile Methods
    def get_landlord_profile(self):
        """Safely get or create landlord profile"""
        from landlords.models import LandlordProfile
        if self.is_landlord():
            profile, created = LandlordProfile.objects.get_or_create(user=self)
            return profile
        return None
    
    def get_seeker_profile(self):
        """Safely get or create seeker profile"""
        from seekers.models import SeekerProfile
        if self.is_tenant():
            profile, created = SeekerProfile.objects.get_or_create(user=self)
            return profile
        return None
    
    # Security Methods
    def is_account_locked(self):
        """Check if the user's account is currently locked"""
        if self.account_locked_until:
            if timezone.now() < self.account_locked_until:
                return True
            else:
                # Auto-unlock if lock period has passed
                self.account_locked_until = None
                self.failed_login_attempts = 0
                self.save(update_fields=['account_locked_until', 'failed_login_attempts'])
        return False
    
    def increment_failed_login(self):
        """
        Increment failed login attempts with progressive lockout
        1-2 attempts: No lock
        3-4 attempts: 5 minutes
        5+ attempts: 30 minutes
        """
        self.failed_login_attempts += 1
        
        if self.failed_login_attempts >= 5:
            lock_duration = timedelta(minutes=30)
        elif self.failed_login_attempts >= 3:
            lock_duration = timedelta(minutes=5)
        else:
            lock_duration = None
        
        if lock_duration:
            self.account_locked_until = timezone.now() + lock_duration
        
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])
    
    def reset_failed_logins(self):
        """Reset failed login attempts and unlock account"""
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])
    
    # MFA Methods
    def generate_totp_secret(self):
        """Generate a new TOTP secret for Google Authenticator"""
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
            self.save(update_fields=['totp_secret'])
        return self.totp_secret
    
    def verify_totp(self, otp):
        """Verify TOTP code for Google Authenticator"""
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(otp, valid_window=1)
    
    def generate_backup_codes(self, count=10):
        """Generate MFA backup codes (hashed)"""
        import hashlib
        codes = []
        hashed_codes = []
        
        for _ in range(count):
            code = f"{secrets.randbelow(10**8):08d}"
            codes.append(code)
            hashed_codes.append(hashlib.sha256(code.encode()).hexdigest())
        
        self.mfa_backup_codes = hashed_codes
        self.save(update_fields=['mfa_backup_codes'])
        return codes  # Return unhashed codes to display to user ONCE
    
    def verify_backup_code(self, code):
        """Verify and consume a backup code"""
        import hashlib
        hashed_code = hashlib.sha256(code.encode()).hexdigest()
        
        if hashed_code in self.mfa_backup_codes:
            self.mfa_backup_codes.remove(hashed_code)
            self.save(update_fields=['mfa_backup_codes'])
            return True
        return False
    
    def requires_mfa(self):
        """Check if user requires MFA verification"""
        return self.mfa_method != 'none' and self.email_verified
    
    def get_display_mfa_method(self):
        """Get display name for MFA method"""
        return dict(self.MFA_METHOD_CHOICES).get(self.mfa_method, 'None')
    
    # Password Methods
    def is_password_expired(self, days=90):
        """Check if password is older than specified days"""
        if not self.password_changed_at:
            return False
        age = timezone.now() - self.password_changed_at
        return age.days > days
    
    def mark_password_changed(self):
        """Update password change timestamp"""
        self.password_changed_at = timezone.now()
        self.save(update_fields=['password_changed_at'])


class SecurityLog(models.Model):
    """Comprehensive security event logging"""
    
    ACTION_CHOICES = (
        ('REGISTER', 'User Registration'),
        ('LOGIN', 'Successful Login'),
        ('LOGIN_MFA', 'MFA Login'),
        ('FAILED_LOGIN', 'Failed Login'),
        ('LOGOUT', 'Logout'),
        ('PASSWORD_RESET', 'Password Reset Request'),
        ('PASSWORD_CHANGED', 'Password Changed'),
        ('EMAIL_VERIFIED', 'Email Verified'),
        ('MFA_ENABLED', 'MFA Enabled'),
        ('MFA_DISABLED', 'MFA Disabled'),
        ('DEVICE_ADDED', 'Trusted Device Added'),
        ('DEVICE_REMOVED', 'Trusted Device Removed'),
        ('ACCOUNT_LOCKED', 'Account Locked'),
        ('ACCOUNT_UNLOCKED', 'Account Unlocked'),
        ('SUSPICIOUS_ACTIVITY', 'Suspicious Activity Detected'),
        ('ACCESS_DENIED', 'Access Denied'),
    )
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='security_logs',
        null=True,  # Allow null for anonymous attempts
        blank=True
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # Store additional context
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
        ]
        verbose_name = 'Security Log'
        verbose_name_plural = 'Security Logs'
    
    def __str__(self):
        user_str = self.user.username if self.user else 'Anonymous'
        return f"{user_str} - {self.action} - {self.timestamp}"


class TrustedDevice(models.Model):
    """Store trusted devices for MFA bypass"""
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='trusted_devices'
    )
    device_id = models.CharField(max_length=64, db_index=True)
    device_name = models.CharField(max_length=100, blank=True)
    device_type = models.CharField(max_length=50, blank=True)  # mobile, desktop, tablet
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)  # Optional device expiration
    
    class Meta:
        unique_together = ['user', 'device_id']
        ordering = ['-last_used']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['device_id']),
        ]
        verbose_name = 'Trusted Device'
        verbose_name_plural = 'Trusted Devices'
    
    def __str__(self):
        return f"{self.user.username} - {self.device_name or self.device_id[:10]}"
    
    def is_expired(self):
        """Check if device trust has expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class LoginAttempt(models.Model):
    """Track login attempts for rate limiting and security monitoring"""
    
    identifier = models.CharField(max_length=255, db_index=True)  # username/email/phone
    ip_address = models.GenericIPAddressField(db_index=True)
    success = models.BooleanField(default=False, db_index=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['identifier', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
            models.Index(fields=['success', '-timestamp']),
        ]
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'
    
    @classmethod
    def get_recent_failed_attempts(cls, identifier=None, ip_address=None, minutes=15):
        """Get recent failed login attempts for rate limiting"""
        cutoff = timezone.now() - timedelta(minutes=minutes)
        query = cls.objects.filter(success=False, timestamp__gte=cutoff)
        
        if identifier:
            query = query.filter(identifier=identifier)
        if ip_address:
            query = query.filter(ip_address=ip_address)
        
        return query.count()
    
    @classmethod
    def is_rate_limited(cls, identifier=None, ip_address=None, max_attempts=5):
        """Check if identifier or IP is rate limited"""
        attempts = cls.get_recent_failed_attempts(identifier, ip_address)
        return attempts >= max_attempts


class PasswordResetToken(models.Model):
    """Track password reset tokens separately for better security"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField()
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'
    
    def is_valid(self):
        """Check if token is still valid"""
        return not self.used and timezone.now() < self.expires_at
    
    def mark_used(self):
        """Mark token as used"""
        self.used = True
        self.save(update_fields=['used'])