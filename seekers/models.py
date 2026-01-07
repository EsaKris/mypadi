from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from landlords.models import Property, Conversation


User = get_user_model()

class SeekerProfile(models.Model):
    PROPERTY_TYPE_CHOICES = [
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('condo', 'Condo'),
        ('studio', 'Studio'),
        ('shared', 'Shared Room'),
    ]
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),

    ]
    
    EMPLOYMENT_CHOICES = [
        ('employed', 'Employed'),
        ('self_employed', 'Self-Employed'),
        ('student', 'Student'),
        ('unemployed', 'Unemployed'),
        ('retired', 'Retired'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seeker_profile')
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    bio = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, blank=True)
    current_address = models.TextField(blank=True)
    
    # Housing preferences
    budget_min = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    budget_max = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    preferred_property_type = models.CharField(
        max_length=20, 
        choices=PROPERTY_TYPE_CHOICES, 
        blank=True
    )
    preferred_locations = models.TextField(default='[]')
    move_in_date = models.DateField(null=True, blank=True)
    
    # Verification fields
    verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    phone_verified_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name()}'s Seeker Profile"

# Uncommented and fixed SavedProperty model
class SavedProperty(models.Model):
    seeker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_properties')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='saved_by')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seeker', 'property')

    def __str__(self):
        return f"{self.seeker.username} saved {self.property.title}"

# class Message(models.Model):
#     sender = models.ForeignKey(
#         User, on_delete=models.CASCADE, related_name='seeker_sent_messages'
#     )
#     recipient = models.ForeignKey(
#         User, on_delete=models.CASCADE, related_name='seeker_received_messages'
#     )
#     conversation = models.ForeignKey(
#         Conversation,
#         on_delete=models.CASCADE,
#         related_name='seeker_messages',  # 👈 unique related_name
#         null=True,
#         blank=True
#     )
#     property = models.ForeignKey(
#         'landlords.Property',
#         on_delete=models.CASCADE,
#         related_name='seeker_messages',
#         null=True,
#         blank=True
#     )
#     content = models.TextField()
#     read = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ["-updated_at"]

#     def __str__(self):
#         return f"Message from {self.sender} to {self.recipient} about {self.property}"

class CommunityPost(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seekers_community_posts')
    views = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=200)
    content = models.TextField()
    location_tag = models.CharField(max_length=100, blank=True)
    upvotes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    property
    def reply_count(self):
        return self.seekers_replies.count()

class CommunityReply(models.Model):
    post = models.ForeignKey('CommunityPost', on_delete=models.CASCADE, related_name='seekers_replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seekers_community_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Community Replies'

    def __str__(self):
        return f"Reply by {self.author.username} on {self.post.title}"