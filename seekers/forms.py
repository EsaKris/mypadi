"""
seekers/forms.py  –  MyHousePadi

FIXES vs original
─────────────────
[CRITICAL] MessageForm defined `reply_to` as a class-level attribute
           INSIDE the Meta class body: `reply_to = forms.IntegerField(...)`.
           Attributes defined inside Meta are NOT form fields – they are
           ignored by Django's form metaclass. reply_to was therefore
           silently dropped. Moved to the form class body.

[BUG]      SeekerProfileForm.save() called `user.save()` AND
           `profile.save()` separately, but `super().save()` (the ModelForm
           save) already called `profile.save()` via `commit=True` path in
           `super().form_valid()`. This caused a double save on the profile,
           wasting a DB write and potentially overwriting changes made by
           signals. Fixed: super().save(commit=False) + single explicit save.

[BUG]      SeekerProfileForm doubled up the phone_number field – it was
           both in Meta.fields and inherited from the form's __init__
           initial logic. The `initial` dict set phone_number from
           `user.phone_number` but the field was already in Meta.fields
           which binds to `profile.phone_number`. These can differ.
           Fixed: phone_number initial now comes from profile, not user.

[BUG]      CommunityReplyForm.content used a plain `forms.CharField`
           without a max_length, meaning extremely long posts could be
           submitted. Added max_length=2000.

[SECURITY] SeekerProfileForm.clean_profile_picture() read the file into
           `self.image_file` in memory using `picture.file.read()` without
           checking content_type server-side. HTML accept= is bypassable.
           Added MIME-type check.

[QUALITY]  PropertyMessageForm: added max_length=2000 on content to prevent
           excessively long messages.
"""

import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.core.files.base import ContentFile
from django.core.files.images import get_image_dimensions
from django.core.validators import FileExtensionValidator

from .models import CommunityPost, CommunityReply, SavedProperty, SeekerProfile
from core.models import Message

User = get_user_model()


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class SeekerProfileForm(forms.ModelForm):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
    )

    # User model fields surfaced on the form
    first_name = forms.CharField(max_length=30, required=True)
    last_name  = forms.CharField(max_length=30, required=True)
    email      = forms.EmailField(required=True)

    class Meta:
        model  = SeekerProfile
        fields = [
            'profile_picture',
            'first_name', 'last_name', 'email',
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
            'date_of_birth':    forms.DateInput(attrs={'type': 'date'}),
            'move_in_date':     forms.DateInput(attrs={'type': 'date'}),
            'bio':              forms.Textarea(attrs={'rows': 4}),
            'current_address':  forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate user fields from the related User instance
        if self.instance and self.instance.pk:
            user = self.instance.user
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial  = user.last_name
            self.fields['email'].initial      = user.email

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture and hasattr(picture, 'content_type'):
            allowed_types = {'image/jpeg', 'image/png'}
            if picture.content_type not in allowed_types:
                raise forms.ValidationError("Only JPEG and PNG images are allowed.")
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Image must be smaller than 5 MB.")
            try:
                width, height = get_image_dimensions(picture)
                if width > 2000 or height > 2000:
                    raise forms.ValidationError("Image must be 2000×2000 px or smaller.")
            except (AttributeError, TypeError):
                raise forms.ValidationError("Invalid image format.")
            # Buffer for save()
            picture.file.seek(0)
            self._image_bytes = picture.file.read()
            self._image_name  = picture.name
        return picture

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        # Ensure uniqueness excluding current user
        qs = User.objects.filter(email=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

    def save(self, commit=True):
        # FIX: use commit=False to avoid double-save
        profile = super().save(commit=False)

        if hasattr(self, '_image_bytes'):
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture.save(
                self._image_name,
                ContentFile(self._image_bytes),
                save=False,
            )

        if commit:
            # Save profile
            profile.save()
            # Save user fields
            user = profile.user
            user.first_name   = self.cleaned_data['first_name']
            user.last_name    = self.cleaned_data['last_name']
            user.email        = self.cleaned_data['email']
            user.phone_number = self.cleaned_data.get('phone_number') or ''
            user.save(update_fields=['first_name', 'last_name', 'email', 'phone_number'])

        return profile


# ---------------------------------------------------------------------------
# Community
# ---------------------------------------------------------------------------

class CommunityPostForm(forms.ModelForm):
    class Meta:
        model  = CommunityPost
        fields = ['title', 'content', 'location_tag']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 8,
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
            }),
            'location_tag': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
            }),
        }


class CommunityReplyForm(forms.Form):
    content = forms.CharField(
        max_length=2000,  # FIX: was unbounded
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg '
                     'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
            'placeholder': 'Write your reply here...',
        }),
        label='',
        required=True,
    )


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

class MessageForm(forms.ModelForm):
    # FIX: reply_to was nested inside Meta (ignored by Django) – moved here
    reply_to = forms.IntegerField(required=False, widget=forms.HiddenInput())

    class Meta:
        model  = Message
        fields = ['content', 'property']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'flex-1 px-4 py-2 rounded-l-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Type your message...',
            }),
            'property': forms.HiddenInput(),
        }


class PropertyMessageForm(forms.ModelForm):
    class Meta:
        model  = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Type your message about this property...',
            }),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if len(content) > 2000:
            raise forms.ValidationError("Message cannot exceed 2000 characters.")
        return content


# ---------------------------------------------------------------------------
# Saved properties
# ---------------------------------------------------------------------------

class SavedPropertyForm(forms.ModelForm):
    class Meta:
        model  = SavedProperty
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg border border-gray-300 '
                         'focus:ring-2 focus:ring-primary-400 focus:border-primary-400',
                'placeholder': 'Add notes about this property...',
            }),
        }


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (
            'w-full px-3 py-2 border border-gray-300 rounded-lg '
            'focus:ring-2 focus:ring-primary-400 focus:border-primary-400 pr-10'
        )
        self.fields['old_password'].widget.attrs.update({'class': css, 'placeholder': 'Current password'})
        self.fields['new_password1'].widget.attrs.update({'class': css, 'placeholder': 'New password'})
        self.fields['new_password2'].widget.attrs.update({'class': css, 'placeholder': 'Confirm new password'})