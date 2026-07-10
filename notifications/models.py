# notifications/models.py
"""
notifications/models.py
──────────────────────────────────────────────────────────────────────────────
Centralized, auditable data models tracking asynchronous customer notifications,
multi-channel delivery attempts, and immutable historical audit logs.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ChannelChoices(models.TextChoices):
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    WHATSAPP = "whatsapp", _("WhatsApp")


class EventChoices(models.TextChoices):
    ORDER_CREATED = "order_created", _("Order Created")
    PAYMENT_SUCCESSFUL = "payment_successful", _("Payment Successful")
    PAYMENT_FAILED = "payment_failed", _("Payment Failed")
    ORDER_PROCESSING = "order_processing", _("Order Processing")
    ORDER_SHIPPED = "order_shipped", _("Order Shipped")
    ORDER_DELIVERED = "order_delivered", _("Order Delivered")
    PASSWORD_RESET = "password_reset", _("Password Reset")
    ACCOUNT_REGISTERED = "account_registered", _("Account Registered")


class NotificationStatusChoices(models.TextChoices):
    PENDING = "pending", _("Pending")
    SENDING = "sending", _("Sending")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class DeliveryLogStatusChoices(models.TextChoices):
    SUCCESS = "success", _("Success")
    ERROR = "error", _("Error")
    RETRY = "retry", _("Retry")


class Notification(models.Model):
    """
    Represents an outbound transactional notification dispatched after a customer or order event.
    Stores complete historical context, target recipient, channel selection, and processing status.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Customer account associated with this notification (if registered)."
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Order associated with this notification (if applicable)."
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Payment record associated with this notification (if applicable)."
    )
    channel = models.CharField(
        max_length=20,
        choices=ChannelChoices.choices,
        default=ChannelChoices.EMAIL,
        help_text="Communication channel (Email, SMS, or WhatsApp)."
    )
    event = models.CharField(
        max_length=50,
        choices=EventChoices.choices,
        help_text="Business event triggering this notification."
    )
    recipient = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Target address (Email address or E.164 phone number)."
    )
    subject = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Notification subject or heading."
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationStatusChoices.choices,
        default=NotificationStatusChoices.PENDING,
        help_text="Current dispatch lifecycle state."
    )
    provider = models.CharField(
        max_length=50,
        blank=True,
        default="email_smtp",
        help_text="Adapter code used for delivery (e.g. email_smtp, sms_twilio, whatsapp_cloud)."
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Detailed error text if delivery attempt encountered an exception."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured template parameters or pre-rendered text/html content."
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts executed so far."
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the message was accepted by the external provider."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when notification record was created."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when notification record was last updated."
    )

    class Meta:
        verbose_name = "notification"
        verbose_name_plural = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["channel", "event"]),
        ]

    def __str__(self) -> str:
        return f"Notification #{self.pk} [{self.get_channel_display()} - {self.get_event_display()}] -> {self.recipient} ({self.status})"


class NotificationDeliveryLog(models.Model):
    """
    Immutable audit log recording every single delivery attempt, retry, or failure
    for a specific Notification record.
    """
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
        help_text="Parent notification record being dispatched."
    )
    channel = models.CharField(
        max_length=20,
        help_text="Channel over which delivery was attempted."
    )
    provider = models.CharField(
        max_length=50,
        help_text="Provider adapter code."
    )
    recipient = models.CharField(
        max_length=255,
        help_text="Recipient address during this attempt."
    )
    status = models.CharField(
        max_length=20,
        choices=DeliveryLogStatusChoices.choices,
        default=DeliveryLogStatusChoices.SUCCESS,
        help_text="Outcome of this specific delivery attempt."
    )
    error_details = models.TextField(
        blank=True,
        default="",
        help_text="Exception stack trace or provider rejection message."
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Retry attempt number when this log was created."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp of this delivery attempt."
    )

    class Meta:
        verbose_name = "notification delivery log"
        verbose_name_plural = "notification delivery logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["notification", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"DeliveryLog #{self.pk} [Notification #{self.notification_id} via {self.provider}] ({self.status})"
