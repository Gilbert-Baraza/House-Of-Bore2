# fulfillment/signals.py
"""
fulfillment/signals.py
──────────────────────────────────────────────────────────────────────────────
Signal handlers connecting the Order Management System (OMS) with automatic
fulfillment order creation upon payment receipt (`OrderStatus.PAID`), and
automatic RBAC registration post-migration.
──────────────────────────────────────────────────────────────────────────────
"""

from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from orders.models import Order, OrderStatus
from .models import FulfillmentOrder
from .permissions import ensure_fulfillment_permissions
from .services import create_fulfillment_order


@receiver(post_save, sender=Order)
def on_order_post_save(sender, instance: Order, created: bool, **kwargs) -> None:
    """
    Automatically generate a FulfillmentOrder when a customer Order transitions to PAID or PROCESSING.
    """
    if instance.status in {OrderStatus.PAID, OrderStatus.PROCESSING}:
        if not hasattr(instance, "fulfillment_order") and not FulfillmentOrder.objects.filter(order=instance).exists():
            try:
                create_fulfillment_order(order=instance)
            except Exception:
                # Log or ignore if transaction collision inside checkout setup
                pass


@receiver(post_migrate)
def on_post_migrate(sender, **kwargs) -> None:
    """Ensure fulfillment permissions are backfilled to staff roles after migrations."""
    if sender.name == "fulfillment":
        try:
            ensure_fulfillment_permissions()
        except Exception:
            pass
