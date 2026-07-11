# fulfillment/models.py
"""
fulfillment/models.py
──────────────────────────────────────────────────────────────────────────────
Core domain models for the Order Fulfillment & Shipping Operations engine.

Implements:
1. `FulfillmentOrder`: Primary operational tracking model linked 1-to-1 with `Order`.
   Tracks picking, packing, and shipping progression.
2. `FulfillmentItem`: Line-item verification for picking/packing with missing item tracking.
3. `Shipment`: Carrier integration foundation (courier, tracking numbers, dimensions/weight).
4. `FulfillmentEvent`: Immutable event log recording every workflow transition and action.
5. `ReturnExchangeRequest`: Foundation for returns, exchanges, and RMA inspections.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from orders.models import Order, OrderItem


class FulfillmentWorkflowStatus(models.TextChoices):
    """
    Granular state machine statuses for the post-payment order fulfillment lifecycle.
    """
    PENDING_PAYMENT = "pending_payment", _("Pending Payment")
    PAID = "paid", _("Paid — Awaiting Processing")
    PROCESSING = "processing", _("Processing")
    PICKING = "picking", _("Picking in Progress")
    PICKED = "picked", _("Picked")
    PACKING = "packing", _("Packing in Progress")
    PACKED = "packed", _("Packed")
    READY_FOR_DISPATCH = "ready_for_dispatch", _("Ready for Dispatch")
    SHIPPED = "shipped", _("Shipped")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for Delivery")
    DELIVERED = "delivered", _("Delivered")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    FAILED_DELIVERY = "failed_delivery", _("Failed Delivery")
    RETURNED = "returned", _("Returned")
    REFUNDED = "refunded", _("Refunded")
    EXCHANGED = "exchanged", _("Exchanged")


class ShipmentStatus(models.TextChoices):
    """
    Status tracking specifically for outbound packages/shipments.
    """
    PREPARING = "preparing", _("Preparing Package")
    LABEL_CREATED = "label_created", _("Shipping Label Created")
    PICKED_UP = "picked_up", _("Picked Up by Courier")
    IN_TRANSIT = "in_transit", _("In Transit")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for Delivery")
    DELIVERED = "delivered", _("Delivered")
    EXCEPTION = "exception", _("Delivery Exception / Delay")
    FAILED = "failed", _("Failed / Returned to Sender")


class FulfillmentPriority(models.IntegerChoices):
    """
    Operational priority levels for order queue sorting.
    """
    URGENT = 1, _("Urgent (Expedited / Overnight)")
    HIGH = 2, _("High Priority (2-Day / VIP)")
    NORMAL = 3, _("Normal Priority (Standard Ground)")
    LOW = 4, _("Low Priority")


class FulfillmentOrder(models.Model):
    """
    Central operational record directing warehouse picking, packing, and dispatch for an Order.
    Connected one-to-one with `orders.Order`.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="fulfillment_order",
        verbose_name=_("order"),
        help_text=_("Associated customer order.")
    )
    fulfillment_status = models.CharField(
        _("fulfillment status"),
        max_length=35,
        choices=FulfillmentWorkflowStatus.choices,
        default=FulfillmentWorkflowStatus.PENDING_PAYMENT,
        db_index=True,
        help_text=_("Current operational lifecycle state.")
    )
    priority = models.IntegerField(
        _("priority"),
        choices=FulfillmentPriority.choices,
        default=FulfillmentPriority.NORMAL,
        db_index=True,
        help_text=_("Operational priority determining queue ordering.")
    )
    warehouse = models.CharField(
        _("assigned warehouse"),
        max_length=100,
        default="Main Facility — Operations Hub #1",
        db_index=True,
        help_text=_("Designated warehouse or fulfillment center handling this order.")
    )

    # Staff Assignment Tracking
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_fulfillments",
        verbose_name=_("assigned fulfillment lead"),
        help_text=_("Primary staff member supervising this order's fulfillment.")
    )
    assigned_picker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="picked_fulfillments",
        verbose_name=_("assigned picker"),
        help_text=_("Warehouse associate tasked with picking items.")
    )
    assigned_packer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="packed_fulfillments",
        verbose_name=_("assigned packer"),
        help_text=_("Warehouse associate tasked with packing items.")
    )

    # Notes & Instructions
    notes = models.TextField(
        _("customer/shipping notes"),
        blank=True,
        default="",
        help_text=_("External notes or instructions relevant to shipping and handling.")
    )
    internal_notes = models.TextField(
        _("internal staff notes"),
        blank=True,
        default="",
        help_text=_("Private operational notes shared among warehouse staff.")
    )

    # Workflow Timestamps
    picking_started_at = models.DateTimeField(_("picking started at"), null=True, blank=True)
    picking_completed_at = models.DateTimeField(_("picking completed at"), null=True, blank=True)
    packing_started_at = models.DateTimeField(_("packing started at"), null=True, blank=True)
    packing_completed_at = models.DateTimeField(_("packing completed at"), null=True, blank=True)
    dispatched_at = models.DateTimeField(_("dispatched at"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("fulfillment order")
        verbose_name_plural = _("fulfillment orders")
        ordering = ["priority", "-created_at"]

    def __str__(self) -> str:
        return f"Fulfillment [{self.get_fulfillment_status_display()}] — {self.order.order_number}"

    @property
    def is_terminal_state(self) -> bool:
        """Return True if the fulfillment has reached a completed or cancelled state."""
        return self.fulfillment_status in {
            FulfillmentWorkflowStatus.DELIVERED,
            FulfillmentWorkflowStatus.COMPLETED,
            FulfillmentWorkflowStatus.CANCELLED,
            FulfillmentWorkflowStatus.REFUNDED,
            FulfillmentWorkflowStatus.EXCHANGED,
        }

    @property
    def picking_progress_percentage(self) -> int:
        """Calculate percentage of items successfully picked."""
        total = self.items.count()
        if not total:
            return 0
        picked = self.items.filter(is_picked=True).count()
        return int((picked / total) * 100)

    @property
    def packing_progress_percentage(self) -> int:
        """Calculate percentage of items successfully packed."""
        total = self.items.count()
        if not total:
            return 0
        packed = self.items.filter(is_packed=True).count()
        return int((packed / total) * 100)


class FulfillmentItem(models.Model):
    """
    Granular verification record for each line item within a FulfillmentOrder.
    Tracks item-level picking/packing status and isolates missing inventory issues.
    """
    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("fulfillment order")
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="fulfillment_items",
        verbose_name=_("order item")
    )
    quantity = models.PositiveIntegerField(_("target quantity"), default=1)
    picked_quantity = models.PositiveIntegerField(_("picked quantity"), default=0)
    missing_quantity = models.PositiveIntegerField(_("missing / unlocateable quantity"), default=0)
    is_picked = models.BooleanField(_("is picked"), default=False, db_index=True)
    is_packed = models.BooleanField(_("is packed"), default=False, db_index=True)
    notes = models.CharField(
        _("item notes / discrepancy info"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Notes regarding missing items, substitutions, or packaging requirements.")
    )

    class Meta:
        verbose_name = _("fulfillment item")
        verbose_name_plural = _("fulfillment items")
        unique_together = ("fulfillment_order", "order_item")
        ordering = ["order_item__id"]

    def __str__(self) -> str:
        return f"{self.order_item.product_name} ({self.picked_quantity}/{self.quantity})"


class Shipment(models.Model):
    """
    Outbound package tracking linking a FulfillmentOrder with a logistics courier.
    Includes foundation attributes for shipping labels, tracking numbers, and dimensions.
    """
    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name=_("fulfillment order")
    )
    courier = models.CharField(
        _("courier / carrier"),
        max_length=100,
        default="FedEx Ground",
        db_index=True,
        help_text=_("Designated logistics carrier (e.g., FedEx, UPS, USPS, DHL).")
    )
    tracking_number = models.CharField(
        _("tracking number"),
        max_length=120,
        unique=True,
        db_index=True,
        help_text=_("Carrier tracking barcode or reference number.")
    )
    shipping_method = models.CharField(
        _("shipping method"),
        max_length=100,
        default="Standard Ground",
        help_text=_("Service level chosen (e.g., Express Overnight, Ground, 2-Day Air).")
    )
    shipment_status = models.CharField(
        _("shipment status"),
        max_length=30,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.PREPARING,
        db_index=True
    )
    estimated_delivery = models.DateTimeField(_("estimated delivery date"), null=True, blank=True)
    actual_delivery = models.DateTimeField(_("actual delivery date"), null=True, blank=True)
    shipping_cost = models.DecimalField(
        _("actual carrier cost"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Actual billed shipping cost incurred from carrier.")
    )

    # Package Dimensions & Weight Foundation
    package_length = models.DecimalField(_("length (cm)"), max_digits=8, decimal_places=2, null=True, blank=True)
    package_width = models.DecimalField(_("width (cm)"), max_digits=8, decimal_places=2, null=True, blank=True)
    package_height = models.DecimalField(_("height (cm)"), max_digits=8, decimal_places=2, null=True, blank=True)
    package_weight = models.DecimalField(_("weight (kg)"), max_digits=8, decimal_places=3, null=True, blank=True)
    label_url = models.CharField(
        _("shipping label URL"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Foundation placeholder for generated shipping label PDF/ZPL link.")
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("shipment")
        verbose_name_plural = _("shipments")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Shipment [{self.courier}] — {self.tracking_number}"


class FulfillmentEvent(models.Model):
    """
    Immutable event log capturing every state transition, staff assignment, and action
    performed across the lifecycle of a FulfillmentOrder.
    """
    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("fulfillment order")
    )
    event_type = models.CharField(
        _("event type"),
        max_length=50,
        db_index=True,
        help_text=_("Category of action or transition (e.g., STATE_CHANGE, PICKING_COMPLETED).")
    )
    description = models.TextField(
        _("description"),
        help_text=_("Human-readable details regarding what changed.")
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fulfillment_events",
        verbose_name=_("performed by")
    )
    metadata = models.JSONField(
        _("event metadata"),
        default=dict,
        blank=True,
        help_text=_("Structured JSON context (e.g., old status vs new status, missing SKUs).")
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("fulfillment event")
        verbose_name_plural = _("fulfillment events")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.event_type} — {self.fulfillment_order.order.order_number}"


class ReturnRequestStatus(models.TextChoices):
    """
    Status workflow for return and exchange requests.
    """
    REQUESTED = "requested", _("Requested — Awaiting Approval")
    APPROVED = "approved", _("Approved — Awaiting Return Shipment")
    REJECTED = "rejected", _("Rejected")
    INSPECTING = "inspecting", _("Items Received — Under Inspection")
    COMPLETED = "completed", _("Completed — Restocked / Resolved")


class ReturnExchangeRequest(models.Model):
    """
    Foundation model managing customer initiated returns or exchanges,
    bridging fulfillment with warehouse RMA inspection and restock verification.
    """
    REQUEST_TYPES = [
        ("return", _("Return & Refund")),
        ("exchange", _("Item Exchange")),
    ]

    fulfillment_order = models.ForeignKey(
        FulfillmentOrder,
        on_delete=models.CASCADE,
        related_name="return_requests",
        verbose_name=_("fulfillment order")
    )
    request_type = models.CharField(
        _("request type"),
        max_length=20,
        choices=REQUEST_TYPES,
        default="return",
        db_index=True
    )
    status = models.CharField(
        _("status"),
        max_length=30,
        choices=ReturnRequestStatus.choices,
        default=ReturnRequestStatus.REQUESTED,
        db_index=True
    )
    reason = models.TextField(
        _("return/exchange reason"),
        help_text=_("Customer stated rationale for returning or exchanging items.")
    )
    customer_notes = models.TextField(_("customer notes"), blank=True, default="")
    staff_notes = models.TextField(_("staff inspection notes"), blank=True, default="")
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspected_returns",
        verbose_name=_("inspected by")
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("return/exchange request")
        verbose_name_plural = _("return/exchange requests")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"RMA [{self.get_request_type_display()}] — {self.fulfillment_order.order.order_number} ({self.get_status_display()})"
