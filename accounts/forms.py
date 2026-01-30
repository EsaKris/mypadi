"""
Production-Ready Django Authentication Forms
Includes: Enhanced validation, security checks, better UX
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import User
from .utils import is_disposable_email, check_password_strength
import re


class EnhancedLoginForm(AuthenticationForm):
    """
    Enhanced login form with support for username, email, or phone login
    """
    username = forms.CharField(
        label="Username, Email or Phone",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Enter your username, email, or phone number',
            'autocomplete': 'username',
            'autofocus': True
        })
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'current-password'
        })
    )
    
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded text-primary-600 focus:ring-primary-400'
        })
    )
    
    def clean(self):
        """Enhanced cleaning with account lock check"""
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # Normalize username/email
            username = username.strip().lower()
            
            # Check if account is locked before authentication
            try:
                user = User.objects.filter(
                    models.Q(username=username) | 
                    models.Q(email=username) | 
                    models.Q(phone_number=username)
                ).first()
                
                if user and user.is_account_locked():
                    raise ValidationError(
                        "Account temporarily locked due to too many failed login attempts. "
                        "Please try again later or reset your password.",
                        code='account_locked'
                    )
            except User.DoesNotExist:
                pass
        
        return super().clean()
    
    def clean_username(self):
        """Normalize username field"""
        username = self.cleaned_data.get('username', '')
        return username.strip().lower()


class RegistrationForm(UserCreationForm):
    """
    Enhanced registration form with comprehensive validation
    """
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'First Name',
            'autocomplete': 'given-name'
        })
    )
    
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Last Name',
            'autocomplete': 'family-name'
        })
    )
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email'
        })
    )
    
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Choose a username',
            'autocomplete': 'username'
        }),
        help_text='Username must be 3-150 characters. Letters, digits, and @/./+/-/_ only.'
    )
    
    phone_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'flex-grow px-4 py-3 rounded-r-lg border-t border-r border-b border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '801 234 5678',
            'autocomplete': 'tel'
        }),
        help_text='Optional. Format: +1234567890'
    )
    
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'new-password'
        }),
        help_text='Must be at least 8 characters with uppercase, lowercase, number, and special character.'
    )
    
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••',
            'autocomplete': 'new-password'
        })
    )
    
    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'mt-1 mr-2 rounded text-primary-600 focus:ring-primary-400'
        }),
        error_messages={
            'required': 'You must accept the terms and conditions to register.'
        }
    )
    
    USER_TYPE_CHOICES = [
        ('', '--- Select your role ---'),
        ('tenant', 'I want to find a property (House Seeker)'),
        ('landlord', 'I want to list my property (Landlord)'),
        ('both', 'I want to do both'),
    ]
    
    user_type = forms.ChoiceField(
        choices=USER_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
        }),
        label="I am registering as:",
        required=True,
        initial='',
        error_messages={
            'required': 'Please select your role.'
        }
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone_number', 'user_type', 'password1', 'password2']
    
    def clean_username(self):
        """Enhanced username validation"""
        username = self.cleaned_data.get('username', '').strip().lower()
        
        # Length check
        if len(username) < 3:
            raise ValidationError("Username must be at least 3 characters long.")
        
        # Character validation
        if not re.match(r'^[\w.@+-]+$', username):
            raise ValidationError("Username can only contain letters, numbers, and @/./+/-/_ characters.")
        
        # Reserved usernames
        reserved_usernames = {'admin', 'root', 'system', 'administrator', 'moderator', 'support'}
        if username in reserved_usernames:
            raise ValidationError("This username is reserved.")
        
        # Check uniqueness
        if User.objects.filter(username=username).exists():
            raise ValidationError("This username is already taken.")
        
        return username
    
    def clean_email(self):
        """Enhanced email validation"""
        email = self.cleaned_data.get('email', '').strip().lower()
        
        # Check for disposable email
        if is_disposable_email(email):
            raise ValidationError("Disposable email addresses are not allowed.")
        
        # Check uniqueness
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already registered.")
        
        return email
    
    def clean_phone_number(self):
        """Enhanced phone validation"""
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        
        if phone_number:
            # Remove common separators
            phone_clean = re.sub(r'[\s\-\(\)]', '', phone_number)
            
            # Basic validation
            if not re.match(r'^\+?\d{9,15}$', phone_clean):
                raise ValidationError("Invalid phone number format. Use format: +1234567890")
            
            # Check uniqueness
            if User.objects.filter(phone_number=phone_clean).exists():
                raise ValidationError("This phone number is already registered.")
            
            return phone_clean
        
        return phone_number
    
    def clean_password1(self):
        """Enhanced password validation"""
        password = self.cleaned_data.get('password1')
        
        # Check password strength
        is_strong, message = check_password_strength(password)
        if not is_strong:
            raise ValidationError(message)
        
        # Django's built-in validators
        validate_password(password)
        
        return password
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Ensure user type is selected
        user_type = cleaned_data.get('user_type')
        if not user_type or user_type == '':
            raise ValidationError({'user_type': 'Please select your role.'})
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save user with additional fields"""
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email').lower()
        user.phone_number = self.cleaned_data.get('phone_number', '')
        user.user_type = self.cleaned_data.get('user_type')
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        user.terms_accepted = True
        user.terms_accepted_at = timezone.now()
        
        if commit:
            user.save()
        return user


class MFAMethodForm(forms.ModelForm):
    """Multi-Factor Authentication method selection form"""
    
    MFA_CHOICES = [
        ('none', 'No MFA (Less Secure)'),
        ('email', 'Email OTP (Recommended)'),
        ('google_authenticator', 'Google Authenticator (Most Secure)'),
    ]
    
    mfa_method = forms.ChoiceField(
        choices=MFA_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'mfa-radio'
        }),
        label="Select your preferred authentication method:",
        required=True
    )
    
    class Meta:
        model = User
        fields = ['mfa_method']


class OTPVerificationForm(forms.Form):
    """OTP verification form with enhanced validation"""
    
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition text-center text-lg font-mono',
            'placeholder': '000000',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6',
            'autofocus': True
        }),
        error_messages={
            'required': 'Please enter the 6-digit verification code',
            'min_length': 'Verification code must be 6 digits',
            'max_length': 'Verification code must be 6 digits'
        }
    )
    
    def clean_otp(self):
        """Validate OTP format"""
        otp = self.cleaned_data.get('otp', '').strip()
        
        # Must be exactly 6 digits
        if not re.match(r'^\d{6}$', otp):
            raise ValidationError("Verification code must be exactly 6 digits.")
        
        return otp


class CustomPasswordResetForm(PasswordResetForm):
    """Enhanced password reset form"""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email'
        })
    )
    
    def clean_email(self):
        """Validate email exists"""
        email = self.cleaned_data.get('email', '').strip().lower()
        
        # Check if user exists (but don't reveal in error message for security)
        if not User.objects.filter(email=email).exists():
            # Still return success to prevent user enumeration
            pass
        
        return email


class ResendVerificationForm(forms.Form):
    """Form for resending email verification"""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email'
        })
    )
    
    def clean_email(self):
        """Validate email (without revealing if account exists)"""
        email = self.cleaned_data.get('email', '').strip().lower()
        return email


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile"""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'bio', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
                'rows': 4
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
                'accept': 'image/*'
            })
        }
    
    def clean_phone_number(self):
        """Validate phone number"""
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        
        if phone_number:
            phone_clean = re.sub(r'[\s\-\(\)]', '', phone_number)
            
            if not re.match(r'^\+?\d{9,15}$', phone_clean):
                raise ValidationError("Invalid phone number format.")
            
            # Check uniqueness (excluding current user)
            if User.objects.filter(phone_number=phone_clean).exclude(pk=self.instance.pk).exists():
                raise ValidationError("This phone number is already in use.")
            
            return phone_clean
        
        return phone_number


# Import required for Q objects
from django.db import models
from django.utils import timezone