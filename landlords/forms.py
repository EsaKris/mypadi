from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm
from django.core.validators import FileExtensionValidator, URLValidator
from urllib.parse import urlparse

from .models import (
    Amenity,
    CommunityPost,
    CommunityReply,
    Expense,
    LeaseAgreement,
    LandlordProfile,
    MaintenanceRequest,
    Payment,
    Property,
    PropertyImage,
    RentalApplication,
    Tenant,
)

User = get_user_model()

ADMIN_DEFAULT_PASSWORD = 'Padiassist123'


# ---------------------------------------------------------------------------
# Shared base mixin
# ---------------------------------------------------------------------------

class BaseFormStyle:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if 'class' not in widget.attrs:
                if isinstance(widget, forms.CheckboxInput):
                    widget.attrs['class'] = (
                        'form-checkbox h-4 w-4 text-primary-600 '
                        'focus:ring-primary-500 border-gray-300 rounded'
                    )
                elif isinstance(widget, forms.Textarea):
                    widget.attrs.setdefault('rows', 3)
                    widget.attrs['class'] = (
                        'form-textarea block w-full rounded-md border-gray-300 '
                        'shadow-sm focus:border-primary-500 focus:ring-primary-500'
                    )
                else:
                    widget.attrs['class'] = (
                        'form-input block w-full rounded-md border-gray-300 '
                        'shadow-sm focus:border-primary-500 focus:ring-primary-500'
                    )
            if 'placeholder' not in widget.attrs and hasattr(field, 'label') and field.label:
                widget.attrs['placeholder'] = field.label


# ---------------------------------------------------------------------------
# Multi-file upload widget & field
# ---------------------------------------------------------------------------

class MultipleFileInput(forms.ClearableFileInput):
    """File input that correctly handles multiple file selection."""
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        defaults = {'multiple': True}
        if attrs:
            defaults.update(attrs)
        super().__init__(defaults)

    def value_from_datadict(self, data, files, name):
        """
        ROOT CAUSE FIX for images not saving on create.

        Django's default ClearableFileInput.value_from_datadict() calls
        files.get(name) which returns only ONE file — the last one —
        even when the HTML input has multiple=True and the user selected
        many files.

        Overriding to use files.getlist(name) returns ALL uploaded files
        for this input name, so MultipleFileField.clean() receives the
        full list and PropertyForm.save() creates a PropertyImage for each.
        """
        return files.getlist(name)


class MultipleFileField(forms.FileField):
    """
    FileField that handles <input type="file" multiple>.
    Always returns a list of file objects (even for a single file).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Nothing submitted — keep existing files if any
        if not data:
            return initial or []

        # Normalise to always be a list
        if not isinstance(data, (list, tuple)):
            data = [data]

        return [super(MultipleFileField, self).clean(d, initial) for d in data]


# ---------------------------------------------------------------------------
# LandlordProfileForm
# ---------------------------------------------------------------------------

class LandlordProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                     'focus:ring-primary-500 focus:border-primary-500',
        }),
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                     'focus:ring-primary-500 focus:border-primary-500',
        }),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                     'focus:ring-primary-500 focus:border-primary-500',
        }),
    )
    profile_picture = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/jpeg,image/png',
            'onchange': 'previewImage(this)',
        }),
    )
    verification_documents = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.FileInput(attrs={'class': 'hidden'}),
    )

    class Meta:
        model = LandlordProfile
        fields = [
            'profile_picture', 'phone_number', 'bio', 'company_name',
            'business_address', 'social_facebook', 'social_twitter',
            'social_linkedin', 'social_instagram', 'verification_documents',
        ]
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'business_address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'social_facebook': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://facebook.com/yourprofile',
            }),
            'social_twitter': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://twitter.com/yourprofile',
            }),
            'social_linkedin': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://linkedin.com/in/yourprofile',
            }),
            'social_instagram': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://instagram.com/yourprofile',
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email

    def _clean_social_url(self, field_name, primary_domain, alternative_domains=None):
        url = self.cleaned_data.get(field_name)
        if not url:
            return None
        url = str(url).strip()
        if not url:
            return None
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        validate = URLValidator()
        try:
            validate(url)
        except forms.ValidationError:
            raise forms.ValidationError(f"Please enter a valid URL for {primary_domain}")
        domain = urlparse(url).netloc.lower()
        allowed = [primary_domain] + (alternative_domains or [])
        if not any(d in domain for d in allowed):
            raise forms.ValidationError(f"Please enter a valid {primary_domain} URL")
        return url

    def clean_social_facebook(self):
        return self._clean_social_url('social_facebook', 'facebook.com')

    def clean_social_twitter(self):
        return self._clean_social_url('social_twitter', 'twitter.com', ['x.com'])

    def clean_social_linkedin(self):
        return self._clean_social_url('social_linkedin', 'linkedin.com')

    def clean_social_instagram(self):
        return self._clean_social_url('social_instagram', 'instagram.com')

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture and hasattr(picture, 'size') and picture.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Image file too large (max 2 MB)")
        return picture


# ---------------------------------------------------------------------------
# PropertyForm
# ---------------------------------------------------------------------------

class PropertyForm(forms.ModelForm):

    images = MultipleFileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        widget=MultipleFileInput(attrs={
            'class': 'hidden',
            'accept': 'image/jpeg,image/png,image/webp',
            'id': 'property-images-input',
        }),
        help_text="Upload up to 12 images (JPEG/PNG/WEBP, max 5 MB each)",
    )

    delete_images = forms.ModelMultipleChoiceField(
        queryset=PropertyImage.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput(),
    )

    amenities = forms.ModelMultipleChoiceField(
        queryset=Amenity.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Property
        fields = [
            'name', 'address', 'city', 'state', 'zip_code',
            'property_type', 'num_units', 'price', 'price_period',
            'description', 'amenities', 'is_active', 'is_published',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Property name',
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Full street address',
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'state': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'zip_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'property_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'num_units': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
                'min': '1',
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
                'step': '0.01',
                'min': '0',
            }),
            'price_period': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
            }),
            'description': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Describe the property features, amenities, and neighbourhood…',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-5 w-5 text-primary-600 focus:ring-primary-500 border-gray-300 rounded',
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_is_published',
            }),
        }
        help_texts = {
            'price': 'Rental price in Naira (₦)',
            'num_units': 'Total number of units in this property',
            'description': 'Minimum 50 characters required',
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['amenities'].initial = self.instance.amenities.all()
            self.fields['delete_images'].queryset = self.instance.images.all()

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price

    def clean_description(self):
        desc = self.cleaned_data.get('description', '')
        if desc and len(desc) < 50:
            raise forms.ValidationError("Description must be at least 50 characters.")
        return desc

    def clean_images(self):
        images = self.cleaned_data.get('images') or []
        if not images:
            return images
        if len(images) > 12:
            raise forms.ValidationError("You can upload a maximum of 12 images.")
        for image in images:
            if hasattr(image, 'size') and image.size > 5 * 1024 * 1024:
                raise forms.ValidationError(f"'{image.name}' is too large (max 5 MB each).")
            content_type = getattr(image, 'content_type', None)
            if content_type and not content_type.startswith('image/'):
                raise forms.ValidationError(f"'{image.name}' is not a valid image file.")
        return images

    def save(self, commit=True):
        prop = super().save(commit=False)

        if commit:
            prop.save()
            self.save_m2m()

            # Delete images marked for removal
            images_to_delete = self.cleaned_data.get('delete_images')
            if images_to_delete:
                for img in images_to_delete:
                    if img.image:
                        img.image.delete(save=False)
                    img.delete()

            # Save new uploaded images
            # Now that value_from_datadict uses getlist(), this receives ALL files
            new_images = self.cleaned_data.get('images') or []
            existing_count = prop.images.count()
            for i, img_file in enumerate(new_images):
                is_primary = (existing_count == 0 and i == 0)
                PropertyImage.objects.create(
                    property=prop,
                    image=img_file,
                    is_primary=is_primary,
                )

        return prop


# ---------------------------------------------------------------------------
# TenantForm
# ---------------------------------------------------------------------------

class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = [
            'property', 'full_name', 'email', 'phone',
            'lease_start', 'lease_end', 'rent_amount',
            'security_deposit', 'emergency_contact', 'notes',
        ]
        widgets = {
            'lease_start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'lease_end': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'property': forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if 'landlord' in self.fields:
            del self.fields['landlord']
        if user:
            self.fields['property'].queryset = Property.objects.filter(landlord=user)
        for field_name, field in self.fields.items():
            if field_name == 'property':
                continue
            if 'class' not in field.widget.attrs:
                if isinstance(field.widget, forms.Textarea):
                    field.widget.attrs['class'] = 'form-control'
                    field.widget.attrs.setdefault('rows', 3)
                else:
                    field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        lease_start = cleaned_data.get('lease_start')
        lease_end = cleaned_data.get('lease_end')
        property_obj = cleaned_data.get('property')
        email = cleaned_data.get('email')

        if lease_start and lease_end and lease_start >= lease_end:
            raise forms.ValidationError("Lease end date must be after lease start date.")

        if property_obj and email:
            qs = Tenant.objects.filter(property=property_obj, email=email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "A tenant with this email already exists for this property."
                )
        return cleaned_data


# ---------------------------------------------------------------------------
# RentalApplicationForm
# ---------------------------------------------------------------------------

class RentalApplicationForm(forms.ModelForm):
    class Meta:
        model = RentalApplication
        fields = [
            'status', 'notes', 'credit_score',
            'employment_verified', 'income_verified',
            'references_checked', 'background_check',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


# ---------------------------------------------------------------------------
# LeaseAgreementForm
# ---------------------------------------------------------------------------

class LeaseAgreementForm(forms.ModelForm):
    class Meta:
        model = LeaseAgreement
        fields = ['start_date', 'end_date', 'monthly_rent', 'security_deposit', 'terms']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'terms': forms.Textarea(attrs={'rows': 10, 'class': 'form-control'}),
        }


# ---------------------------------------------------------------------------
# MaintenanceRequestForm
# ---------------------------------------------------------------------------

class MaintenanceRequestForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = [
            'title', 'description', 'priority', 'status',
            'assigned_to', 'completion_date', 'cost',
            'before_photo', 'after_photo',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'completion_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['assigned_to'].queryset = User.objects.filter(is_staff=True)
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'


# ---------------------------------------------------------------------------
# PaymentForm
# ---------------------------------------------------------------------------

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'payment_method', 'reference_number', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'


# ---------------------------------------------------------------------------
# ExpenseForm
# ---------------------------------------------------------------------------

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'date', 'description', 'receipt']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'form-control'


# ---------------------------------------------------------------------------
# Community forms
# ---------------------------------------------------------------------------

class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ['title', 'content', 'location_tag', 'visibility']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'location_tag': forms.TextInput(attrs={'class': 'form-control'}),
            'visibility': forms.RadioSelect(attrs={'class': 'form-check-input'}),
        }
        labels = {'visibility': 'Post Visibility'}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user and not hasattr(self.user, 'landlord_profile'):
            self.fields.pop('visibility', None)


class CommunityReplyForm(forms.ModelForm):
    class Meta:
        model = CommunityReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Write your reply…',
            }),
        }


# ---------------------------------------------------------------------------
# Admin forms
# ---------------------------------------------------------------------------

class PropertyVerificationForm(BaseFormStyle, forms.ModelForm):
    is_verified = forms.BooleanField(label="Verify Property", required=False)
    is_published = forms.BooleanField(label="Publish Property", required=False)
    verification_notes = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Enter verification notes…'}),
        required=False,
    )

    class Meta:
        model = Property
        fields = ['is_verified', 'is_published', 'verification_notes']


class LandlordVerificationForm(BaseFormStyle, forms.ModelForm):
    is_verified = forms.BooleanField(label="Verify Landlord", required=False)
    verification_notes = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Enter verification notes…'}),
        required=False,
    )

    class Meta:
        model = LandlordProfile
        fields = ['is_verified', 'verification_notes']


class AdminCreationForm(BaseFormStyle, forms.ModelForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'admin@example.com'}),
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'username'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(ADMIN_DEFAULT_PASSWORD)
        user.is_staff = True
        if commit:
            user.save()
        return user


class AdminAuthenticationForm(BaseFormStyle, AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Username'}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'}),
    )

    def confirm_login_allowed(self, user):
        if not user.is_staff:
            raise forms.ValidationError(
                "This account doesn't have admin privileges.",
                code='no_admin_privileges',
            )


class AdminProfileForm(BaseFormStyle, forms.ModelForm):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/jpeg,image/png',
            'id': 'profile-picture-input',
        }),
    )
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    email = forms.EmailField()
    username = forms.CharField()

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('password', None)

    def save(self, commit=True):
        user = super().save(commit=commit)
        return user


class AdminSettingsForm(BaseFormStyle, forms.Form):
    dark_mode = forms.BooleanField(required=False)
    notifications_enabled = forms.BooleanField(required=False)
    items_per_page = forms.IntegerField(min_value=5, max_value=100)