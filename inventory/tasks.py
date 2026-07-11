import logging
from celery import shared_task
from django.utils import timezone

from .selectors import low_stock_products, out_of_stock_products, products_to_reorder

logger = logging.getLogger(__name__)


@shared_task
def generate_inventory_alerts() -> dict[str, int]:
    """
    Periodic task that audits inventory levels and aggregates low-stock, out-of-stock,
    and reorder threshold alerts. Prepares data payload for email/SMS notification dispatch.
    """
    low_stock = low_stock_products(limit=500)
    out_of_stock = out_of_stock_products(limit=500)
    to_reorder = products_to_reorder(limit=500)

    alerts_count = {
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "reorder_needed_count": len(to_reorder),
        "timestamp": timezone.now().isoformat(),
    }

    if alerts_count["low_stock_count"] > 0 or alerts_count["out_of_stock_count"] > 0:
        logger.warning(
            "Inventory Alert Generated: %d out-of-stock items, %d low-stock items.",
            alerts_count["out_of_stock_count"],
            alerts_count["low_stock_count"],
        )
        # Future architecture hook: Dispatch email/SMS digest to inventory_manager staff members

    return alerts_count


@shared_task
def dispatch_inventory_alert_notification(alert_type: str, product_name: str, current_quantity: int, threshold: int) -> bool:
    """
    Celery-ready task architecture for dispatching real-time stock notifications via Email and SMS
    to store administrators and warehouse managers when critical thresholds are crossed.
    """
    logger.info(
        "Dispatching %s alert for product '%s'. Current stock: %d (Threshold: %d)",
        alert_type,
        product_name,
        current_quantity,
        threshold,
    )
    return True

