# payments/models.py
"""
payments/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for production-grade payment processing and gateway auditing.
Stores auditable payment attempts (`Payment`) and incoming webhook deliveries
(`PaymentWebhookLog`) for strict idempotency, replay protection, and tracking.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PaymentStatus(models.TextChoices):
    """
    Lifecycle status of a payment transaction attempt.
    """
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    AUTHORIZED = "authorized", _("Authorized")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")
    EXPIRED = "expired", _("Expired")


class GatewayChoices(models.TextChoices):
    """
    Supported payment gateway provider codes.
    """
    PAYPAL = "paypal", _("PayPal")
    MPESA = "mpesa", _("M-Pesa (Daraja API)")
    STRIPE = "stripe", _("Stripe")
    MANUAL = "manual", _("Manual / Test")


class Payment(models.Model):
    """
    Permanent record of a payment attempt against an `Order`.
    Stores gateway responses and metadata for auditing without exposing or logging
    unencrypted sensitive customer credentials (e.g., PANs/CVVs).
    """
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
        help_text="Order associated with this payment attempt."
    )
    payment_reference = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique internal payment transaction identifier (e.g., PAY-20260710-000001)."
    )
    gateway = models.CharField(
        max_length=50,
        choices=GatewayChoices.choices,
        db_index=True,
        help_text="Payment provider gateway code."
    )
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Gateway-specific transaction, capture, or receipt ID (e.g., MpesaReceiptNumber, PayPal Capture ID)."
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Exact amount requested or paid in this transaction attempt."
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO currency code (e.g., USD, KES)."
    )
    status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
        help_text="Current monetary lifecycle status of this payment attempt."
    )
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw or structured gateway responses for auditing and troubleshooting."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Gateway-specific metadata (e.g., MerchantRequestID, CheckoutRequestID, phone_number)."
    )
    initiated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when payment processing was initiated with the gateway."
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when payment was confirmed, completed, or failed."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the payment attempt record was created."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the payment attempt record was last updated."
    )

    class Meta:
        verbose_name = "payment"
        verbose_name_plural = "payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"]),
            models.Index(fields=["gateway", "status"]),
            models.Index(fields=["transaction_id"]),
        ]

    def __str__(self) -> str:
        return f"Payment {self.payment_reference} ({self.get_gateway_display()}: {self.get_status_display()})"

    @property
    def is_completed(self) -> bool:
        """
        Returns True if this payment attempt is fully completed/captured.
        """
        return self.status == PaymentStatus.COMPLETED

    @property
    def is_pending_or_processing(self) -> bool:
        """
        Returns True if payment is currently pending initiation or in progress with the gateway.
        """
        return self.status in (PaymentStatus.PENDING, PaymentStatus.PROCESSING, PaymentStatus.AUTHORIZED)


class PaymentWebhookLog(models.Model):
    """
    Immutable audit log and deduplication record for incoming gateway webhooks.
    Enforces strict idempotency by preventing duplicate `event_id` deliveries from
    double-processing order updates or inventory deductions.
    """
    STATUS_CHOICES = [
        ("processed", _("Processed")),
        ("duplicate", _("Duplicate")),
        ("failed", _("Failed")),
        ("ignored", _("Ignored")),
    ]

    gateway = models.CharField(
        max_length=50,
        choices=GatewayChoices.choices,
        db_index=True,
        help_text="Gateway originating the webhook delivery."
    )
    event_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique event or transmission ID provided by the gateway for deduplication."
    )
    event_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Event type string (e.g., CHECKOUT.ORDER.APPROVED, stkCallback)."
    )
    payload = models.JSONField(
        default=dict,
        help_text="Full JSON payload received in the webhook body."
    )
    headers = models.JSONField(
        default=dict,
        help_text="Incoming HTTP headers for cryptographic signature verification audit."
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="processed",
        db_index=True,
        help_text="Processing status of this webhook delivery."
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if webhook verification or processing failed."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the webhook was received."
    )

    class Meta:
        verbose_name = "payment webhook log"
        verbose_name_plural = "payment webhook logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["gateway", "event_id"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Webhook #{self.pk} [{self.get_gateway_display()} - {self.event_type} - {self.event_id}] ({self.status})"
