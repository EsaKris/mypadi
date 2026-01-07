# landlords/utils.py or seekers/utils.py
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

def send_notification(recipient, title, message, notification_type='system', related_url=None):
    """
    Send a notification to a user
    """
    notification = Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        related_url=related_url
    )
    return notification

def send_bulk_notification(recipients, title, message, notification_type='system', related_url=None):
    """
    Send notification to multiple users
    """
    notifications = []
    for recipient in recipients:
        notifications.append(Notification(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            related_url=related_url
        ))
    return Notification.objects.bulk_create(notifications)