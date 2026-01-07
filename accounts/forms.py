from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm
from django.core.exceptions import ValidationError
from .models import User

class EnhancedLoginForm(AuthenticationForm):
    username = forms.CharField(
    label="Username, Email or Phone",
    max_length=150,
    widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'Enter your username, email, or phone number'
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••'
        })
    )
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            try:
                user = User.objects.get(username=username)
                if user.is_account_locked():
                    raise ValidationError(
                        "Account temporarily locked due to too many failed login attempts. "
                        "Please try again later or reset your password."
                    )
            except User.DoesNotExist:
                pass
                
        return super().clean()

class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com'
        })
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com'
        })
    )
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'flex-grow px-4 py-3 rounded-r-lg border-t border-r border-b border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '801 234 5678'
        })
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••'
        })
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': '••••••••'
        })
    )
    terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'mt-1 mr-2 rounded text-primary-600 focus:ring-primary-400'
        })
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
        initial=''
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone_number', 'user_type', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email address is already in use.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number and User.objects.filter(phone_number=phone_number).exists():
            raise ValidationError("This phone number is already in use.")
        return phone_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.phone_number = self.cleaned_data.get('phone_number')
        user.user_type = self.cleaned_data.get('user_type')
        user.email = self.cleaned_data.get('email')
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        if commit:
            user.save()
        return user

class MFAMethodForm(forms.ModelForm):
    MFA_CHOICES = [
        ('none', 'No MFA (Less Secure)'),
        ('email', 'Email OTP (Recommended)'),
        ('google_authenticator', 'Google Authenticator (Most Secure)'),
    ]
    
    mfa_method = forms.ChoiceField(
        choices=MFA_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'mfa-radio hidden'
        }),
        label="Select your preferred authentication method:",
        required=True
    )
    
    class Meta:
        model = User
        fields = ['mfa_method']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add classes to radio options for styling
        self.fields['mfa_method'].widget.attrs.update({'class': 'mfa-radio-option'})

class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition text-center text-lg font-mono',
            'placeholder': '000000',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]*'
        }),
        error_messages={
            'required': 'Please enter the 6-digit verification code',
            'min_length': 'Verification code must be 6 digits',
            'max_length': 'Verification code must be 6 digits'
        }
    )

class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com'
        })
    )

class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400 transition',
            'placeholder': 'your@email.com'
        })
    )
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        try:
            user = User.objects.get(email=email)
            if user.email_verified:
                raise ValidationError("This email address is already verified.")
        except User.DoesNotExist:
            raise ValidationError("No account found with this email address.")
        return email

# Keep the original LoginForm for backward compatibility
class LoginForm(EnhancedLoginForm):
    """Backward compatibility alias - use EnhancedLoginForm for new code"""
    pass