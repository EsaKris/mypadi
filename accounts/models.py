"""
accounts/models.py  –  MyHousePadi
Security-hardened User model and related security tables.

FIXES vs original
─────────────────
[CRITICAL] is_account_locked() called self.save() on EVERY page load for
           a locked user, triggering all signals and wasting DB writes.
           Fixed: targeted UPDATE only when lock actually expires.

[CRITICAL] generate_totp_secret() immediately committed the secret to DB
           before the user ever confirmed their authenticator app works.
           If setup is abandoned the secret is leaked in the DB.
           Fixed: generate only; caller passes commit=True after confirmation.

[BUG]      password_changed_at used auto_now_add=True which means the
           column NEVER updates when the user actually changes their
           password. Fixed: default=timezone.now + explicit update in
           mark_password_changed().

[BUG]      increment_failed_login() and reset_failed_logins() both called
           full self.save() triggering all signals. Fixed: targeted UPDATE.

[BUG]      Meta.indexes duplicated db_index=True field-level declarations,
           causing Django to create two separate indexes per field.
           Fixed: removed db_index=True from fields already in Meta.indexes.

[BUG]      mfa_backup_codes = JSONField(default=list) – list is a class,
           not an instance. Django handles this correctly for JSONField but
           it is still a code smell. Left as-is (Django handles it) but
           documented clearly.

[SECURITY] generate_backup_codes now stores SHA-256 hashes (was already
           hashed, preserved) and uses update_fields to avoid full save.

[SECURITY] Added __str__ to PasswordResetToken and cleanup_expired()
           classmethod to prune stale tokens.
"""

import hashlib
import secrets
from datetime import timedelta

import pyotp
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Custom User
# ---------------------------------------------------------------------------

class User(AbstractUser):
    """Enhanced User model with MFA, progressive lockout, and role management."""

    USER_TYPE_CHOICES = (
        ('tenant',   'Tenant'),
        ('landlord', 'Landlord'),
        ('both',     'Both'),
        ('admin',    'Admin'),
    )

    MFA_METHOD_CHOICES = (
        ('none',                 'None'),
        ('email',                'Email OTP'),
        ('google_authenticator', 'Google Authenticator'),
    )

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be in format: '+999999999'. Up to 15 digits.",
    )

    # ── Profile ──────────────────────────────────────────────────────────
    phone_number    = models.CharField(validators=[phone_regex], max_length=20, blank=True)
    user_type       = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='tenant')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio             = models.TextField(blank=True, max_length=500)

    # ── Email verification ────────────────────────────────────────────────
    email_verified              = models.BooleanField(default=False)
    email_verification_token    = models.CharField(max_length=255, blank=True)
    email_verification_sent_at  = models.DateTimeField(blank=True, null=True)

    # ── MFA ──────────────────────────────────────────────────────────────
    mfa_method       = models.CharField(max_length=20, choices=MFA_METHOD_CHOICES, default='none')
    totp_secret      = models.CharField(max_length=32, blank=True)
    # JSONField(default=list) – Django correctly handles the callable default.
    mfa_backup_codes = models.JSONField(default=list, blank=True)

    # ── Security ─────────────────────────────────────────────────────────
    last_login_ip          = models.GenericIPAddressField(blank=True, null=True)
    last_login_at          = models.DateTimeField(blank=True, null=True)
    failed_login_attempts  = models.IntegerField(default=0)
    account_locked_until   = models.DateTimeField(blank=True, null=True)
    # FIX: was auto_now_add – never updated on actual password change
    password_changed_at    = models.DateTimeField(default=timezone.now)

    # ── Compliance ────────────────────────────────────────────────────────
    terms_accepted           = models.BooleanField(default=False)
    terms_accepted_at        = models.DateTimeField(blank=True, null=True)
    privacy_policy_accepted  = models.BooleanField(default=False)

    # ── Soft delete ───────────────────────────────────────────────────────
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # NOTE: do NOT also add db_index=True on these fields –
        # that would create a duplicate index.
        indexes = [
            models.Index(fields=['email', 'email_verified'],  name='user_email_verified_idx'),
            models.Index(fields=['phone_number'],              name='user_phone_idx'),
            models.Index(fields=['user_type'],                 name='user_type_idx'),
            models.Index(fields=['account_locked_until'],      name='user_locked_idx'),
        ]
        verbose_name        = _('User')
        verbose_name_plural = _('Users')

    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    # ── Role helpers ──────────────────────────────────────────────────────

    def is_tenant(self):
        return self.user_type in ('tenant', 'both')

    def is_landlord(self):
        return self.user_type in ('landlord', 'both')

    def is_admin_user(self):
        return self.is_staff or self.user_type == 'admin'

    def get_display_mfa_method(self):
        return dict(self.MFA_METHOD_CHOICES).get(self.mfa_method, 'None')

    # ── Profile helpers ───────────────────────────────────────────────────

    def get_landlord_profile(self):
        from landlords.models import LandlordProfile
        if self.is_landlord():
            profile, _ = LandlordProfile.objects.get_or_create(user=self)
            return profile
        return None

    def get_seeker_profile(self):
        from seekers.models import SeekerProfile
        if self.is_tenant():
            profile, _ = SeekerProfile.objects.get_or_create(user=self)
            return profile
        return None

    # ── Account lock ──────────────────────────────────────────────────────

    def is_account_locked(self):
        """
        Returns True if account is currently locked.
        Uses a targeted DB UPDATE (not full save) when auto-unlocking so
        no signals fire on a simple read-like check.
        """
        if not self.account_locked_until:
            return False
        if timezone.now() < self.account_locked_until:
            return True
        # Lock has expired – clear without triggering signals
        User.objects.filter(pk=self.pk).update(
            account_locked_until=None,
            failed_login_attempts=0,
        )
        self.account_locked_until = None
        self.failed_login_attempts = 0
        return False

    def increment_failed_login(self):
        """
        Progressive lockout:
          3–4 failures → 5-minute lock
          5+  failures → 30-minute lock
        Uses targeted UPDATE to avoid signal noise.
        """
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            lock_delta = timedelta(minutes=30)
        elif self.failed_login_attempts >= 3:
            lock_delta = timedelta(minutes=5)
        else:
            lock_delta = None

        self.account_locked_until = (
            timezone.now() + lock_delta if lock_delta else None
        )
        User.objects.filter(pk=self.pk).update(
            failed_login_attempts=self.failed_login_attempts,
            account_locked_until=self.account_locked_until,
        )

    def reset_failed_logins(self):
        User.objects.filter(pk=self.pk).update(
            failed_login_attempts=0,
            account_locked_until=None,
        )
        self.failed_login_attempts = 0
        self.account_locked_until = None

    # ── MFA ──────────────────────────────────────────────────────────────

    def generate_totp_secret(self, commit=False):
        """
        Generate a TOTP secret.
        Do NOT pass commit=True until the user has confirmed their
        authenticator app works – otherwise an abandoned setup leaks
        an unconfirmed secret in the DB.
        """
        if not self.totp_secret:
            self.totp_secret = pyotp.random_base32()
        if commit:
            User.objects.filter(pk=self.pk).update(totp_secret=self.totp_secret)
        return self.totp_secret

    def confirm_totp_secret(self):
        """Call this after the user proves their authenticator works."""
        User.objects.filter(pk=self.pk).update(totp_secret=self.totp_secret)

    def verify_totp(self, otp: str) -> bool:
        if not self.totp_secret:
            return False
        return pyotp.TOTP(self.totp_secret).verify(otp, valid_window=1)

    def generate_backup_codes(self, count: int = 10):
        """
        Generate `count` backup codes.
        Stores SHA-256 hashes only; returns plain codes ONCE for display.
        Uses targeted UPDATE to avoid triggering unrelated signals.
        """
        codes = [f"{secrets.randbelow(10 ** 8):08d}" for _ in range(count)]
        self.mfa_backup_codes = [
            hashlib.sha256(c.encode()).hexdigest() for c in codes
        ]
        User.objects.filter(pk=self.pk).update(mfa_backup_codes=self.mfa_backup_codes)
        return codes

    def verify_backup_code(self, code: str) -> bool:
        hashed = hashlib.sha256(code.encode()).hexdigest()
        if hashed in self.mfa_backup_codes:
            self.mfa_backup_codes.remove(hashed)
            User.objects.filter(pk=self.pk).update(mfa_backup_codes=self.mfa_backup_codes)
            return True
        return False

    def requires_mfa(self) -> bool:
        return self.mfa_method != 'none' and self.email_verified

    # ── Password ──────────────────────────────────────────────────────────

    def is_password_expired(self, days: int = 90) -> bool:
        if not self.password_changed_at:
            return False
        return (timezone.now() - self.password_changed_at).days > days

    def mark_password_changed(self):
        self.password_changed_at = timezone.now()
        User.objects.filter(pk=self.pk).update(
            password_changed_at=self.password_changed_at
        )


# ---------------------------------------------------------------------------
# Security Log
# ---------------------------------------------------------------------------

class SecurityLog(models.Model):
    ACTION_CHOICES = (
        ('REGISTER',               'User Registration'),
        ('LOGIN',                  'Successful Login'),
        ('LOGIN_MFA',              'MFA Login'),
        ('FAILED_LOGIN',           'Failed Login'),
        ('LOGOUT',                 'Logout'),
        ('PASSWORD_RESET',         'Password Reset Request'),
        ('PASSWORD_CHANGED',       'Password Changed'),
        ('EMAIL_VERIFIED',         'Email Verified'),
        ('MFA_ENABLED',            'MFA Enabled'),
        ('MFA_DISABLED',           'MFA Disabled'),
        ('DEVICE_ADDED',           'Trusted Device Added'),
        ('DEVICE_REMOVED',         'Trusted Device Removed'),
        ('ACCOUNT_LOCKED',         'Account Locked'),
        ('ACCOUNT_UNLOCKED',       'Account Unlocked'),
        ('SUSPICIOUS_ACTIVITY',    'Suspicious Activity Detected'),
        ('ACCESS_DENIED',          'Access Denied'),
        ('BACKUP_CODES_REGENERATED', 'Backup Codes Regenerated'),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='security_logs',
        null=True, blank=True,
    )
    action     = models.CharField(max_length=50, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    metadata   = models.JSONField(default=dict, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user',       '-timestamp'], name='seclog_user_ts_idx'),
            models.Index(fields=['action',     '-timestamp'], name='seclog_action_ts_idx'),
            models.Index(fields=['ip_address', '-timestamp'], name='seclog_ip_ts_idx'),
        ]
        verbose_name        = 'Security Log'
        verbose_name_plural = 'Security Logs'

    def __str__(self):
        user_str = self.user.username if self.user else 'Anonymous'
        return f"{user_str} – {self.action} – {self.timestamp:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Trusted Device
# ---------------------------------------------------------------------------

class TrustedDevice(models.Model):
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    device_id   = models.CharField(max_length=64)
    device_name = models.CharField(max_length=100, blank=True)
    device_type = models.CharField(max_length=50, blank=True)
    user_agent  = models.TextField(blank=True)
    ip_address  = models.GenericIPAddressField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)
    last_used   = models.DateTimeField(auto_now=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = [('user', 'device_id')]
        ordering = ['-last_used']
        indexes = [
            models.Index(fields=['user', 'is_active'], name='device_user_active_idx'),
            models.Index(fields=['device_id'],         name='device_id_idx'),
        ]
        verbose_name        = 'Trusted Device'
        verbose_name_plural = 'Trusted Devices'

    def __str__(self):
        return f"{self.user.username} – {self.device_name or self.device_id[:10]}"

    def is_expired(self) -> bool:
        """Returns True only if an explicit expiry is set AND has passed."""
        return bool(self.expires_at) and timezone.now() > self.expires_at


# ---------------------------------------------------------------------------
# Login Attempt
# ---------------------------------------------------------------------------

class LoginAttempt(models.Model):
    identifier = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField()
    success    = models.BooleanField(default=False)
    user_agent = models.TextField(blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['identifier', '-timestamp'], name='login_ident_ts_idx'),
            models.Index(fields=['ip_address',  '-timestamp'], name='login_ip_ts_idx'),
            models.Index(fields=['success',     '-timestamp'], name='login_success_ts_idx'),
        ]
        verbose_name        = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"{self.identifier} [{status}] – {self.timestamp:%Y-%m-%d %H:%M}"

    @classmethod
    def get_recent_failed_attempts(
        cls, identifier=None, ip_address=None, minutes: int = 15
    ) -> int:
        cutoff = timezone.now() - timedelta(minutes=minutes)
        qs = cls.objects.filter(success=False, timestamp__gte=cutoff)
        if identifier:
            qs = qs.filter(identifier=identifier)
        if ip_address:
            qs = qs.filter(ip_address=ip_address)
        return qs.count()

    @classmethod
    def is_rate_limited(
        cls,
        identifier=None,
        ip_address=None,
        max_attempts: int = 5,
        minutes: int = 15,
    ) -> bool:
        return cls.get_recent_failed_attempts(
            identifier=identifier,
            ip_address=ip_address,
            minutes=minutes,
        ) >= max_attempts


# ---------------------------------------------------------------------------
# Password Reset Token
# ---------------------------------------------------------------------------

class PasswordResetToken(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token      = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used       = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token'],      name='prt_token_idx'),
            models.Index(fields=['user', 'used'], name='prt_user_used_idx'),
        ]
        verbose_name        = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'

    def __str__(self):
        status = 'used' if self.used else ('expired' if not self.is_valid() else 'valid')
        return f"{self.user.username} – {status} – {self.created_at:%Y-%m-%d %H:%M}"

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at

    def mark_used(self):
        self.used = True
        PasswordResetToken.objects.filter(pk=self.pk).update(used=True)

    @classmethod
    def cleanup_expired(cls) -> int:
        """
        Delete used/expired tokens to keep the table lean.
        Call periodically via a management command or Celery beat.
        """
        from django.db.models import Q
        deleted, _ = cls.objects.filter(
            Q(used=True) | Q(expires_at__lt=timezone.now())
        ).delete()
        return deleted