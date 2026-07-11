# fulfillment/services.py
"""
fulfillment/services.py
──────────────────────────────────────────────────────────────────────────────
Core service layer encapsulating all post-payment order fulfillment workflows,
state transitions, staff assignments, picking/packing verifications, carrier
shipment creation, and audit trail logging.

Implements controlled state machine transitions ensuring exact concurrency
safety (`select_for_update`) and coupling with `orders.services.transition_order_status`
and `inventory.services` stock mutations.
──────────────────────────────────────────────────────────────────────────────
"""

import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from orders.models import Order, OrderStatus
from orders.services import transition_order_status
from .models import (
    FulfillmentEvent,
    FulfillmentItem,
    FulfillmentOrder,
    FulfillmentPriority,
    FulfillmentWorkflowStatus,
    ReturnExchangeRequest,
    ReturnRequestStatus,
    Shipment,
    ShipmentStatus,
)

User = get_user_model()

# Valid State Transition Graph
VALID_TRANSITIONS: Dict[str, set] = {
    FulfillmentWorkflowStatus.PENDING_PAYMENT: {
        FulfillmentWorkflowStatus.PAID,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PAID: {
        FulfillmentWorkflowStatus.PROCESSING,
        FulfillmentWorkflowStatus.PICKING,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PROCESSING: {
        FulfillmentWorkflowStatus.PICKING,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PICKING: {
        FulfillmentWorkflowStatus.PICKED,
        FulfillmentWorkflowStatus.PROCESSING,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PICKED: {
        FulfillmentWorkflowStatus.PACKING,
        FulfillmentWorkflowStatus.PICKING,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PACKING: {
        FulfillmentWorkflowStatus.PACKED,
        FulfillmentWorkflowStatus.READY_FOR_DISPATCH,
        FulfillmentWorkflowStatus.PICKED,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.PACKED: {
        FulfillmentWorkflowStatus.READY_FOR_DISPATCH,
        FulfillmentWorkflowStatus.SHIPPED,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.READY_FOR_DISPATCH: {
        FulfillmentWorkflowStatus.SHIPPED,
        FulfillmentWorkflowStatus.PACKED,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.SHIPPED: {
        FulfillmentWorkflowStatus.OUT_FOR_DELIVERY,
        FulfillmentWorkflowStatus.DELIVERED,
        FulfillmentWorkflowStatus.FAILED_DELIVERY,
        FulfillmentWorkflowStatus.RETURNED,
    },
    FulfillmentWorkflowStatus.OUT_FOR_DELIVERY: {
        FulfillmentWorkflowStatus.DELIVERED,
        FulfillmentWorkflowStatus.FAILED_DELIVERY,
    },
    FulfillmentWorkflowStatus.FAILED_DELIVERY: {
        FulfillmentWorkflowStatus.SHIPPED,
        FulfillmentWorkflowStatus.OUT_FOR_DELIVERY,
        FulfillmentWorkflowStatus.RETURNED,
        FulfillmentWorkflowStatus.CANCELLED,
    },
    FulfillmentWorkflowStatus.DELIVERED: {
        FulfillmentWorkflowStatus.COMPLETED,
        FulfillmentWorkflowStatus.RETURNED,
        FulfillmentWorkflowStatus.EXCHANGED,
        FulfillmentWorkflowStatus.REFUNDED,
    },
    FulfillmentWorkflowStatus.COMPLETED: {
        FulfillmentWorkflowStatus.RETURNED,
        FulfillmentWorkflowStatus.EXCHANGED,
        FulfillmentWorkflowStatus.REFUNDED,
    },
    FulfillmentWorkflowStatus.CANCELLED: set(),
    FulfillmentWorkflowStatus.RETURNED: {
        FulfillmentWorkflowStatus.REFUNDED,
        FulfillmentWorkflowStatus.EXCHANGED,
    },
    FulfillmentWorkflowStatus.REFUNDED: set(),
    FulfillmentWorkflowStatus.EXCHANGED: set(),
}


def log_fulfillment_event(
    fulfillment_order: FulfillmentOrder,
    event_type: str,
    description: str,
    performed_by: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> FulfillmentEvent:
    """
    Append an immutable event entry to the fulfillment order's operational audit log.
    """
    if performed_by and not performed_by.is_authenticated:
        performed_by = None

    return FulfillmentEvent.objects.create(
        fulfillment_order=fulfillment_order,
        event_type=event_type,
        description=description,
        performed_by=performed_by,
        metadata=metadata or {},
    )


def _validate_state_transition(current_status: str, target_status: str) -> None:
    if current_status == target_status:
        return
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ValidationError(
            f"Invalid fulfillment state transition from '{current_status}' to '{target_status}'."
        )


@transaction.atomic
def create_fulfillment_order(
    order: Order,
    priority: int = FulfillmentPriority.NORMAL,
    warehouse: str = "Main Facility — Operations Hub #1",
    notes: str = "",
    performed_by: Optional[Any] = None,
) -> FulfillmentOrder:
    """
    Initialize a new FulfillmentOrder for a customer Order along with exact line item
    verification records (`FulfillmentItem`).
    """
    if hasattr(order, "fulfillment_order") and order.fulfillment_order:
        fo = order.fulfillment_order
        updated = False
        if priority != FulfillmentPriority.NORMAL and fo.priority != priority:
            fo.priority = priority
            updated = True
        if warehouse != "Main Facility — Operations Hub #1" and fo.warehouse != warehouse:
            fo.warehouse = warehouse
            updated = True
        if notes and fo.notes != notes:
            fo.notes = notes
            updated = True
        if updated:
            fo.save(update_fields=["priority", "warehouse", "notes", "updated_at"])

        # Sync any order items that were added after the initial fulfillment order creation
        for item in order.items.all():
            if not fo.items.filter(order_item=item).exists():
                FulfillmentItem.objects.create(
                    fulfillment_order=fo,
                    order_item=item,
                    quantity=item.quantity,
                    picked_quantity=0,
                    missing_quantity=0,
                    is_picked=False,
                    is_packed=False,
                )
        return fo

    initial_status = (
        FulfillmentWorkflowStatus.PAID
        if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING}
        else FulfillmentWorkflowStatus.PENDING_PAYMENT
    )

    fulfillment = FulfillmentOrder.objects.create(
        order=order,
        fulfillment_status=initial_status,
        priority=priority,
        warehouse=warehouse,
        notes=notes or order.customer_notes,
    )

    # Populate item verification records from order line items
    for item in order.items.all():
        FulfillmentItem.objects.create(
            fulfillment_order=fulfillment,
            order_item=item,
            quantity=item.quantity,
            picked_quantity=0,
            missing_quantity=0,
            is_picked=False,
            is_packed=False,
        )

    log_fulfillment_event(
        fulfillment_order=fulfillment,
        event_type="INITIALIZED",
        description=f"Fulfillment workflow initialized in status: {fulfillment.get_fulfillment_status_display()}",
        performed_by=performed_by,
        metadata={"initial_status": initial_status, "priority": priority},
    )

    return fulfillment


@transaction.atomic
def assign_order(
    fulfillment_order: FulfillmentOrder,
    staff_user: Optional[Any],
    role: str = "general",
    performed_by: Optional[Any] = None,
) -> FulfillmentOrder:
    """
    Assign staff leads, pickers, or packers to oversee this order's processing.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)

    if role == "picker":
        fo.assigned_picker = staff_user
        desc = f"Assigned picker: {staff_user.email if staff_user else 'Unassigned'}"
    elif role == "packer":
        fo.assigned_packer = staff_user
        desc = f"Assigned packer: {staff_user.email if staff_user else 'Unassigned'}"
    else:
        fo.assigned_staff = staff_user
        desc = f"Assigned fulfillment lead: {staff_user.email if staff_user else 'Unassigned'}"

    fo.save(update_fields=["assigned_staff", "assigned_picker", "assigned_packer", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="STAFF_ASSIGNED",
        description=desc,
        performed_by=performed_by,
        metadata={"role": role, "assigned_to": getattr(staff_user, "email", None)},
    )

    return fo


@transaction.atomic
def start_picking(
    fulfillment_order: FulfillmentOrder,
    picker: Optional[Any] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Transition fulfillment order to 'Picking in Progress' and stamp start time.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.PICKING)

    fo.fulfillment_status = FulfillmentWorkflowStatus.PICKING
    if picker:
        fo.assigned_picker = picker
    elif performed_by and not fo.assigned_picker:
        fo.assigned_picker = performed_by

    if not fo.picking_started_at:
        fo.picking_started_at = timezone.now()

    if notes:
        fo.internal_notes = f"{fo.internal_notes}\n[Picking Started] {notes}".strip()

    fo.save(update_fields=["fulfillment_status", "assigned_picker", "picking_started_at", "internal_notes", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="PICKING_STARTED",
        description=f"Picking process initiated by {getattr(fo.assigned_picker, 'email', 'Staff')}.",
        performed_by=performed_by or fo.assigned_picker,
    )

    return fo


@transaction.atomic
def complete_picking(
    fulfillment_order: FulfillmentOrder,
    picked_items_data: Optional[List[Dict[str, Any]]] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Verify and record picked quantities against order line items.
    If missing quantities are discovered, flags discrepancies and transitions to 'Picked'.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.PICKED)

    has_missing = False
    if picked_items_data:
        for item_data in picked_items_data:
            item_id = item_data.get("item_id")
            if not item_id:
                continue
            item = fo.items.filter(pk=item_id).first()
            if not item:
                continue
            picked_qty = int(item_data.get("picked_quantity", item.quantity))
            missing_qty = int(item_data.get("missing_quantity", max(0, item.quantity - picked_qty)))
            item_notes = item_data.get("notes", "")

            item.picked_quantity = picked_qty
            item.missing_quantity = missing_qty
            item.is_picked = (picked_qty >= item.quantity)
            if item_notes:
                item.notes = item_notes
            if missing_qty > 0:
                has_missing = True
            item.save()
    else:
        # Default all items to fully picked
        fo.items.update(is_picked=True)
        for item in fo.items.all():
            item.picked_quantity = item.quantity
            item.missing_quantity = 0
            item.save()

    fo.fulfillment_status = FulfillmentWorkflowStatus.PICKED
    fo.picking_completed_at = timezone.now()
    if notes or has_missing:
        msg = notes or ("Discrepancy noted during picking." if has_missing else "All items successfully picked.")
        fo.internal_notes = f"{fo.internal_notes}\n[Picking Completed] {msg}".strip()

    fo.save(update_fields=["fulfillment_status", "picking_completed_at", "internal_notes", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="PICKING_COMPLETED",
        description="Picking verification completed" + (" with missing items!" if has_missing else " cleanly."),
        performed_by=performed_by or fo.assigned_picker,
        metadata={"has_missing_items": has_missing},
    )

    return fo


@transaction.atomic
def start_packing(
    fulfillment_order: FulfillmentOrder,
    packer: Optional[Any] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Transition order to 'Packing in Progress' and stamp start time.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.PACKING)

    fo.fulfillment_status = FulfillmentWorkflowStatus.PACKING
    if packer:
        fo.assigned_packer = packer
    elif performed_by and not fo.assigned_packer:
        fo.assigned_packer = performed_by

    if not fo.packing_started_at:
        fo.packing_started_at = timezone.now()

    if notes:
        fo.internal_notes = f"{fo.internal_notes}\n[Packing Started] {notes}".strip()

    fo.save(update_fields=["fulfillment_status", "assigned_packer", "packing_started_at", "internal_notes", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="PACKING_STARTED",
        description=f"Packing verification initiated by {getattr(fo.assigned_packer, 'email', 'Staff')}.",
        performed_by=performed_by or fo.assigned_packer,
    )

    return fo


@transaction.atomic
def complete_packing(
    fulfillment_order: FulfillmentOrder,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Confirm all items packed and transition order to 'Packed' / 'Ready for Dispatch'.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.PACKED)

    fo.items.update(is_packed=True)
    fo.fulfillment_status = FulfillmentWorkflowStatus.PACKED
    fo.packing_completed_at = timezone.now()

    if notes:
        fo.internal_notes = f"{fo.internal_notes}\n[Packing Completed] {notes}".strip()

    fo.save(update_fields=["fulfillment_status", "packing_completed_at", "internal_notes", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="PACKING_COMPLETED",
        description="All items verified and packed into shipment boxes.",
        performed_by=performed_by or fo.assigned_packer,
    )

    return fo


@transaction.atomic
def create_shipment(
    fulfillment_order: FulfillmentOrder,
    courier: str = "FedEx Ground",
    shipping_method: str = "Standard Ground",
    tracking_number: str = "",
    estimated_delivery: Optional[Any] = None,
    shipping_cost: Decimal = Decimal("0.00"),
    dimensions: Optional[Dict[str, Any]] = None,
    performed_by: Optional[Any] = None,
) -> Shipment:
    """
    Generate or link a logistics carrier Shipment to the FulfillmentOrder.
    Protects against duplicate shipment creation unless explicitly replacing.
    Automatically transitions order status to 'Ready for Dispatch'.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)

    # Check for existing active shipment
    existing = fo.shipments.filter(shipment_status__in=[
        ShipmentStatus.PREPARING, ShipmentStatus.LABEL_CREATED, ShipmentStatus.PICKED_UP, ShipmentStatus.IN_TRANSIT
    ]).first()
    if existing and tracking_number and existing.tracking_number == tracking_number:
        return existing

    if not tracking_number:
        # Generate internal tracking code if courier interface has not supplied one
        date_str = timezone.now().strftime("%Y%m%d")
        rand_suffix = uuid.uuid4().hex[:6].upper()
        tracking_number = f"HOB-TRK-{date_str}-{rand_suffix}"

    dims = dimensions or {}
    shipment = Shipment.objects.create(
        fulfillment_order=fo,
        courier=courier,
        tracking_number=tracking_number,
        shipping_method=shipping_method,
        estimated_delivery=estimated_delivery,
        shipping_cost=shipping_cost,
        shipment_status=ShipmentStatus.LABEL_CREATED,
        package_length=dims.get("length"),
        package_width=dims.get("width"),
        package_height=dims.get("height"),
        package_weight=dims.get("weight"),
        label_url=dims.get("label_url", ""),
    )

    # Transition fulfillment to Ready for Dispatch if not already past it
    if fo.fulfillment_status in {FulfillmentWorkflowStatus.PACKING, FulfillmentWorkflowStatus.PACKED}:
        fo.fulfillment_status = FulfillmentWorkflowStatus.READY_FOR_DISPATCH
        fo.save(update_fields=["fulfillment_status", "updated_at"])

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="SHIPMENT_CREATED",
        description=f"Shipment label generated with {courier} (Tracking: {tracking_number}).",
        performed_by=performed_by,
        metadata={"courier": courier, "tracking_number": tracking_number, "shipment_id": shipment.pk},
    )

    return shipment


@transaction.atomic
def dispatch_order(
    fulfillment_order: FulfillmentOrder,
    shipment: Optional[Shipment] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Confirm courier pickup/dispatch. Transitions both FulfillmentOrder (`SHIPPED`)
    and the underlying Order (`OrderStatus.SHIPPED`), which atomically fulfills reserved inventory stock.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.SHIPPED)

    fo.fulfillment_status = FulfillmentWorkflowStatus.SHIPPED
    fo.dispatched_at = timezone.now()
    if notes:
        fo.internal_notes = f"{fo.internal_notes}\n[Dispatched] {notes}".strip()
    fo.save(update_fields=["fulfillment_status", "dispatched_at", "internal_notes", "updated_at"])

    # Update attached shipment status
    target_shipment = shipment or fo.shipments.first()
    if target_shipment:
        target_shipment.shipment_status = ShipmentStatus.IN_TRANSIT
        target_shipment.save(update_fields=["shipment_status", "updated_at"])

    # Bridge status transition with OMS order engine & inventory fulfillment
    if fo.order.status != OrderStatus.SHIPPED:
        transition_order_status(fo.order, OrderStatus.SHIPPED, note=notes or "Order dispatched via courier.")

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="DISPATCHED",
        description="Package handed off to courier and marked SHIPPED.",
        performed_by=performed_by,
        metadata={"tracking_number": getattr(target_shipment, "tracking_number", None)},
    )

    return fo


@transaction.atomic
def confirm_delivery(
    fulfillment_order: FulfillmentOrder,
    shipment: Optional[Shipment] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> FulfillmentOrder:
    """
    Confirm final delivery to customer. Transitions FulfillmentOrder (`DELIVERED`/`COMPLETED`)
    and Order (`OrderStatus.DELIVERED`).
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    _validate_state_transition(fo.fulfillment_status, FulfillmentWorkflowStatus.DELIVERED)

    fo.fulfillment_status = FulfillmentWorkflowStatus.DELIVERED
    fo.delivered_at = timezone.now()
    if notes:
        fo.internal_notes = f"{fo.internal_notes}\n[Delivered] {notes}".strip()
    fo.save(update_fields=["fulfillment_status", "delivered_at", "internal_notes", "updated_at"])

    target_shipment = shipment or fo.shipments.first()
    if target_shipment:
        target_shipment.shipment_status = ShipmentStatus.DELIVERED
        target_shipment.actual_delivery = timezone.now()
        target_shipment.save(update_fields=["shipment_status", "actual_delivery", "updated_at"])

    if fo.order.status != OrderStatus.DELIVERED:
        transition_order_status(fo.order, OrderStatus.DELIVERED, note=notes or "Confirmed delivered to recipient.")

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="DELIVERED",
        description="Package confirmed delivered to customer address.",
        performed_by=performed_by,
        metadata={"delivery_timestamp": fo.delivered_at.isoformat() if fo.delivered_at else None},
    )

    return fo


@transaction.atomic
def initiate_return(
    fulfillment_order: FulfillmentOrder,
    reason: str,
    items_data: Optional[List[Dict[str, Any]]] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> ReturnExchangeRequest:
    """
    Initiate a return request against a delivered or shipped order.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)

    req = ReturnExchangeRequest.objects.create(
        fulfillment_order=fo,
        request_type="return",
        status=ReturnRequestStatus.REQUESTED,
        reason=reason,
        customer_notes=notes,
    )

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="RETURN_INITIATED",
        description=f"Return request initiated for reason: {reason}",
        performed_by=performed_by,
        metadata={"return_request_id": req.pk, "reason": reason},
    )

    return req


@transaction.atomic
def initiate_exchange(
    fulfillment_order: FulfillmentOrder,
    reason: str,
    items_data: Optional[List[Dict[str, Any]]] = None,
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> ReturnExchangeRequest:
    """
    Initiate an item exchange request.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)

    req = ReturnExchangeRequest.objects.create(
        fulfillment_order=fo,
        request_type="exchange",
        status=ReturnRequestStatus.REQUESTED,
        reason=reason,
        customer_notes=notes,
    )

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="EXCHANGE_INITIATED",
        description=f"Exchange request initiated for reason: {reason}",
        performed_by=performed_by,
        metadata={"exchange_request_id": req.pk, "reason": reason},
    )

    return req


@transaction.atomic
def process_return_inspection(
    return_request: ReturnExchangeRequest,
    action: str,  # "approve", "reject", "inspect", "restock"
    performed_by: Optional[Any] = None,
    notes: str = "",
) -> ReturnExchangeRequest:
    """
    Inspect or approve a return/exchange. When action is 'restock', bridges with
    `inventory.services.process_return` to reintegrate returned items into sellable stock.
    """
    req = ReturnExchangeRequest.objects.select_for_update().get(pk=return_request.pk)
    fo = req.fulfillment_order

    if action == "approve":
        req.status = ReturnRequestStatus.APPROVED
    elif action == "reject":
        req.status = ReturnRequestStatus.REJECTED
    elif action == "inspect":
        req.status = ReturnRequestStatus.INSPECTING
    elif action == "restock":
        req.status = ReturnRequestStatus.COMPLETED
        fo.fulfillment_status = FulfillmentWorkflowStatus.RETURNED
        fo.save(update_fields=["fulfillment_status", "updated_at"])

        # Reintegrate physical items into stock ledger via inventory service
        from inventory.models import Inventory
        from inventory.services import process_return as inv_process_return
        for f_item in fo.items.all():
            if f_item.picked_quantity > 0:
                variant = getattr(f_item.order_item.product, "variants", None)
                # Check for inventory model linked to variant or product
                inv = Inventory.objects.filter(product_variant__sku=f_item.order_item.sku).first()
                if inv:
                    inv_process_return(
                        inventory=inv,
                        quantity=f_item.picked_quantity,
                        performed_by=performed_by,
                        notes=f"RMA restock from order {fo.order.order_number} ({notes})",
                        reference_type="return_request",
                        reference_id=str(req.pk)
                    )

    if notes:
        req.staff_notes = f"{req.staff_notes}\n[{action.upper()}] {notes}".strip()
    if performed_by and not req.inspected_by:
        req.inspected_by = performed_by

    req.save()

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type=f"RMA_{action.upper()}",
        description=f"Return/Exchange request updated to {req.get_status_display()}.",
        performed_by=performed_by,
        metadata={"rma_id": req.pk, "action": action},
    )

    return req


@transaction.atomic
def cancel_fulfillment(
    fulfillment_order: FulfillmentOrder,
    reason: str = "Order cancelled",
    performed_by: Optional[Any] = None,
) -> FulfillmentOrder:
    """
    Cancel fulfillment order and trigger order cancellation + stock reservation release.
    """
    fo = FulfillmentOrder.objects.select_for_update().get(pk=fulfillment_order.pk)
    fo.fulfillment_status = FulfillmentWorkflowStatus.CANCELLED
    fo.internal_notes = f"{fo.internal_notes}\n[Cancelled] {reason}".strip()
    fo.save(update_fields=["fulfillment_status", "internal_notes", "updated_at"])

    if fo.order.status != OrderStatus.CANCELLED:
        transition_order_status(fo.order, OrderStatus.CANCELLED, note=reason)

    log_fulfillment_event(
        fulfillment_order=fo,
        event_type="CANCELLED",
        description=f"Fulfillment cancelled: {reason}",
        performed_by=performed_by,
    )

    return fo


def fulfillment_timeline(fulfillment_order: FulfillmentOrder) -> List[Dict[str, Any]]:
    """
    Generate a chronological, user/staff-friendly sequence of status progression events.
    """
    events = list(fulfillment_order.events.order_by("created_at"))
    shipment = fulfillment_order.shipments.first()

    timeline = [
        {
            "step": 1,
            "title": "Order Confirmed & Paid",
            "status_code": "paid",
            "is_completed": fulfillment_order.fulfillment_status != FulfillmentWorkflowStatus.PENDING_PAYMENT,
            "is_active": fulfillment_order.fulfillment_status in {FulfillmentWorkflowStatus.PAID, FulfillmentWorkflowStatus.PROCESSING},
            "timestamp": fulfillment_order.created_at,
            "description": f"Order {fulfillment_order.order.order_number} successfully placed and queued for fulfillment.",
            "icon": "bi-bag-check-fill",
        },
        {
            "step": 2,
            "title": "Being Prepared (Picking & Packing)",
            "status_code": "picking",
            "is_completed": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.PACKED, FulfillmentWorkflowStatus.READY_FOR_DISPATCH,
                FulfillmentWorkflowStatus.SHIPPED, FulfillmentWorkflowStatus.OUT_FOR_DELIVERY,
                FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED,
            },
            "is_active": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.PICKING, FulfillmentWorkflowStatus.PICKED, FulfillmentWorkflowStatus.PACKING
            },
            "timestamp": fulfillment_order.picking_started_at or fulfillment_order.updated_at,
            "description": "Warehouse team is actively locating, verifying, and securely packing order items.",
            "icon": "bi-box-seam-fill",
        },
        {
            "step": 3,
            "title": "Ready for Dispatch",
            "status_code": "ready_for_dispatch",
            "is_completed": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.SHIPPED, FulfillmentWorkflowStatus.OUT_FOR_DELIVERY,
                FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED,
            },
            "is_active": fulfillment_order.fulfillment_status == FulfillmentWorkflowStatus.READY_FOR_DISPATCH,
            "timestamp": fulfillment_order.packing_completed_at or fulfillment_order.updated_at,
            "description": f"Shipping label generated ({shipment.courier if shipment else 'Logistics'}). Awaiting courier pickup.",
            "icon": "bi-tag-fill",
        },
        {
            "step": 4,
            "title": "Shipped & In Transit",
            "status_code": "shipped",
            "is_completed": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED,
            },
            "is_active": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.SHIPPED, FulfillmentWorkflowStatus.OUT_FOR_DELIVERY
            },
            "timestamp": fulfillment_order.dispatched_at,
            "description": f"Shipped via {shipment.courier if shipment else 'Courier'} (Tracking: {shipment.tracking_number if shipment else 'Pending'}).",
            "icon": "bi-truck",
        },
        {
            "step": 5,
            "title": "Delivered",
            "status_code": "delivered",
            "is_completed": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED,
            },
            "is_active": fulfillment_order.fulfillment_status in {
                FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED,
            },
            "timestamp": fulfillment_order.delivered_at,
            "description": "Confirmed delivered to destination address.",
            "icon": "bi-house-check-fill",
        },
    ]

    return timeline
