from django import forms
from django.db import models 
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.core.files.images import get_image_dimensions
from django.core.files.base import ContentFile
from django.core.validators import MinValueValidator, FileExtensionValidator
from .models import SeekerProfile, CommunityPost, Property, SavedProperty, CommunityReply
from core.models import Conversation, Message

User = get_user_model()

class SeekerProfileForm(forms.ModelForm):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'accept': 'image/*'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    
    class Meta:
        model = SeekerProfile
        fields = [
            'profile_picture',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'bio',
            'date_of_birth',
            'gender',
            'employment_status',
            'current_address',
            'budget_min',
            'budget_max',
            'preferred_property_type',
            'preferred_locations',
            'move_in_date',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'move_in_date': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 4}),
            'current_address': forms.Textarea(attrs={'rows': 3}),
            'preferred_locations': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        initial = kwargs.pop('initial', {})
        super().__init__(*args, **kwargs)
        
        for field in ['first_name', 'last_name', 'email']:
            if field in initial:
                self.fields[field].initial = initial[field]
    
    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            # Check file size (5MB limit)
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Image file too large (max 5MB)")
            
            # Check image dimensions
            try:
                width, height = get_image_dimensions(picture)
                if width > 2000 or height > 2000:
                    raise forms.ValidationError("Image dimensions too large (max 2000x2000px)")
            except (AttributeError, TypeError):
                raise forms.ValidationError("Invalid image format")
            
            # Store the file content in memory for later use
            picture.file.seek(0)
            self.image_file = picture.file.read()
            self.image_name = picture.name
        return picture
    
    def save(self, commit=True):
        profile = super().save(commit=False)
        
        if hasattr(self, 'image_file'):
            # Delete old profile picture if it exists
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            
            # Save new profile picture from memory
            profile.profile_picture.save(
                self.image_name,
                ContentFile(self.image_file),
                save=False
            )
        
        user = profile.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        
        if commit:
            user.save()
            profile.save()
        
        return profile


class CommunityPostForm(forms.ModelForm):
    class Meta:
        model = CommunityPost
        fields = ['title', 'content', 'location_tag']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 8, 
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400'
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400'
            }),
            'location_tag': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400'
            }),
        }


class CommunityReplyForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
            'placeholder': 'Write your reply here...'
        }),
        label='',  # Remove the label for cleaner appearance
        required=True
    )

    def __init__(self, *args, **kwargs):
        # Safely handle request if passed (but not required)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # You can add request-based customizations here if needed
        if self.request:
            # Example: Customize based on user permissions
            pass


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'property']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'flex-1 px-4 py-2 rounded-l-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Type your message...'
            }),
            'property': forms.HiddenInput()
        }
        reply_to = forms.IntegerField(required=False, widget=forms.HiddenInput())  # For reply functionality

class PropertyMessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Type your message about this property...'
            })
        }

class SavedPropertyForm(forms.ModelForm):
    class Meta:
        model = SavedProperty
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Add notes about this property...'
            })
        }

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400 pr-10',
            'placeholder': 'Current password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400 pr-10',
            'placeholder': 'New password'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400 pr-10',
            'placeholder': 'Confirm new password'
        })