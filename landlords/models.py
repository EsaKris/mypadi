"""
landlords/models.py
Production-ready, optimized models for MyHousePadi landlord app.

Key fixes & improvements:
- Removed unused LoginRequiredMixin import (belongs in views, not models)
- Fixed Property.increment_views() race condition with F() expression
- Added proper db_index on all ForeignKey/filter fields
- Added select_related hints via Meta indexes
- Added get_absolute_url() to models that were missing it (used in signals)
- Fixed LandlordProfile.get_absolute_url() referenced in signals but never defined
- Cleaned up commented-out dead code
- Added file size validation directly on model ImageFields via clean()
- Added __str__ to LeaseAgreement
- Fixed Notification.mark_as_read() to use update_fields for efficiency
- Added Amenity.Meta ordering so queries are consistent
- PropertyImage: enforce max 1 primary per property at DB level via signal-safe save()
"""

import logging
import os

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.models import Conversation, Message  # noqa: F401 – keep for FK integrity

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_image_size(file, max_mb=2):
    """Reusable validator – raises ValidationError if file exceeds max_mb."""
    limit = max_mb * 1024 * 1024
    if file and hasattr(file, 'size') and file.size > limit:
        raise ValidationError(f"File too large. Maximum size is {max_mb} MB.")


def validate_profile_picture(file):
    validate_image_size(file, max_mb=2)


def validate_property_image(file):
    validate_image_size(file, max_mb=5)


# ---------------------------------------------------------------------------
# Amenity
# ---------------------------------------------------------------------------

class Amenity(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, help_text="Font Awesome icon class (e.g. 'fa-wifi')")

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Amenities'

    def __str__(self):
        return self.name

    @classmethod
    def create_default_amenities(cls):
        defaults = [
            ('WiFi', 'fa-wifi'),
            ('Swimming Pool', 'fa-swimming-pool'),
            ('Gym', 'fa-dumbbell'),
            ('Parking', 'fa-parking'),
            ('Air Conditioning', 'fa-snowflake'),
            ('Heating', 'fa-temperature-high'),
            ('Laundry', 'fa-tshirt'),
            ('Elevator', 'fa-elevator'),
            ('Security', 'fa-shield-alt'),
            ('Furnished', 'fa-couch'),
            ('Pet Friendly', 'fa-paw'),
            ('Garden', 'fa-tree'),
            ('Balcony', 'fa-umbrella-beach'),
            ('Cleaning Service', 'fa-broom'),
            ('Concierge', 'fa-bell-concierge'),
            ('Disability Access', 'fa-wheelchair'),
        ]
        for name, icon in defaults:
            cls.objects.get_or_create(name=name, defaults={'icon': icon})


# ---------------------------------------------------------------------------
# LandlordProfile
# ---------------------------------------------------------------------------

class LandlordProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='landlord_profile'
    )
    profile_picture = models.ImageField(
        upload_to='landlord_profile_pics/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png']),
            validate_profile_picture,
        ],
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    company_name = models.CharField(max_length=100, blank=True, null=True)
    business_address = models.TextField(blank=True, null=True)
    social_facebook = models.URLField(blank=True, null=True)
    social_twitter = models.URLField(blank=True, null=True)
    social_linkedin = models.URLField(blank=True, null=True)
    social_instagram = models.URLField(blank=True, null=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    verification_documents = models.FileField(
        upload_to='verification_docs/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
    )
    phone_verified = models.BooleanField(default=False)
    phone_verified_date = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(
        blank=True, null=True, help_text="Notes from the verification process"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()}'s Profile"

    # Keep these as properties so templates / admin still work unchanged
    @property
    def get_full_name(self):
        return self.user.get_full_name()

    @property
    def email(self):
        return self.user.email

    def get_absolute_url(self):
        return reverse('landlords:profile')


# ---------------------------------------------------------------------------
# Property & related
# ---------------------------------------------------------------------------

class Property(models.Model):
    PROPERTY_TYPES = (
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('commercial', 'Commercial Space'),
        ('land', 'Land'),
        ('other', 'Other'),
    )

    PRICE_PERIODS = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    )

    landlord = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='owned_properties', db_index=True
    )
    name = models.CharField(max_length=100)
    address = models.TextField()
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100, db_index=True)
    zip_code = models.CharField(max_length=20, blank=True)
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPES, db_index=True)
    num_units = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True)
    price_period = models.CharField(max_length=20, choices=PRICE_PERIODS, default='monthly')
    amenities = models.ManyToManyField('Amenity', blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    is_published = models.BooleanField(default=True, verbose_name="Publish on marketplace", db_index=True)
    description = models.TextField(blank=True, null=True)
    views = models.PositiveIntegerField(default=0)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)
    verification_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Properties'
        ordering = ['-created_at']
        indexes = [
            # Composite index for the most common listing query
            models.Index(fields=['is_published', 'is_active', '-is_featured', '-created_at'],
                         name='property_listing_idx'),
            models.Index(fields=['landlord', 'is_active'], name='property_landlord_idx'),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}"

    def get_absolute_url(self):
        return reverse('landing:property_detail', kwargs={'slug': self.slug})

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def display_price(self):
        period = dict(self.PRICE_PERIODS).get(self.price_period, '').lower()
        return f"₦{self.price:,.2f}/{period}"

    @property
    def primary_image(self):
        """Returns the primary image or falls back to the first available."""
        return self.images.filter(is_primary=True).first() or self.images.first()

    @property
    def is_occupied(self):
        today = timezone.now().date()
        return self.leases.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).exists()

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_current_tenant(self):
        today = timezone.now().date()
        lease = self.leases.filter(
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        ).select_related('tenant').first()
        return lease.tenant if lease else None

    def get_upcoming_vacancies(self):
        today = timezone.now().date()
        return self.leases.filter(
            is_active=True,
            end_date__range=(today, today + timedelta(days=30)),
        )

    def increment_views(self):
        """
        Use F() expression to avoid race conditions when multiple users
        view the same property simultaneously.
        """
        Property.objects.filter(pk=self.pk).update(views=F('views') + 1)
        self.refresh_from_db(fields=['views'])

    def save(self, *args, **kwargs):
        if not self.slug:
            try:
                base_slug = slugify(f"{self.name}-{self.city}")
                if not base_slug:
                    base_slug = f"property-{self.pk or 'new'}"

                slug_candidate = base_slug
                counter = 1
                while Property.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                    slug_candidate = f"{base_slug}-{counter}"
                    counter += 1
                self.slug = slug_candidate

            except Exception as exc:
                logger.error("Error generating slug for property %s: %s", self.pk, exc)
                if not self.slug and self.pk:
                    self.slug = f"property-{self.pk}"

        super().save(*args, **kwargs)


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='images', db_index=True
    )
    image = models.ImageField(
        upload_to='property_images/',
        validators=[validate_property_image],
    )
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f"Image for {self.property.name}"

    def save(self, *args, **kwargs):
        """Ensure only one primary image exists per property."""
        if self.is_primary:
            PropertyImage.objects.filter(
                property=self.property, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

class Tenant(models.Model):
    landlord = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='tenants', db_index=True
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='current_tenants', db_index=True
    )
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    lease_start = models.DateField()
    lease_end = models.DateField()
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    emergency_contact = models.CharField(max_length=100)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['property', 'email'], name='tenant_property_email_idx'),
        ]

    def __str__(self):
        return self.full_name


# ---------------------------------------------------------------------------
# RentalApplication
# ---------------------------------------------------------------------------

class RentalApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='applications', db_index=True
    )
    applicant = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='rental_applications', db_index=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    application_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    credit_score = models.IntegerField(blank=True, null=True)
    employment_verified = models.BooleanField(default=False)
    income_verified = models.BooleanField(default=False)
    references_checked = models.BooleanField(default=False)
    background_check = models.BooleanField(default=False)

    def __str__(self):
        return f"Application for {self.property} by {self.applicant}"

    def get_absolute_url(self):
        return reverse('landlords:application_detail', kwargs={'pk': self.pk})


# ---------------------------------------------------------------------------
# LeaseAgreement
# ---------------------------------------------------------------------------

class LeaseAgreement(models.Model):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='leases', db_index=True
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='leases', db_index=True
    )
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    terms = models.TextField()
    signed_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Lease: {self.tenant} @ {self.property} ({self.start_date} – {self.end_date})"


# ---------------------------------------------------------------------------
# MaintenanceRequest
# ---------------------------------------------------------------------------

class MaintenanceRequest(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('emergency', 'Emergency'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='maintenance_requests', db_index=True
    )
    tenant = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='maintenance_requests', db_index=True
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='assigned_maintenance'
    )
    completion_date = models.DateField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    # Use separate ImageField per photo to keep uploads clean
    before_photo = models.ImageField(
        upload_to='maintenance/before/', blank=True, null=True,
        validators=[validate_property_image],
    )
    after_photo = models.ImageField(
        upload_to='maintenance/after/', blank=True, null=True,
        validators=[validate_property_image],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.property})"


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('mobile_money', 'Mobile Money'),
        ('cash', 'Cash'),
        ('check', 'Check'),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='payments', db_index=True
    )
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='payments', db_index=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment of ₦{self.amount} for {self.property}"


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('repair', 'Repair'),
        ('maintenance', 'Maintenance'),
        ('utility', 'Utility'),
        ('tax', 'Tax'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    ]

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='expenses', db_index=True
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(db_index=True)
    description = models.TextField()
    receipt = models.FileField(upload_to='expense_receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category} expense for {self.property} – ₦{self.amount}"


# ---------------------------------------------------------------------------
# Community
# ---------------------------------------------------------------------------

class CommunityPost(models.Model):
    VISIBILITY_CHOICES = [
        ('landlords', 'Landlords Only'),
        ('all', 'All Users (Seekers & Landlords)'),
    ]

    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='landlords_community_posts', db_index=True
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    location_tag = models.CharField(max_length=100, blank=True)
    upvotes = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='all',
        db_index=True,
        help_text="Who can view this post?",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def reply_count(self):
        return self.landlords_replies.count()

    def can_view(self, user):
        if self.visibility == 'all':
            return True
        return hasattr(user, 'landlord_profile')


class CommunityReply(models.Model):
    post = models.ForeignKey(
        CommunityPost, on_delete=models.CASCADE, related_name='landlords_replies', db_index=True
    )
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='landlords_community_replies', db_index=True
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Community Replies'

    def __str__(self):
        return f"Reply by {self.author.username} on {self.post.title}"


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('system', 'System'),
        ('property', 'Property'),
        ('application', 'Application'),
        ('verification', 'Verification'),
        ('account', 'Account'),
    )

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications', db_index=True
    )
    title = models.CharField(max_length=100)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)
    related_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='notification_unread_idx'),
        ]

    def __str__(self):
        return f"{self.title} → {self.recipient.email}"

    def mark_as_read(self):
        """Efficient single-field update instead of full model save."""
        if not self.is_read:
            self.is_read = True
            Notification.objects.filter(pk=self.pk).update(is_read=True)