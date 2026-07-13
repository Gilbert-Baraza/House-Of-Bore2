# orders/tasks.py
"""
orders/tasks.py
──────────────────────────────────────────────────────────────────────────────
Background Celery tasks for order lifecycle management:
1. expire_pending_payments — auto-expire orders pending payment beyond cutoff
2. clear_abandoned_carts — purge inactive shopping carts after 7 days
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("orders")


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def expire_pending_payments(self):
    """
    Periodic task that marks orders stuck in 'pending' / 'awaiting_payment'
    status for over 24 hours as expired. This frees reserved inventory and
    prevents ghost orders from inflating sales reports.

    Runs hourly via Celery Beat.
    """
    from orders.models import Order, OrderStatus, PaymentStatus

    cutoff = timezone.now() - timedelta(hours=24)

    expired_orders = Order.objects.filter(
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.AWAITING_PAYMENT,
        created_at__lt=cutoff,
    )

    count = expired_orders.count()

    if count > 0:
        expired_orders.update(
            status=OrderStatus.CANCELLED,
            payment_status=PaymentStatus.EXPIRED,
            updated_at=timezone.now(),
        )
        logger.warning(
            "Expired %d pending orders older than %s.",
            count,
            cutoff.isoformat(),
        )

    return {"expired_count": count, "cutoff": cutoff.isoformat()}


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def clear_abandoned_carts(self):
    """
    Periodic task that deletes shopping carts that have been inactive for
    more than 7 days. This cleans up abandoned sessions and prevents
    database bloat from unfinished checkouts.

    Runs daily at 3:00 AM via Celery Beat.
    """
    from cart.models import Cart

    cutoff = timezone.now() - timedelta(days=7)

    abandoned_carts = Cart.objects.filter(updated_at__lt=cutoff)
    count = abandoned_carts.count()

    if count > 0:
        abandoned_carts.delete()
        logger.info(
            "Cleared %d abandoned carts older than %s.",
            count,
            cutoff.isoformat(),
        )

    return {"cleared_count": count, "cutoff": cutoff.isoformat()}
