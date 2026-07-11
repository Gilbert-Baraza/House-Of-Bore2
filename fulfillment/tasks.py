# fulfillment/tasks.py
"""
fulfillment/tasks.py
──────────────────────────────────────────────────────────────────────────────
Background Celery tasks for order fulfillment supervision:
1. `check_overdue_fulfillments`: Scans for orders awaiting picking/packing over 24 hours.
2. `check_delivery_exceptions`: Scans carrier shipments stuck in exception status.
──────────────────────────────────────────────────────────────────────────────
"""

from datetime import timedelta
from typing import Dict
from celery import shared_task
from django.utils import timezone

from .models import FulfillmentOrder, FulfillmentWorkflowStatus, Shipment, ShipmentStatus


@shared_task
def check_overdue_fulfillments() -> Dict[str, int]:
    """
    Periodic task scanning for fulfillment orders that have been in 'Paid' or
    'Picking' status for over 24 hours without completing packing or dispatch.
    Stamps high priority or logs internal alerts.
    """
    threshold = timezone.now() - timedelta(hours=24)
    overdue_picks = FulfillmentOrder.objects.filter(
        fulfillment_status__in=[FulfillmentWorkflowStatus.PAID, FulfillmentWorkflowStatus.PROCESSING, FulfillmentWorkflowStatus.PICKING],
        created_at__lt=threshold,
    )
    count = overdue_picks.count()
    if count > 0:
        # Elevate priority of overdue items
        overdue_picks.filter(priority__gt=1).update(priority=1, updated_at=timezone.now())

    return {"overdue_fulfillment_count": count}


@shared_task
def check_delivery_exceptions() -> Dict[str, int]:
    """
    Periodic task aggregating shipments flagged with delivery delays or exceptions.
    """
    exception_shipments = Shipment.objects.filter(shipment_status=ShipmentStatus.EXCEPTION)
    return {"exception_shipment_count": exception_shipments.count()}
