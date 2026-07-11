# dashboard/selectors.py
"""
dashboard/selectors.py
──────────────────────────────────────────────────────────────────────────────
Optimized query selectors for the Custom Administration Dashboard.

Implements queries with zero N+1 overhead using `select_related`,
`prefetch_related`, and database-level aggregations (`Sum`, `Avg`, `Count`).

Selectors:
- revenue_today()
- orders_today()
- pending_orders()
- processing_orders()
- total_products()
- total_customers()
- low_stock_products()
- average_order_value()
- recent_orders()
- new_customers()
- recent_activity()
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any
from django.contrib.auth import get_user_model
from django.db.models import Avg, Sum, QuerySet
from django.utils import timezone

from orders.models import Order, OrderStatus, PaymentStatus
from products.models import Product
from .models import AuditLog

User = get_user_model()


def revenue_today() -> Decimal:
    """
    Calculate total revenue generated from paid or processing orders placed today.
    """
    today = timezone.now().date()
    result = Order.objects.filter(
        created_at__date=today,
        payment_status=PaymentStatus.PAID
    ).aggregate(total=Sum("grand_total"))["total"]
    return result or Decimal("0.00")


def orders_today() -> int:
    """
    Count total number of orders placed today across all lifecycle states.
    """
    today = timezone.now().date()
    return Order.objects.filter(created_at__date=today).count()


def pending_orders() -> QuerySet[Order]:
    """
    Retrieve queryset of all currently pending customer orders, eager-loading
    user account details.
    """
    return Order.objects.filter(status=OrderStatus.PENDING).select_related("user").order_by("-created_at")


def processing_orders() -> QuerySet[Order]:
    """
    Retrieve queryset of all customer orders currently in processing.
    """
    return Order.objects.filter(status=OrderStatus.PROCESSING).select_related("user").order_by("-created_at")


def total_products() -> int:
    """
    Return the total number of products in the catalog.
    """
    return Product.objects.count()


def total_customers() -> int:
    """
    Return the total number of registered non-staff customer accounts.
    """
    return User.objects.filter(is_staff=False).count()


def low_stock_products(limit: int = 10) -> QuerySet[Any]:
    """
    Retrieve products or inventory records whose available quantity is at or below
    the reorder threshold. Delegates to inventory selectors for real-time accuracy.
    """
    try:
        from inventory.selectors import low_stock_products as inv_low_stock
        return inv_low_stock(limit=limit)
    except Exception:
        return []


def average_order_value() -> Decimal:
    """
    Calculate the Average Order Value (AOV) across all successfully paid orders.
    """
    result = Order.objects.filter(payment_status=PaymentStatus.PAID).aggregate(
        aov=Avg("grand_total")
    )["aov"]
    if result is None:
        return Decimal("0.00")
    return Decimal(str(result)).quantize(Decimal("0.01"))


def recent_orders(limit: int = 10) -> QuerySet[Order]:
    """
    Fetch the most recent customer orders with optimized related queries.
    """
    return Order.objects.select_related("user").order_by("-created_at")[:limit]


def new_customers(limit: int = 10) -> QuerySet[Any]:
    """
    Fetch the most recently registered customer accounts, prefetching profile data.
    """
    return User.objects.filter(is_staff=False).select_related("profile").order_by("-date_joined")[:limit]


def recent_activity(limit: int = 20) -> QuerySet[AuditLog]:
    """
    Retrieve recent administrative and system activity events from the audit log,
    optimized with user prefetching.
    """
    return AuditLog.objects.select_related("user").order_by("-timestamp")[:limit]
