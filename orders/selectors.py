# orders/selectors.py
"""
orders/selectors.py
──────────────────────────────────────────────────────────────────────────────
High-performance database query queries for orders and order items.
Enforces security constraints (user access parity / guest session tokens) and
optimizes relationship fetching with `select_related()` and `prefetch_related()`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict, Optional
from django.db.models import Count, Q, QuerySet
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus


def get_order(order_number: str, user: Optional[Any] = None, session_key: Optional[str] = None) -> Optional[Order]:
    """
    Fetch an order by its unique human-readable order number.
    Applies security checks so authenticated customers can only access their own orders,
    and guests can only access orders matching their active session key.
    If `user` is staff (`is_staff`), full access is granted.
    """
    order = (
        Order.objects.filter(order_number=order_number)
        .select_related("user", "checkout_session")
        .prefetch_related("items", "items__product")
        .first()
    )
    if not order:
        return None

    # Staff override
    if user and hasattr(user, "is_staff") and user.is_staff:
        return order

    # Authenticated user check
    if user and hasattr(user, "is_authenticated") and user.is_authenticated:
        if order.user == user:
            return order
        # If order was placed while guest but matches current session key, allow
        if session_key and order.session_key and order.session_key == session_key:
            return order
        return None

    # Guest session check
    if session_key and order.session_key and order.session_key == session_key:
        return order

    return None


def get_customer_orders(user: Any) -> QuerySet[Order]:
    """
    Retrieve all historical orders for an authenticated customer, ordered from newest to oldest.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return Order.objects.none()

    return (
        Order.objects.filter(user=user)
        .select_related("checkout_session")
        .prefetch_related("items")
        .order_by("-created_at")
    )


def get_order_items(order: Order) -> QuerySet[OrderItem]:
    """
    Retrieve line item snapshots belonging to a specific order.
    """
    if not order:
        return OrderItem.objects.none()

    return order.items.all().select_related("product").order_by("id")


def recent_orders(limit: int = 10) -> QuerySet[Order]:
    """
    Retrieve the most recent system orders across all customers (administrative/staff query).
    """
    return (
        Order.objects.all()
        .select_related("user")
        .prefetch_related("items")
        .order_by("-created_at")[:limit]
    )


def get_admin_orders(status: str = "all", payment_status: str = "all", search: str = "") -> QuerySet[Order]:
    """
    Administrative query for retrieving and filtering customer orders with full relationship prefetching.
    Ensures zero N+1 queries.
    """
    qs = (
        Order.objects.all()
        .select_related("user", "checkout_session", "fulfillment_order")
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )
    if status and status != "all":
        qs = qs.filter(status=status)
    if payment_status and payment_status != "all":
        qs = qs.filter(payment_status=payment_status)
    if search:
        search = search.strip()
        qs = qs.filter(
            Q(order_number__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(shipping_address_snapshot__recipient_name__icontains=search)
        ).distinct()
    return qs


def get_admin_order_statistics() -> Dict[str, Any]:
    """
    Aggregate administrative KPI metrics for customer orders.
    """
    qs = Order.objects.all()
    stats = qs.aggregate(
        total_orders=Count("id"),
        pending_payment=Count("id", filter=Q(status=OrderStatus.PENDING) | Q(payment_status=PaymentStatus.AWAITING_PAYMENT)),
        paid_awaiting=Count("id", filter=Q(status=OrderStatus.PAID)),
        processing=Count("id", filter=Q(status=OrderStatus.PROCESSING)),
        shipped=Count("id", filter=Q(status=OrderStatus.SHIPPED)),
        delivered=Count("id", filter=Q(status=OrderStatus.DELIVERED)),
        cancelled_refunded=Count("id", filter=Q(status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]) | Q(payment_status=PaymentStatus.REFUNDED)),
    )
    for k in stats:
        stats[k] = stats[k] or 0
    return stats
