"""
seekers/models.py  –  MyHousePadi

FIXES vs original
─────────────────
[CRITICAL] CommunityPost had a bare `property` keyword on its own line
           between the `views` field and `reply_count()`. This is a
           syntax-level artifact that references the built-in `property`
           decorator – it's a no-op statement that would cause a confusing
           SyntaxWarning in Python 3.12+ and crash linters/type-checkers.
           Removed.

[CRITICAL] CommunityPost.reply_count() was defined as a plain method but
           used as if it were a property in templates (no parentheses).
           Decorated with @property so templates can use {{ post.reply_count }}.

[BUG]      SeekerProfile.preferred_locations stored JSON as a raw TextField
           with default='[]'. Any code that does `json.loads(profile.preferred_locations)`
           will crash on existing blank rows ('[]' is fine, but any manual
           admin edit could store bare text). Replaced with JSONField so
           Django handles serialisation.

[BUG]      SavedProperty used `property` as a field name which shadows
           Python's built-in. Renamed to `listing` but kept `property`
           as a @property alias so existing template code still works.
           NOTE: requires a migration rename.

[BUG]      CommunityPost.replies was referenced in PostDetailView but the
           related_name on CommunityReply is 'seekers_replies'. Added a
           @property `replies` alias so both names work.

[QUALITY]  Added Meta.indexes on commonly filtered/ordered fields.
[QUALITY]  Added get_absolute_url() to CommunityPost and CommunityReply.
[QUALITY]  SeekerProfile: added budget validation (min <= max).
"""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth import get_user_model
from django.urls import reverse
from landlords.models import Property

User = get_user_model()


class SeekerProfile(models.Model):
    PROPERTY_TYPE_CHOICES = [
        ('apartment', 'Apartment'),
        ('house',     'House'),
        ('condo',     'Condo'),
        ('studio',    'Studio'),
        ('shared',    'Shared Room'),
    ]

    GENDER_CHOICES = [
        ('male',   'Male'),
        ('female', 'Female'),
        ('other',  'Other'),
    ]

    EMPLOYMENT_CHOICES = [
        ('employed',      'Employed'),
        ('self_employed', 'Self-Employed'),
        ('student',       'Student'),
        ('unemployed',    'Unemployed'),
        ('retired',       'Retired'),
    ]

    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seeker_profile')
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    bio             = models.TextField(blank=True)
    phone_number    = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth   = models.DateField(null=True, blank=True)
    gender          = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, blank=True)
    current_address = models.TextField(blank=True)

    # Housing preferences
    budget_min = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    budget_max = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    preferred_property_type = models.CharField(
        max_length=20, choices=PROPERTY_TYPE_CHOICES, blank=True
    )
    # FIX: was TextField(default='[]') – JSONField handles serialisation properly
    preferred_locations = models.JSONField(default=list, blank=True)
    move_in_date = models.DateField(null=True, blank=True)

    # Verification
    verified            = models.BooleanField(default=False)
    phone_verified      = models.BooleanField(default=False)
    phone_verified_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['verified'],         name='seeker_verified_idx'),
            models.Index(fields=['employment_status'], name='seeker_employment_idx'),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}'s Seeker Profile"

    def clean(self):
        """Validate budget range."""
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValidationError(
                {'budget_max': 'Maximum budget must be greater than minimum budget.'}
            )

    def get_absolute_url(self):
        return reverse('seekers:profile')


class SavedProperty(models.Model):
    seeker   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_properties')
    # FIX: field renamed to avoid shadowing Python built-in `property`
    listing  = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='saved_by')
    notes    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seeker', 'listing')
        indexes = [
            models.Index(fields=['seeker', '-created_at'], name='saved_seeker_ts_idx'),
        ]

    def __str__(self):
        return f"{self.seeker.username} saved {self.listing.title}"

    # Backward-compat alias so existing code using `.property` still works
    @property
    def property(self):
        return self.listing


class CommunityPost(models.Model):
    author      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seekers_community_posts')
    title       = models.CharField(max_length=200)
    content     = models.TextField()
    location_tag = models.CharField(max_length=100, blank=True)
    views       = models.PositiveIntegerField(default=0)
    upvotes     = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'],           name='post_created_idx'),
            models.Index(fields=['author', '-created_at'], name='post_author_ts_idx'),
            models.Index(fields=['location_tag'],          name='post_location_idx'),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('seekers:community_detail', kwargs={'pk': self.pk})

    # FIX: was a plain method used as a property in templates – now a proper @property
    @property
    def reply_count(self):
        return self.seekers_replies.count()

    # Convenience alias for views that use `.replies`
    @property
    def replies(self):
        return self.seekers_replies


class CommunityReply(models.Model):
    post    = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='seekers_replies')
    author  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seekers_community_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['created_at']
        verbose_name_plural = 'Community Replies'
        indexes = [
            models.Index(fields=['post', 'created_at'], name='reply_post_ts_idx'),
        ]

    def __str__(self):
        return f"Reply by {self.author.username} on {self.post.title}"

    def get_absolute_url(self):
        return reverse('seekers:community_detail', kwargs={'pk': self.post.pk})