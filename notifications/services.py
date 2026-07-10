# notifications/services.py
"""
notifications/services.py
──────────────────────────────────────────────────────────────────────────────
Centralized service architecture responsible for event publishing, message
formatting, asynchronous dispatching, delivery auditing, and retry recovery.
Never send direct notifications from views or models — all communication passes
through this strictly decoupled layer.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from typing import Any, Dict, Optional
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from notifications.models import (
    ChannelChoices,
    DeliveryLogStatusChoices,
    EventChoices,
    Notification,
    NotificationDeliveryLog,
    NotificationStatusChoices,
)
from notifications.providers import get_provider

logger = logging.getLogger(__name__)

# Default template mapping for Email channel events
EVENT_EMAIL_TEMPLATES = {
    EventChoices.ORDER_CREATED: {
        "html": "notifications/email/order_confirmation.html",
        "text": "notifications/email/order_confirmation.txt",
        "default_subject": "Order Confirmation - House of Bore",
    },
    EventChoices.PAYMENT_SUCCESSFUL: {
        "html": "notifications/email/payment_successful.html",
        "text": "notifications/email/payment_successful.txt",
        "default_subject": "Payment Receipt - House of Bore",
    },
    EventChoices.PAYMENT_FAILED: {
        "html": "notifications/email/payment_failed.html",
        "text": "notifications/email/payment_failed.txt",
        "default_subject": "Payment Authorization Failed - House of Bore",
    },
    EventChoices.ACCOUNT_REGISTERED: {
        "html": "notifications/email/welcome.html",
        "text": "notifications/email/welcome.txt",
        "default_subject": "Welcome to House of Bore Atelier",
    },
    EventChoices.PASSWORD_RESET: {
        "html": "notifications/email/password_reset.html",
        "text": "notifications/email/password_reset.txt",
        "default_subject": "Password Reset Request - House of Bore",
    },
}


def publish_event(
    event: str,
    recipient: str,
    channel: str = ChannelChoices.EMAIL,
    user: Optional[Any] = None,
    order: Optional[Any] = None,
    payment: Optional[Any] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    Publish a domain event, render corresponding channel templates (if Email),
    and asynchronously queue the notification for delivery.
    """
    if not recipient or not isinstance(recipient, str):
        raise ValueError("Valid recipient string is required to publish notification event.")

    context = {
        "user": user,
        "order": order,
        "payment": payment,
        **(extra_context or {}),
    }

    subject = ""
    text_content = ""
    html_content = None

    if channel == ChannelChoices.EMAIL and event in EVENT_EMAIL_TEMPLATES:
        template_info = EVENT_EMAIL_TEMPLATES[event]
        # Determine dynamic subject or fall back to default
        if order and event == EventChoices.ORDER_CREATED:
            subject = f"Order Confirmation - #{order.order_number}"
        elif payment and event == EventChoices.PAYMENT_SUCCESSFUL:
            subject = f"Payment Receipt - {payment.payment_reference}"
        elif order and event == EventChoices.PAYMENT_FAILED:
            subject = f"Payment Failed - Order #{order.order_number}"
        else:
            subject = template_info.get("default_subject", "House of Bore Notification")

        if "html" in template_info and "text" in template_info:
            try:
                html_content = render_to_string(template_info["html"], context)
                text_content = render_to_string(template_info["text"], context)
            except Exception as exc:
                logger.warning(f"Failed to render templates for event '{event}': {exc}. Using fallback text.")
                text_content = (extra_context or {}).get("text_content", f"House of Bore notification: {event}")
                html_content = None
    else:
        # Fallback formatting for SMS/WhatsApp or unmapped events
        subject = (extra_context or {}).get("subject", f"Notification for {event}")
        text_content = (extra_context or {}).get("text_content", f"House of Bore notification: {event}")
        html_content = (extra_context or {}).get("html_content")

    metadata = {
        "text_content": text_content,
        "html_content": html_content,
        "extra_context": {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in (extra_context or {}).items()},
    }

    return queue_notification(
        channel=channel,
        event=event,
        recipient=recipient.strip(),
        subject=subject,
        user=user,
        order=order,
        payment=payment,
        metadata=metadata,
    )


def queue_notification(
    channel: str,
    event: str,
    recipient: str,
    subject: str = "",
    user: Optional[Any] = None,
    order: Optional[Any] = None,
    payment: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    Create a `Notification` record in PENDING state and enqueue Celery dispatch task.
    Ensures zero blocking on web HTTP request threads.
    """
    from notifications.tasks import dispatch_notification_task

    notification = Notification.objects.create(
        user=user,
        order=order,
        payment=payment,
        channel=channel,
        event=event,
        recipient=recipient.strip(),
        subject=subject.strip(),
        status=NotificationStatusChoices.PENDING,
        metadata=metadata or {},
    )

    # Dispatch via Celery async worker
    try:
        dispatch_notification_task.delay(notification.pk)
    except Exception as exc:
        logger.error(f"Failed to enqueue Celery task for Notification #{notification.pk}: {exc}")
        # If Celery queue fails completely (e.g., Redis down), we leave status as PENDING or log error
        notification.error_message = f"Enqueue failure: {exc}"
        notification.save(update_fields=["error_message", "updated_at"])

    return notification


def log_delivery(
    notification: Notification,
    channel: str,
    provider: str,
    recipient: str,
    status: str,
    error_details: str = "",
) -> NotificationDeliveryLog:
    """
    Create an immutable audit entry inside `NotificationDeliveryLog` recording the attempt.
    """
    return NotificationDeliveryLog.objects.create(
        notification=notification,
        channel=channel,
        provider=provider,
        recipient=recipient,
        status=status,
        error_details=error_details,
        retry_count=notification.retry_count,
    )


def send_notification(notification_id: int) -> Notification:
    """
    Synchronous worker operation processing a `Notification` record.
    Locks row, validates status, delegates to `BaseNotificationProvider.send()`,
    records `NotificationDeliveryLog`, and updates lifecycle state.
    """
    with transaction.atomic():
        try:
            notification = Notification.objects.select_for_update().get(pk=notification_id)
        except Notification.DoesNotExist:
            logger.error(f"send_notification aborted: Notification #{notification_id} does not exist.")
            raise

        if notification.status in [NotificationStatusChoices.SENT, NotificationStatusChoices.CANCELLED]:
            logger.info(f"Notification #{notification_id} is already in state {notification.status}. Skipping dispatch.")
            return notification

        notification.status = NotificationStatusChoices.SENDING
        notification.save(update_fields=["status", "updated_at"])

    # Instantiate provider outside atomic lock to avoid holding database transactions during external HTTP/SMTP calls
    provider = get_provider(notification.channel)
    content = notification.metadata.get("text_content", "") if isinstance(notification.metadata, dict) else ""
    html_content = notification.metadata.get("html_content") if isinstance(notification.metadata, dict) else None

    result = provider.send(
        recipient=notification.recipient,
        subject=notification.subject,
        content=content,
        html_content=html_content,
        metadata=notification.metadata,
    )

    with transaction.atomic():
        notification = Notification.objects.select_for_update().get(pk=notification_id)
        notification.provider = result.get("provider_code", provider.provider_code)

        if result.get("success"):
            notification.status = NotificationStatusChoices.SENT
            notification.sent_at = timezone.now()
            notification.error_message = ""
            log_status = DeliveryLogStatusChoices.SUCCESS
            error_details = ""
        else:
            notification.status = NotificationStatusChoices.FAILED
            notification.error_message = result.get("error") or "Unknown delivery error reported by provider."
            notification.retry_count += 1
            log_status = DeliveryLogStatusChoices.ERROR
            error_details = notification.error_message

        notification.save(update_fields=["status", "sent_at", "provider", "error_message", "retry_count", "updated_at"])
        log_delivery(
            notification=notification,
            channel=notification.channel,
            provider=notification.provider,
            recipient=notification.recipient,
            status=log_status,
            error_details=error_details,
        )

    return notification


def send_email(
    recipient: str,
    subject: str,
    text_content: str,
    html_content: Optional[str] = None,
    user: Optional[Any] = None,
    order: Optional[Any] = None,
    payment: Optional[Any] = None,
    event: str = EventChoices.ORDER_CREATED,
) -> Notification:
    """
    Convenience method directly enqueueing an Email notification.
    """
    metadata = {
        "text_content": text_content,
        "html_content": html_content,
    }
    return queue_notification(
        channel=ChannelChoices.EMAIL,
        event=event,
        recipient=recipient,
        subject=subject,
        user=user,
        order=order,
        payment=payment,
        metadata=metadata,
    )


def send_sms(
    recipient: str,
    content: str,
    user: Optional[Any] = None,
    order: Optional[Any] = None,
    payment: Optional[Any] = None,
    event: str = EventChoices.ORDER_CREATED,
) -> Notification:
    """
    Convenience method directly enqueueing an SMS notification.
    """
    metadata = {"text_content": content}
    return queue_notification(
        channel=ChannelChoices.SMS,
        event=event,
        recipient=recipient,
        subject="",
        user=user,
        order=order,
        payment=payment,
        metadata=metadata,
    )


def send_whatsapp(
    recipient: str,
    content: str,
    template_name: Optional[str] = None,
    user: Optional[Any] = None,
    order: Optional[Any] = None,
    payment: Optional[Any] = None,
    event: str = EventChoices.ORDER_CREATED,
) -> Notification:
    """
    Convenience method directly enqueueing a WhatsApp notification.
    """
    metadata = {"text_content": content}
    if template_name:
        metadata["template_name"] = template_name
    return queue_notification(
        channel=ChannelChoices.WHATSAPP,
        event=event,
        recipient=recipient,
        subject="",
        user=user,
        order=order,
        payment=payment,
        metadata=metadata,
    )


def retry_notification(notification: Notification) -> Notification:
    """
    Manually or programmatically retry a previously failed `Notification`.
    Resets status to PENDING, logs a RETRY attempt, and enqueues Celery dispatch.
    """
    from notifications.tasks import dispatch_notification_task

    with transaction.atomic():
        if notification.status != NotificationStatusChoices.FAILED:
            raise ValueError(f"Only FAILED notifications can be retried. Current status is {notification.status}.")

        notification.status = NotificationStatusChoices.PENDING
        notification.save(update_fields=["status", "updated_at"])

        log_delivery(
            notification=notification,
            channel=notification.channel,
            provider=notification.provider,
            recipient=notification.recipient,
            status=DeliveryLogStatusChoices.RETRY,
            error_details=f"Manual/Programmatic retry initiated (Attempt #{notification.retry_count + 1}).",
        )

    dispatch_notification_task.delay(notification.pk)
    return notification
