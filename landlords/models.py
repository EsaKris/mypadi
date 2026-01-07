from django.db import models
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
from django.core.validators import FileExtensionValidator
from core.models import Conversation, Message

import logging


logger = logging.getLogger(__name__)
User = get_user_model()

class LandlordProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='landlord_profile')
    profile_picture = models.ImageField(
        upload_to='landlord_profile_pics/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    company_name = models.CharField(max_length=100, blank=True, null=True)
    business_address = models.TextField(blank=True, null=True)
    social_facebook = models.URLField(blank=True, null=True)
    social_twitter = models.URLField(blank=True, null=True)
    social_linkedin = models.URLField(blank=True, null=True)
    social_instagram = models.URLField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_documents = models.FileField(
        upload_to='verification_docs/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])]
    )
    phone_verified = models.BooleanField(default=False)
    phone_verified_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verification_notes = models.TextField(blank=True, null=True, help_text="Notes from the verification process")

    def __str__(self):
        return f"{self.user.get_full_name()}'s Profile"

    @property
    def get_full_name(self):
        return self.user.get_full_name()

    @property
    def email(self):
        return self.user.email

class Amenity(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, help_text="Font Awesome icon class (e.g. 'fa-wifi')")
    
    def __str__(self):
        return self.name

    @classmethod
    def create_default_amenities(cls):
        default_amenities = [
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
        for name, icon in default_amenities:
            cls.objects.get_or_create(name=name, icon=icon)

class PropertyImage(models.Model):
    property = models.ForeignKey('Property', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='property_images/')
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f"Image for {self.property.name}"
    


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
    
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_properties')
    name = models.CharField(max_length=100)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPES)
    num_units = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    price_period = models.CharField(max_length=20, choices=PRICE_PERIODS, default='monthly')
    amenities = models.ManyToManyField('Amenity', blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True, verbose_name="Publish on marketplace")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    views = models.PositiveIntegerField(default=0)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)
    verification_notes = models.TextField(blank=True, null=True, help_text="Notes from the verification process")

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.city}"

    @property
    def display_price(self):
        period = dict(self.PRICE_PERIODS).get(self.price_period, '').lower()
        return f"₦{self.price:,.2f}/{period}"

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()

    @property
    def is_occupied(self):
        now = timezone.now().date()
        return self.leases.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).exists()

    def get_current_tenant(self):
        if self.is_occupied:
            lease = self.leases.filter(
                is_active=True,
                start_date__lte=timezone.now().date(),
                end_date__gte=timezone.now().date()
            ).first()
            return lease.tenant if lease else None
        return None

    def get_upcoming_vacancies(self):
        return self.leases.filter(
            is_active=True,
            end_date__range=(
                timezone.now().date(),
                timezone.now().date() + timedelta(days=30)
        ))

    def increment_views(self):
        self.views += 1
        self.save(update_fields=['views'])
    
    def save(self, *args, **kwargs):
        """
        Override save method to automatically generate unique slugs
        """
        if not self.slug:
            try:
                base_slug = slugify(f"{self.name}-{self.city}")
                if not base_slug:  # Fallback if name and city are empty
                    base_slug = f"property-{self.id or 'new'}"
                
                self.slug = base_slug
                counter = 1
                
                # Ensure slug is unique
                while Property.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                    self.slug = f"{base_slug}-{counter}"
                    counter += 1
                    
            except Exception as e:
                logger.error(f"Error generating slug for property {self.id}: {e}")
                if not self.slug and self.id:
                    self.slug = f"property-{self.id}"
        
        super().save(*args, **kwargs)


class Tenant(models.Model):
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tenants')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='current_tenants')
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

    def __str__(self):
        return self.full_name

# # In your Conversation model
# class Conversation(models.Model):
#     participants = models.ManyToManyField(User)
#     property = models.ForeignKey(
#         Property,
#         on_delete=models.CASCADE,
#         related_name='conversations'
#     )
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ["-updated_at"]

#     def get_last_message(self):
#         # Try to get the last message from either app
#         from landlords.models import Message as LandlordMessage
#         from seekers.models import Message as SeekerMessage
        
#         landlord_msg = LandlordMessage.objects.filter(
#             conversation=self
#         ).order_by('-created_at').first()
        
#         seeker_msg = SeekerMessage.objects.filter(
#             conversation=self
#         ).order_by('-created_at').first()
        
#         # Return the most recent message
#         if landlord_msg and seeker_msg:
#             return landlord_msg if landlord_msg.created_at > seeker_msg.created_at else seeker_msg
#         return landlord_msg or seeker_msg

#     def get_messages(self):
#         # Get all messages from both apps
#         from landlords.models import Message as LandlordMessage
#         from seekers.models import Message as SeekerMessage
        
#         landlord_messages = LandlordMessage.objects.filter(conversation=self)
#         seeker_messages = SeekerMessage.objects.filter(conversation=self)
        
#         # Combine and order by creation time
#         all_messages = list(landlord_messages) + list(seeker_messages)
#         return sorted(all_messages, key=lambda x: x.created_at)

# # landlords/models.py

# class Message(models.Model):
#     sender = models.ForeignKey(
#         User, on_delete=models.CASCADE, related_name='landlord_sent_messages'
#     )
#     recipient = models.ForeignKey(
#         User, on_delete=models.CASCADE, related_name='landlord_received_messages'
#     )
#     conversation = models.ForeignKey(
#         Conversation,
#         on_delete=models.CASCADE,
#         related_name='landlord_messages',  # 👈 unique related_name
#         null=True,
#         blank=True
#     )
#     property = models.ForeignKey(
#         'landlords.Property',
#         on_delete=models.CASCADE,
#         related_name='landlord_messages',
#         null=True,
#         blank=True
#     )
#     content = models.TextField()
#     read = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['created_at']

#     def __str__(self):
#         return f"Message from {self.sender} to {self.recipient}"


class RentalApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='applications')
    applicant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rental_applications')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    application_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    credit_score = models.IntegerField(blank=True, null=True)
    employment_verified = models.BooleanField(default=False)
    income_verified = models.BooleanField(default=False)
    references_checked = models.BooleanField(default=False)
    background_check = models.BooleanField(default=False)

    def __str__(self):
        return f"Application for {self.property} by {self.applicant}"

class LeaseAgreement(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leases')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='leases')
    start_date = models.DateField()
    end_date = models.DateField()
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    terms = models.TextField()
    signed_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='maintenance_requests')
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='maintenance_requests')
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='assigned_maintenance')
    completion_date = models.DateField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    before_photos = models.ImageField(upload_to='maintenance/before/', blank=True, null=True)
    after_photos = models.ImageField(upload_to='maintenance/after/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('mobile_money', 'Mobile Money'),
        ('cash', 'Cash'),
        ('check', 'Check'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment of {self.amount} for {self.property}"

class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('repair', 'Repair'),
        ('maintenance', 'Maintenance'),
        ('utility', 'Utility'),
        ('tax', 'Tax'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    description = models.TextField()
    receipt = models.FileField(upload_to='expense_receipts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category} expense for {self.property} - {self.amount}"

class CommunityPost(models.Model):
    VISIBILITY_CHOICES = [
        ('landlords', 'Landlords Only'),
        ('all', 'All Users (Seekers & Landlords)'),
    ]
    
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='landlords_community_posts')
    views = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200)
    content = models.TextField()
    location_tag = models.CharField(max_length=100, blank=True)
    upvotes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='all',
        help_text="Who can view this post?"
    )

    def __str__(self):
        return self.title
    
    @property
    def reply_count(self):
        return self.landlords_replies.count()
    
    def can_view(self, user):
        """Check if a user can view this post"""
        if self.visibility == 'all':
            return True
        # For landlords-only posts, check if user is a landlord
        return hasattr(user, 'landlord_profile')

class CommunityReply(models.Model):
    post = models.ForeignKey('CommunityPost', on_delete=models.CASCADE, related_name='landlords_replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='landlords_community_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Community Replies'

    def __str__(self):
        return f"Reply by {self.author.username} on {self.post.title}"

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('system', 'System'),
        ('property', 'Property'),
        ('application', 'Application'),
        ('verification', 'Verification'),
        ('account', 'Account'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=100)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    related_url = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"{self.title} - {self.recipient.email}"

    def mark_as_read(self):
        self.is_read = True
        self.save()