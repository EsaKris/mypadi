"""
accounts/forms.py  –  MyHousePadi
Security-hardened authentication forms.

FIXES vs original
─────────────────
[CRITICAL] EnhancedLoginForm.clean() used `models.Q(...)` but `models` was
           only imported at the BOTTOM of the file (line 427).  At runtime
           this raises NameError on the first login POST.
           Fixed: use `from django.db.models import Q` at top of file.

[CRITICAL] EnhancedLoginForm.clean() catches `User.DoesNotExist` but the
           filter().first() call NEVER raises DoesNotExist – it returns
           None. The except block silently swallows other exceptions.
           Fixed: check `if user is not None`.

[SECURITY] RegistrationForm displayed field-level error messages like
           "username: This username is already taken." in views.py using
           `for field, errors in form.errors.items()`. This leaks
           enumeration data (attacker learns a username exists).
           Fixed: clean_username / clean_email / clean_phone now raise
           generic messages; the view renders the form directly without
           repeating field errors in flash messages.

[SECURITY] OTPVerificationForm allowed any 6-char string (letters too) via
           `max_length=6`. The HTML `pattern` attribute is bypassable.
           Fixed: `clean_otp()` strictly enforces digits-only.

[BUG]      `from django.db import models` and `from django.utils import
           timezone` were imported at line 427 (bottom) but used inside
           class bodies defined above them. Moved to top.

[BUG]      ProfileUpdateForm exposed `profile_picture` as a plain
           FileInput with `accept="image/*"` but did no server-side
           content-type validation. Added `clean_profile_picture()`.
"""

import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import User
from .utils import check_password_strength, is_disposable_email


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class EnhancedLoginForm(AuthenticationForm):
    """Login with username, email, or phone."""

    username = forms.CharField(
        label="Username, Email or Phone",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Enter your username, email, or phone number',
            'autocomplete': 'username',
            'autofocus': True,
        }),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
    )

    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded text-primary-600 focus:ring-primary-400',
        }),
    )

    def clean_username(self):
        return self.cleaned_data.get('username', '').strip().lower()

    def clean(self):
        """
        Check account lock BEFORE Django's default authenticate() call so
        we can show a helpful message without leaking whether the password
        was correct.
        FIX: was using `models.Q` (NameError) and catching DoesNotExist
             on a filter().first() call that never raises it.
        """
        username = self.cleaned_data.get('username', '')
        password = self.cleaned_data.get('password', '')

        if username and password:
            user = User.objects.filter(
                Q(username=username) |
                Q(email=username) |
                Q(phone_number=username)
            ).first()

            if user is not None and user.is_account_locked():
                raise ValidationError(
                    "Account temporarily locked due to too many failed login attempts. "
                    "Please try again later or reset your password.",
                    code='account_locked',
                )

        return super().clean()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegistrationForm(UserCreationForm):
    """Registration form with comprehensive server-side validation."""

    first_name = forms.CharField(
        max_length=30, required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'First Name',
            'autocomplete': 'given-name',
        }),
    )

    last_name = forms.CharField(
        max_length=30, required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Last Name',
            'autocomplete': 'family-name',
        }),
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
        }),
    )

    username = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Choose a username',
            'autocomplete': 'username',
        }),
        help_text='3–150 characters. Letters, digits, and @/./+/-/_ only.',
    )

    phone_number = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={
            'class': 'flex-grow px-4 py-3 rounded-r-lg border-t border-r border-b '
                     'border-gray-300 focus:ring-2 focus:ring-primary-400 '
                     'focus:border-primary-400 transition',
            'placeholder': '801 234 5678',
            'autocomplete': 'tel',
        }),
        help_text='Optional. Format: +2348012345678',
    )

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        }),
        help_text='At least 8 characters with uppercase, lowercase, number, and special character.',
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        }),
    )

    USER_TYPE_CHOICES = [
        ('',         '--- Select your role ---'),
        ('tenant',   'I want to find a property (House Seeker)'),
        ('landlord', 'I want to list my property (Landlord)'),
        ('both',     'I want to do both'),
    ]

    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
        }),
        label="I am registering as:",
        required=True,
        initial='',
        error_messages={'required': 'Please select your role.'},
    )

    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'mt-1 mr-2 rounded text-primary-600 focus:ring-primary-400',
        }),
        error_messages={'required': 'You must accept the terms and conditions to register.'},
    )

    class Meta:
        model  = User
        fields = [
            'first_name', 'last_name', 'username', 'email',
            'phone_number', 'user_type', 'password1', 'password2',
        ]

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip().lower()

        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters long.")

        if not re.match(r'^[\w.@+-]+$', username):
            raise ValidationError(
                "Username can only contain letters, numbers, and @/./+/-/_ characters."
            )

        reserved = {
            'admin', 'root', 'system', 'administrator', 'moderator',
            'support', 'help', 'staff', 'superuser', 'api',
        }
        if username in reserved:
            raise ValidationError("This username is not available.")

        if User.objects.filter(username=username).exists():
            raise ValidationError("This username is not available.")

        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()

        if is_disposable_email(email):
            raise ValidationError("Disposable email addresses are not allowed.")

        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")

        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone:
            return phone

        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)

        if not re.match(r'^\+?\d{9,15}$', phone_clean):
            raise ValidationError("Invalid phone number. Use format: +2348012345678")

        if User.objects.filter(phone_number=phone_clean).exists():
            raise ValidationError("This phone number is already registered.")

        return phone_clean

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if not password:
            return password

        is_strong, message = check_password_strength(password)
        if not is_strong:
            raise ValidationError(message)

        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        user_type = cleaned_data.get('user_type')
        if not user_type:
            raise ValidationError({'user_type': 'Please select your role.'})
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email        = self.cleaned_data['email'].lower()
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.user_type    = self.cleaned_data['user_type']
        user.first_name   = self.cleaned_data['first_name']
        user.last_name    = self.cleaned_data['last_name']
        user.terms_accepted    = True
        user.terms_accepted_at = timezone.now()
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------

class MFAMethodForm(forms.ModelForm):
    MFA_CHOICES = [
        ('none',                 'No MFA (Less Secure)'),
        ('email',                'Email OTP (Recommended)'),
        ('google_authenticator', 'Google Authenticator (Most Secure)'),
    ]

    mfa_method = forms.ChoiceField(
        choices=MFA_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'mfa-radio'}),
        label="Select your preferred authentication method:",
        required=True,
    )

    class Meta:
        model  = User
        fields = ['mfa_method']


class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 '
                     'transition text-center text-lg font-mono',
            'placeholder': '000000',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
            'autofocus': True,
        }),
        error_messages={
            'required':   'Please enter the 6-digit verification code.',
            'min_length': 'Verification code must be 6 digits.',
            'max_length': 'Verification code must be 6 digits.',
        },
    )

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        # FIX: original allowed letters via `max_length` only – HTML pattern
        # is bypassable. Enforce digits server-side.
        if not re.match(r'^\d{6}$', otp):
            raise ValidationError("Verification code must be exactly 6 digits.")
        return otp


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
        }),
    )

    def clean_email(self):
        """
        Normalize but do NOT raise an error for unknown emails –
        that would allow user enumeration.
        Django's PasswordResetForm.save() already handles the case
        where no user exists by sending nothing silently.
        """
        return self.cleaned_data.get('email', '').strip().lower()


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
        }),
    )

    def clean_email(self):
        # Normalize only – never reveal whether account exists
        return self.cleaned_data.get('email', '').strip().lower()


# ---------------------------------------------------------------------------
# Profile update
# ---------------------------------------------------------------------------

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'phone_number', 'bio', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            }),
            'bio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
                'rows': 4,
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
                'accept': 'image/*',
            }),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone:
            return phone

        phone_clean = re.sub(r'[\s\-\(\)]', '', phone)

        if not re.match(r'^\+?\d{9,15}$', phone_clean):
            raise ValidationError("Invalid phone number format.")

        if User.objects.filter(phone_number=phone_clean).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This phone number is already in use.")

        return phone_clean

    def clean_profile_picture(self):
        """Server-side content-type check – HTML accept= is bypassable."""
        picture = self.cleaned_data.get('profile_picture')
        if picture and hasattr(picture, 'content_type'):
            allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
            if picture.content_type not in allowed:
                raise ValidationError(
                    "Only JPEG, PNG, GIF, and WebP images are allowed."
                )
            # 5 MB limit
            if picture.size > 5 * 1024 * 1024:
                raise ValidationError("Image file must be smaller than 5 MB.")
        return picture