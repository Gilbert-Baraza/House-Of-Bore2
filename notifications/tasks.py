# notifications/tasks.py
"""
notifications/tasks.py
──────────────────────────────────────────────────────────────────────────────
Asynchronous Celery background workers responsible for reliable delivery
of transactional communications with exponential backoff retry support.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), max_retries=3, retry_backoff=True, retry_backoff_max=300)
def dispatch_notification_task(self, notification_id: int) -> dict:
    """
    Celery background task executing delivery of a pending `Notification` record.
    Implements automatic exponential backoff up to 3 retries upon encountering
    transient delivery or network errors.
    """
    from notifications.models import Notification, NotificationStatusChoices
    from notifications.services import send_notification

    logger.info(f"Task dispatch_notification_task started for Notification #{notification_id} (attempt {self.request.retries + 1})")

    try:
        notification = send_notification(notification_id)
        if notification.status == NotificationStatusChoices.SENT:
            logger.info(f"Notification #{notification_id} dispatched successfully.")
            return {"status": "sent", "notification_id": notification_id}
        elif notification.status == NotificationStatusChoices.FAILED:
            # If retry count is less than max_retries, raise an exception so autoretry_for triggers backoff
            if self.request.retries < self.max_retries:
                err_msg = f"Delivery failed: {notification.error_message}. Retrying via backoff..."
                logger.warning(f"Notification #{notification_id} failed: {err_msg}")
                raise RuntimeError(err_msg)
            else:
                logger.error(f"Notification #{notification_id} exhausted all retries ({self.max_retries}). Marked FAILED.")
                return {"status": "failed", "notification_id": notification_id, "error": notification.error_message}
        return {"status": notification.status, "notification_id": notification_id}
    except Exception as exc:
        logger.exception(f"Exception while executing dispatch_notification_task for Notification #{notification_id}: {exc}")
        # Re-raise so Celery autoretry_for handles backoff if under max_retries
        raise exc
