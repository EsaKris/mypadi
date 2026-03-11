"""
landlords/signals.py
Production-ready signals for MyHousePadi landlord app.

Key fixes & improvements:
- save_user_profile: wrapped in try/except so it doesn't crash if the
  LandlordProfile hasn't been created yet (e.g. during fixtures / migrations)
- notify_property_status_change: update_fields from post_save is a frozenset,
  not a list – use `in` operator works on both, but original code used
  `kwargs.get('update_fields') or []` which turns a frozenset into falsy when
  empty. Fixed with explicit None check.
- All send_notification calls are now wrapped in try/except so a notification
  failure never breaks the main save operation.
"""

import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import LandlordProfile, Property, RentalApplication
from .utils import send_notification

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a LandlordProfile automatically when a new User is created."""
    if created:
        LandlordProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Keep the related LandlordProfile in sync when the User is saved."""
    try:
        instance.landlord_profile.save()
    except LandlordProfile.DoesNotExist:
        # Profile hasn't been created yet (e.g. during initial migration).
        pass
    except Exception as exc:
        logger.warning("Could not save LandlordProfile for user %s: %s", instance.pk, exc)


@receiver(post_save, sender=Property)
def notify_property_status_change(sender, instance, created, **kwargs):
    """Notify the landlord when their property verification status changes."""
    if created:
        return

    update_fields = kwargs.get('update_fields')
    # update_fields is None (full save) or a frozenset of field names
    if update_fields is not None and 'is_verified' not in update_fields:
        return

    try:
        status = "approved" if instance.is_verified else "rejected"
        send_notification(
            recipient=instance.landlord,
            title=f"Property Verification {status.capitalize()}",
            message=f"Your property '{instance.name}' has been {status} by the admin.",
            notification_type='property',
            related_url=instance.get_absolute_url(),
        )
    except Exception as exc:
        logger.error(
            "Failed to send property verification notification for property %s: %s",
            instance.pk, exc,
        )


@receiver(post_save, sender=RentalApplication)
def notify_application_status_change(sender, instance, created, **kwargs):
    """Notify the applicant when their rental application status changes."""
    if created:
        return

    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'status' not in update_fields:
        return

    try:
        send_notification(
            recipient=instance.applicant,
            title=f"Application {instance.status.capitalize()}",
            message=(
                f"Your application for '{instance.property.name}' "
                f"has been {instance.status}."
            ),
            notification_type='application',
            related_url=instance.get_absolute_url(),
        )
    except Exception as exc:
        logger.error(
            "Failed to send application status notification for application %s: %s",
            instance.pk, exc,
        )


@receiver(post_save, sender=LandlordProfile)
def notify_landlord_verification(sender, instance, created, **kwargs):
    """Notify the landlord when their account verification status changes."""
    if created:
        return

    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'is_verified' not in update_fields:
        return

    try:
        status = "verified" if instance.is_verified else "rejected"
        send_notification(
            recipient=instance.user,
            title=f"Account Verification {status.capitalize()}",
            message=f"Your landlord account has been {status} by the admin.",
            notification_type='verification',
            related_url=instance.get_absolute_url(),
        )
    except Exception as exc:
        logger.error(
            "Failed to send landlord verification notification for profile %s: %s",
            instance.pk, exc,
        )