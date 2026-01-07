from cProfile import Profile
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm
from django.core.validators import FileExtensionValidator, URLValidator
from django.forms import ValidationError
from .models import (
    Amenity, LandlordProfile, Property, PropertyImage, Tenant, RentalApplication,
    LeaseAgreement, MaintenanceRequest, Payment, Expense, CommunityPost, CommunityReply, User
)

User = get_user_model()

class LandlordProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
        })
    )
    profile_picture = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'onchange': 'previewImage(this)'
        })
    )
    verification_documents = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        widget=forms.FileInput(attrs={'class': 'hidden'})
    )

    class Meta:
        model = LandlordProfile
        fields = [
            'profile_picture',
            'phone_number',
            'bio',
            'company_name',
            'business_address',
            'social_facebook',
            'social_twitter',
            'social_linkedin',
            'social_instagram',
            'verification_documents'
        ]
        widgets = {
            'phone_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'business_address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'social_facebook': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://facebook.com/yourprofile'
            }),
            'social_twitter': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://twitter.com/yourprofile'
            }),
            'social_linkedin': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://linkedin.com/in/yourprofile'
            }),
            'social_instagram': forms.URLInput(attrs={
                'class': 'w-full px-3 py-1 text-sm border border-gray-300 rounded-lg',
                'placeholder': 'https://instagram.com/yourprofile'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email

    def clean_social_facebook(self):
        return self._clean_social_url('facebook.com')

    def clean_social_twitter(self):
        return self._clean_social_url('twitter.com', ['x.com'])

    def clean_social_linkedin(self):
        return self._clean_social_url('linkedin.com')

    def clean_social_instagram(self):
        return self._clean_social_url('instagram.com')

    def _clean_social_url(self, primary_domain, alternative_domains=None):
        field_name = f'social_{primary_domain.split(".")[0]}'
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
            
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        allowed_domains = [primary_domain] + (alternative_domains or [])
        
        if not any(allowed_domain in domain for allowed_domain in allowed_domains):
            raise forms.ValidationError(f"Please enter a valid {primary_domain} URL")
            
        return url

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture and picture.size > 2*1024*1024:
            raise forms.ValidationError("Image file too large ( > 2MB )")
        return picture

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        default_attrs = {'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data and initial:
            return initial
            
        if isinstance(data, (list, tuple)):
            result = [super().clean(d, initial) for d in data]
        else:
            result = super().clean(data, initial)
        return result

class PropertyForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        widget=MultipleFileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'id': 'property-images-input'
        }),
        help_text="Upload up to 12 images (JPEG/PNG, max 5MB each)"
    )
    
    delete_images = forms.ModelMultipleChoiceField(
        queryset=PropertyImage.objects.none(),
        required=False,
        widget=forms.MultipleHiddenInput()
    )
    
    amenities = forms.ModelMultipleChoiceField(
        queryset=Amenity.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'grid grid-cols-2 md:grid-cols-3 gap-2'
        })
    )

    class Meta:
        model = Property
        fields = [
            'name', 'address', 'city', 'state', 'zip_code', 
            'property_type', 'num_units', 'price', 'price_period',
            'description', 'amenities', 'is_active', 'is_featured',
            'is_published'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Property name'
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Full street address'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'state': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'zip_code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'property_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'num_units': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500',
                'min': '1'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500',
                'step': '0.01',
                'min': '0'
            }),
            'price_period': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
            }),
            'description': forms.Textarea(attrs={
                'rows': 6,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500',
                'placeholder': 'Describe property features, amenities, and neighborhood...'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-5 w-5 text-primary-600 focus:ring-primary-500 border-gray-300 rounded'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'h-5 w-5 text-primary-600 focus:ring-primary-500 border-gray-300 rounded'
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_is_published'
            }),
        }
        help_texts = {
            'price': 'Monthly rental price in local currency',
            'num_units': 'Total number of units in this property',
            'description': 'Minimum 50 characters required'
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            self.fields['amenities'].initial = self.instance.amenities.all()
            self.fields['delete_images'].queryset = self.instance.images.all()

    def clean(self):
        cleaned_data = super().clean()
        
        price = cleaned_data.get('price')
        if price is not None and price < 0:
            self.add_error('price', 'Price cannot be negative')
            
        description = cleaned_data.get('description')
        if description and len(description) < 50:
            self.add_error('description', 'Description must be at least 50 characters')
            
        return cleaned_data

    def clean_images(self):
        images = self.cleaned_data.get('images', [])
        if not images:
            return images
            
        if len(images) > 12:
            raise forms.ValidationError("Maximum 12 images allowed")
        
        for image in images:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("One or more images are too large (max 5MB each)")
            if not image.content_type.startswith('image/'):
                raise forms.ValidationError("Only image files are allowed")
                
        return images

    def save(self, commit=True):
        property = super().save(commit=False)
        
        if commit:
            property.save()
            self.save_m2m()
            
            # Handle uploaded images
            images = self.cleaned_data.get('images')
            if images:
                for i, img in enumerate(images):
                    PropertyImage.objects.create(
                        property=property,
                        image=img,
                        is_primary=(i == 0)  # first image = primary
                    )
            
            # Handle deleted images
            delete_images = self.cleaned_data.get('delete_images')
            if delete_images:
                delete_images.delete()
        
        return property

# landlords/forms.py
class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['property', 'full_name', 'email', 'phone', 'lease_start', 'lease_end', 
                 'rent_amount', 'security_deposit', 'emergency_contact', 'notes']
        widgets = {
            'lease_start': forms.DateInput(attrs={'type': 'date'}),
            'lease_end': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'property': forms.HiddenInput(),  # Make property field hidden
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Remove landlord field if it exists
        if 'landlord' in self.fields:
            del self.fields['landlord']
        
        # Filter properties to only those owned by the user
        if user:
            self.fields['property'].queryset = Property.objects.filter(landlord=user)
        
        # Add form-control class to all visible fields
        for field_name, field in self.fields.items():
            if field_name != 'property':  # Skip hidden field
                if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.NumberInput, forms.DateInput, forms.Select)):
                    field.widget.attrs.update({'class': 'form-control'})
                elif isinstance(field.widget, forms.Textarea):
                    field.widget.attrs.update({'class': 'form-control', 'rows': 3})

    def clean(self):
        cleaned_data = super().clean()
        lease_start = cleaned_data.get('lease_start')
        lease_end = cleaned_data.get('lease_end')
        property_obj = cleaned_data.get('property')
        email = cleaned_data.get('email')

        # Validate lease dates
        if lease_start and lease_end:
            if lease_start >= lease_end:
                raise forms.ValidationError("Lease end date must be after lease start date.")

        # Check for existing tenant with same email and property
        if property_obj and email:
            existing_tenant = Tenant.objects.filter(
                property=property_obj,
                email=email
            )
            # Exclude current instance if editing
            if self.instance and self.instance.pk:
                existing_tenant = existing_tenant.exclude(pk=self.instance.pk)
            
            if existing_tenant.exists():
                raise forms.ValidationError("A tenant with this email already exists for this property.")

        return cleaned_data
    
class RentalApplicationForm(forms.ModelForm):
    class Meta:
        model = RentalApplication
        fields = ['status', 'notes', 'credit_score', 'employment_verified', 
                 'income_verified', 'references_checked', 'background_check']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class LeaseAgreementForm(forms.ModelForm):
    class Meta:
        model = LeaseAgreement
        fields = ['start_date', 'end_date', 'monthly_rent', 'security_deposit', 'terms']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'terms': forms.Textarea(attrs={'rows': 10}),
        }

class MaintenanceRequestForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['title', 'description', 'priority', 'status', 'assigned_to', 
                 'completion_date', 'cost', 'before_photos', 'after_photos']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['assigned_to'].queryset = User.objects.filter(is_staff=True)

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'payment_method', 'reference_number', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'amount', 'date', 'description', 'receipt']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ['title', 'content', 'location_tag', 'visibility']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location_tag': forms.TextInput(attrs={'class': 'form-control'}),
            'visibility': forms.RadioSelect(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'visibility': 'Post Visibility'
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if not hasattr(self.user, 'landlord_profile'):
            self.fields.pop('visibility')

class CommunityReplyForm(forms.ModelForm):
    class Meta:
        model = CommunityReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3, 
                'class': 'form-control',
                'placeholder': 'Write your reply...'
            }),
        }

class BaseFormStyle(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Add common classes to all widgets
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-input block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
                })
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'rows': 3,
                    'class': 'form-textarea block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
                })
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-checkbox h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded'
                })

class PropertyVerificationForm(BaseFormStyle, forms.ModelForm):
    is_verified = forms.BooleanField(
        label="Verify Property",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox h-5 w-5 text-primary-600 transition duration-150 ease-in-out'
        })
    )
    
    is_published = forms.BooleanField(
        label="Publish Property",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox h-5 w-5 text-primary-600 transition duration-150 ease-in-out'
        })
    )
    
    verification_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter verification notes...',
            'class': 'form-textarea mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        required=False
    )

    class Meta:
        model = Property
        fields = ['is_verified', 'is_published', 'verification_notes']

class LandlordVerificationForm(BaseFormStyle, forms.ModelForm):
    is_verified = forms.BooleanField(
        label="Verify Landlord",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox h-5 w-5 text-primary-600 transition duration-150 ease-in-out'
        })
    )
    
    verification_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter verification notes...',
            'class': 'form-textarea mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        required=False
    )

    class Meta:
        model = LandlordProfile
        fields = ['is_verified', 'verification_notes']

class AdminCreationForm(BaseFormStyle, forms.ModelForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'admin@example.com',
            'class': 'form-input block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'username',
            'class': 'form-input block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email')
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password('Padiassist123')
        user.is_staff = True
        if commit:
            user.save()
        return user

class AdminAuthenticationForm(BaseFormStyle, AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': 'Username',
            'class': 'form-input block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Password',
            'class': 'form-input block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )

    def confirm_login_allowed(self, user):
        if not user.is_staff:
            raise forms.ValidationError(
                "This account doesn't have admin privileges.",
                code='no_admin_privileges',
            )

class AdminProfileForm(BaseFormStyle, UserChangeForm):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'hidden',
            'accept': 'image/*',
            'id': 'profile-picture-input'
        })
    )

    
    first_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'First name'
        })
    )
    
    last_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Last name'
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Email address'
        })
    )
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Username'
        })
    )

    class Meta:
        model = User
        fields = ('profile_picture', 'first_name', 'last_name', 'email', 'username')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('password')
        
        # Initialize with existing profile picture if available
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['profile_picture'].initial = self.instance.profile.profile_picture

    def save(self, commit=True):
        user = super().save(commit=commit)
        
        # Handle profile picture (assuming User model has profile_picture field)
        profile_picture = self.cleaned_data.get('profile_picture')
        remove_picture = self.data.get('remove_profile_picture', False)
        
        if remove_picture:
            # Remove existing picture if requested
            if user.profile_picture:
                user.profile_picture.delete(save=False)
            user.profile_picture = None
        elif profile_picture:
            # If a new picture was uploaded, replace the existing one
            if user.profile_picture:
                user.profile_picture.delete(save=False)
            user.profile_picture = profile_picture
                
        if commit:
            user.save()
            
        return user

class AdminSettingsForm(BaseFormStyle, forms.Form):
    dark_mode = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500'
        })
    )
    
    notifications_enabled = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500'
        })
    )
    
    items_per_page = forms.IntegerField(
        min_value=5,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': '10'
        })
    )

class BaseFormStyle:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if 'class' not in field.widget.attrs:
                field.widget.attrs['class'] = 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
            if 'placeholder' not in field.widget.attrs and hasattr(field, 'label'):
                field.widget.attrs['placeholder'] = field.label