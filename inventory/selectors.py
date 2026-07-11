from __future__ import annotations

from django.db.models import Avg, Count, F, Q, Sum

from .models import Inventory, InventoryMovement, MovementType


def low_stock_products(limit: int = 10):
    return Inventory.objects.select_related("product_variant", "product_variant__product").filter(available_quantity__gt=0, available_quantity__lte=F("reorder_level")).order_by("available_quantity")[:limit]


def out_of_stock_products(limit: int = 10):
    return Inventory.objects.select_related("product_variant", "product_variant__product").filter(available_quantity=0).order_by("product_variant__product__name")[:limit]


def inventory_value():
    return Inventory.objects.aggregate(total=Sum(F("available_quantity") * F("product_variant__cost_price")))


def recent_movements(limit: int = 10):
    return InventoryMovement.objects.select_related("inventory", "inventory__product_variant", "performed_by").order_by("-created_at")[:limit]


def reserved_inventory():
    return Inventory.objects.select_related("product_variant", "product_variant__product").filter(reserved_quantity__gt=0).order_by("-reserved_quantity")


def damaged_inventory():
    return Inventory.objects.select_related("product_variant", "product_variant__product").filter(damaged_quantity__gt=0).order_by("-damaged_quantity")


def products_to_reorder(limit: int = 10):
    return Inventory.objects.select_related("product_variant", "product_variant__product").filter(available_quantity__lte=F("reorder_level")).order_by("available_quantity")[:limit]


def most_adjusted_products(limit: int = 10):
    return (
        Inventory.objects.select_related("product_variant", "product_variant__product")
        .annotate(
            adjustment_count=Count(
                "movements",
                filter=Q(
                    movements__movement_type__in=[
                        MovementType.MANUAL_INCREASE,
                        MovementType.MANUAL_DECREASE,
                        MovementType.INVENTORY_CORRECTION,
                    ]
                ),
            )
        )
        .filter(adjustment_count__gt=0)
        .order_by("-adjustment_count", "-updated_at")[:limit]
    )
