from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import LandlordProfile, Property, RentalApplication
from .utils import send_notification


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        LandlordProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Ensure related profile is saved
    instance.landlordprofile.save()


@receiver(post_save, sender=Property)
def notify_property_status_change(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields') or []
    if not created and 'is_verified' in update_fields:
        status = "approved" if instance.is_verified else "rejected"
        send_notification(
            recipient=instance.landlord,
            title=f"Property Verification {status}",
            message=f"Your property '{instance.title}' has been {status} by the admin.",
            notification_type='property',
            related_url=instance.get_absolute_url()
        )


@receiver(post_save, sender=RentalApplication)
def notify_application_status_change(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields') or []
    if not created and 'status' in update_fields:
        send_notification(
            recipient=instance.applicant,
            title=f"Application {instance.status}",
            message=f"Your application for '{instance.property.title}' has been {instance.status}.",
            notification_type='application',
            related_url=instance.get_absolute_url()
        )


@receiver(post_save, sender=LandlordProfile)
def notify_landlord_verification(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields') or []
    if not created and 'is_verified' in update_fields:
        status = "verified" if instance.is_verified else "rejected"
        send_notification(
            recipient=instance.user,
            title=f"Account Verification {status}",
            message=f"Your landlord account has been {status} by the admin.",
            notification_type='verification',
            related_url=instance.get_absolute_url()
        )
