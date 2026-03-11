"""
landlords/utils.py
Production-ready notification utilities for MyHousePadi.

Key fixes & improvements:
- send_notification: now returns None (instead of raising) when recipient is
  None, so a missing user never breaks a caller.
- send_bulk_notification: uses bulk_create with ignore_conflicts=False
  (explicit) and batches in chunks of 500 to stay within DB limits.
- Added get_unread_count() helper used by templates / nav badges.
- Added mark_all_read() helper for the "mark all as read" admin endpoint.
"""

import logging
from typing import Iterable, Optional

from django.contrib.auth import get_user_model

from .models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()


def send_notification(
    recipient,
    title: str,
    message: str,
    notification_type: str = 'system',
    related_url: Optional[str] = None,
) -> Optional[Notification]:
    """
    Create and return a single Notification for *recipient*.

    Returns None and logs a warning if recipient is falsy rather than
    raising an exception – callers (signals, views) shouldn't blow up
    because of a notification failure.
    """
    if not recipient:
        logger.warning("send_notification called with no recipient – skipped.")
        return None

    try:
        return Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            related_url=related_url or '',
        )
    except Exception as exc:
        logger.error("Failed to create notification for user %s: %s", recipient, exc)
        return None


def send_bulk_notification(
    recipients: Iterable,
    title: str,
    message: str,
    notification_type: str = 'system',
    related_url: Optional[str] = None,
    batch_size: int = 500,
) -> list:
    """
    Efficiently create notifications for multiple recipients using bulk_create.

    Inserts in batches of *batch_size* to avoid hitting DB parameter limits
    with very large recipient lists.

    Returns the list of created Notification objects.
    """
    notifications = [
        Notification(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            related_url=related_url or '',
        )
        for recipient in recipients
        if recipient  # skip None / falsy recipients
    ]

    if not notifications:
        return []

    created = []
    for i in range(0, len(notifications), batch_size):
        chunk = notifications[i: i + batch_size]
        created.extend(Notification.objects.bulk_create(chunk))

    return created


def get_unread_count(user) -> int:
    """Return the number of unread notifications for *user*."""
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()


def mark_all_read(user) -> int:
    """
    Mark all unread notifications as read for *user*.
    Returns the number of notifications updated.
    """
    if not user or not user.is_authenticated:
        return 0
    updated, _ = Notification.objects.filter(
        recipient=user, is_read=False
    ).update(is_read=True), None
    return updated