# fulfillment/selectors.py
"""
fulfillment/selectors.py
──────────────────────────────────────────────────────────────────────────────
Optimized query selectors for the Order Fulfillment & Shipping Operations engine.
Ensures zero N+1 query patterns using strict `select_related` and `prefetch_related`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict
from django.db.models import Count, Q, QuerySet

from .models import (
    FulfillmentEvent,
    FulfillmentOrder,
    FulfillmentWorkflowStatus,
    ReturnExchangeRequest,
    ReturnRequestStatus,
    Shipment,
    ShipmentStatus,
)


def _base_fulfillment_queryset() -> QuerySet[FulfillmentOrder]:
    return (
        FulfillmentOrder.objects.select_related(
            "order",
            "order__user",
            "assigned_staff",
            "assigned_picker",
            "assigned_packer",
        )
        .prefetch_related("items", "items__order_item", "shipments")
        .order_by("priority", "-created_at")
    )


def pending_picks() -> QuerySet[FulfillmentOrder]:
    """Return orders queued or actively undergoing warehouse item picking."""
    return _base_fulfillment_queryset().filter(
        fulfillment_status__in=[
            FulfillmentWorkflowStatus.PAID,
            FulfillmentWorkflowStatus.PROCESSING,
            FulfillmentWorkflowStatus.PICKING,
        ]
    )


def pending_packs() -> QuerySet[FulfillmentOrder]:
    """Return orders picked and awaiting or undergoing box packing."""
    return _base_fulfillment_queryset().filter(
        fulfillment_status__in=[
            FulfillmentWorkflowStatus.PICKED,
            FulfillmentWorkflowStatus.PACKING,
        ]
    )


def ready_for_dispatch() -> QuerySet[FulfillmentOrder]:
    """Return orders packed and labeled, awaiting courier handoff/pickup."""
    return _base_fulfillment_queryset().filter(
        fulfillment_status=FulfillmentWorkflowStatus.READY_FOR_DISPATCH
    )


def active_shipments() -> QuerySet[Shipment]:
    """Return active shipments currently in transit or out for delivery."""
    return (
        Shipment.objects.select_related(
            "fulfillment_order",
            "fulfillment_order__order",
        )
        .filter(
            shipment_status__in=[
                ShipmentStatus.LABEL_CREATED,
                ShipmentStatus.PICKED_UP,
                ShipmentStatus.IN_TRANSIT,
                ShipmentStatus.OUT_FOR_DELIVERY,
            ]
        )
        .order_by("-updated_at")
    )


def delivery_exceptions() -> QuerySet[FulfillmentOrder]:
    """Return orders experiencing delivery delays, exceptions, or failures."""
    return _base_fulfillment_queryset().filter(
        Q(fulfillment_status=FulfillmentWorkflowStatus.FAILED_DELIVERY)
        | Q(shipments__shipment_status=ShipmentStatus.EXCEPTION)
    ).distinct()


def return_exchange_requests() -> QuerySet[ReturnExchangeRequest]:
    """Return active RMA requests under customer service or warehouse inspection."""
    return (
        ReturnExchangeRequest.objects.select_related(
            "fulfillment_order",
            "fulfillment_order__order",
            "inspected_by",
        )
        .order_by("-created_at")
    )


def recent_events(limit: int = 15) -> QuerySet[FulfillmentEvent]:
    """Return most recent operational audit events across all fulfillments."""
    return (
        FulfillmentEvent.objects.select_related(
            "fulfillment_order",
            "fulfillment_order__order",
            "performed_by",
        )
        .order_by("-created_at")[:limit]
    )


def fulfillment_statistics() -> Dict[str, Any]:
    """
    Aggregate high-level operational KPI metrics for the fulfillment dashboard.
    """
    qs = FulfillmentOrder.objects.all()
    stats = qs.aggregate(
        total_orders=Count("id"),
        awaiting_pick=Count("id", filter=Q(fulfillment_status__in=[FulfillmentWorkflowStatus.PAID, FulfillmentWorkflowStatus.PROCESSING, FulfillmentWorkflowStatus.PICKING])),
        awaiting_pack=Count("id", filter=Q(fulfillment_status__in=[FulfillmentWorkflowStatus.PICKED, FulfillmentWorkflowStatus.PACKING])),
        ready_dispatch=Count("id", filter=Q(fulfillment_status=FulfillmentWorkflowStatus.READY_FOR_DISPATCH)),
        in_transit=Count("id", filter=Q(fulfillment_status__in=[FulfillmentWorkflowStatus.SHIPPED, FulfillmentWorkflowStatus.OUT_FOR_DELIVERY])),
        exceptions=Count("id", filter=Q(fulfillment_status=FulfillmentWorkflowStatus.FAILED_DELIVERY) | Q(shipments__shipment_status=ShipmentStatus.EXCEPTION)),
        delivered=Count("id", filter=Q(fulfillment_status__in=[FulfillmentWorkflowStatus.DELIVERED, FulfillmentWorkflowStatus.COMPLETED])),
    )
    # Ensure no None values
    for k in stats:
        stats[k] = stats[k] or 0

    return stats


def get_fulfillment_by_id(pk: Any) -> Optional[FulfillmentOrder]:
    """Fetch single fulfillment order with full prefetch."""
    return _base_fulfillment_queryset().filter(pk=pk).first()
