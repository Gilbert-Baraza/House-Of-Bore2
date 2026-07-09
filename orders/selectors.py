# orders/selectors.py
"""
orders/selectors.py
──────────────────────────────────────────────────────────────────────────────
High-performance database query queries for orders and order items.
Enforces security constraints (user access parity / guest session tokens) and
optimizes relationship fetching with `select_related()` and `prefetch_related()`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Optional
from django.db.models import QuerySet
from orders.models import Order, OrderItem


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
