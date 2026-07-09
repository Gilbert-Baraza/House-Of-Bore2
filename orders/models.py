# orders/models.py
"""
orders/models.py
──────────────────────────────────────────────────────────────────────────────
Core data models for the Order Management System (OMS).
Stores permanent, immutable order records (`Order`) and exact line item snapshots
(`OrderItem`). Historical orders never depend on live `Product` pricing or attributes.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class OrderStatus(models.TextChoices):
    """
    Core lifecycle statuses for an order from creation through final delivery or failure.
    """
    PENDING = "pending", _("Pending")
    AWAITING_PAYMENT = "awaiting_payment", _("Awaiting Payment")
    PAID = "paid", _("Paid")
    PROCESSING = "processing", _("Processing")
    PACKED = "packed", _("Packed")
    SHIPPED = "shipped", _("Shipped")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    FAILED = "failed", _("Failed")


class PaymentStatus(models.TextChoices):
    """
    Monetary transaction status of the order.
    """
    AWAITING_PAYMENT = "awaiting_payment", _("Awaiting Payment")
    PAID = "paid", _("Paid")
    FAILED = "failed", _("Failed")
    REFUNDED = "refunded", _("Refunded")


class FulfillmentStatus(models.TextChoices):
    """
    Physical packing and shipping progress of the order items.
    """
    UNFULFILLED = "unfulfilled", _("Unfulfilled")
    PARTIAL = "partial", _("Partially Fulfilled")
    FULFILLED = "fulfilled", _("Fulfilled")


class Order(models.Model):
    """
    Permanent, immutable record of a customer purchase.
    Stores snapshotted addresses and financial breakdowns at creation time.
    """
    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Unique human-readable order number (e.g., HOB-20260709-000001)."
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Customer account associated with the order (null for guest orders)."
    )
    checkout_session = models.ForeignKey(
        "checkout.CheckoutSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Originating checkout session for auditability."
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text="Browser session key for guest order verification and access."
    )

    # Status Tracking
    status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
        help_text="Current lifecycle stage of the order."
    )
    payment_status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        default=PaymentStatus.AWAITING_PAYMENT,
        db_index=True,
        help_text="Current financial transaction state."
    )
    fulfillment_status = models.CharField(
        max_length=30,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
        db_index=True,
        help_text="Physical fulfillment state of order lines."
    )

    # Immutable Address Snapshots
    shipping_address_snapshot = models.JSONField(
        default=dict,
        help_text="Complete JSON snapshot of the shipping address at order time."
    )
    billing_address_snapshot = models.JSONField(
        default=dict,
        help_text="Complete JSON snapshot of the billing address at order time."
    )

    # Financial Summary
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Sum of line items before discounts, shipping, or taxes."
    )
    discount_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total promotional and coupon discounts applied."
    )
    shipping_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Calculated shipping cost."
    )
    tax_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Calculated tax amount."
    )
    grand_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Final payable total at creation."
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO currency code (e.g., USD)."
    )

    # Customer Metadata
    customer_notes = models.TextField(
        blank=True,
        default="",
        help_text="Special delivery instructions or notes provided by the customer."
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when the order was placed."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the order was last updated."
    )

    class Meta:
        verbose_name = "order"
        verbose_name_plural = "orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.order_number}"

    @property
    def item_count(self) -> int:
        """
        Returns the total number of physical units across all order items.
        """
        if hasattr(self, "_prefetched_objects_cache") and "items" in self._prefetched_objects_cache:
            return sum(item.quantity for item in self.items.all())
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def cached_items_count(self) -> int:
        """
        Returns the number of distinct line items without triggering N+1 queries when items are prefetched.
        """
        if hasattr(self, "_prefetched_objects_cache") and "items" in self._prefetched_objects_cache:
            return len(self.items.all())
        return self.items.count()

    @property
    def is_paid(self) -> bool:
        """
        Returns True if the order payment status is PAID.
        """
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_cancelled(self) -> bool:
        """
        Returns True if the order status is CANCELLED.
        """
        return self.status == OrderStatus.CANCELLED

    def can_be_cancelled(self) -> bool:
        """
        Returns True if the order has not yet been shipped, delivered, or cancelled.
        """
        return self.status in (OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID, OrderStatus.PROCESSING)


class OrderItem(models.Model):
    """
    Immutable line item snapshot inside an `Order`.
    Captures the exact title, SKU, option values, and unit price at order creation.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Parent order."
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        help_text="Optional reference to the live Product (nullable to allow product deletion without affecting order history)."
    )
    product_name = models.CharField(
        max_length=255,
        help_text="Snapshot of product title at time of purchase."
    )
    product_slug = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Snapshot of product slug for linking."
    )
    sku = models.CharField(
        max_length=100,
        help_text="Snapshot of specific variant or product SKU."
    )
    variant_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Snapshot of option combination string (e.g., 'Size: 40R / Color: Navy')."
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Quantity purchased."
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Locked price per unit at order creation."
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total line cost (`quantity * unit_price`)."
    )

    class Meta:
        verbose_name = "order item"
        verbose_name_plural = "order items"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity}x {self.product_name} ({self.sku}) [Order {self.order.order_number}]"

    def save(self, *args, **kwargs) -> None:
        """
        Ensure line total is always calculated precisely from quantity and unit price.
        """
        if self.unit_price is not None and self.quantity is not None:
            self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
        super().save(*args, **kwargs)
