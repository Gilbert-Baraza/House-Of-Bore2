# cart/selectors.py
"""
cart/selectors.py
──────────────────────────────────────────────────────────────────────────────
Read-only database queries for shopping carts and line items.
Avoids ORM logic inside views and context processors.
Utilizes prefetch_related to eliminate N+1 query bottlenecks.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Optional, List
from django.http import HttpRequest
from cart.models import Cart, CartItem


def get_cart(request: HttpRequest) -> Optional[Cart]:
    """
    Retrieve the active shopping cart for the current request.
    
    For authenticated users, looks up by `request.user`.
    For anonymous guests, looks up by `request.session.session_key`.
    Prefetches related line items and catalog product data (images, brand, category)
    to guarantee optimal performance and zero N+1 database queries.
    """
    prefetch_fields = [
        "items__product",
        "items__product__images",
        "items__product__brand",
        "items__product__category",
    ]

    if hasattr(request, "user") and request.user.is_authenticated:
        return Cart.objects.filter(user=request.user).select_related("coupon", "user").prefetch_related(*prefetch_fields).first()

    session_key = request.session.session_key
    if not session_key:
        return None

    return Cart.objects.filter(session_key=session_key).select_related("coupon", "user").prefetch_related(*prefetch_fields).first()


def get_cart_items(cart: Optional[Cart]) -> List[CartItem]:
    """
    Retrieve all ordered line items for a given shopping cart.
    Returns an empty list if the cart is None.
    """
    if not cart:
        return []
    return list(cart.items.all())


def cart_item_count(cart: Optional[Cart]) -> int:
    """
    Calculate the total number of individual physical units across all line items in the cart.
    Returns 0 if the cart is None.
    """
    if not cart:
        return 0
    return cart.item_count()


def cart_total(cart: Optional[Cart]) -> Decimal:
    """
    Calculate the monetary subtotal of all line items in the cart via pricing engine.
    Returns 0.00 if the cart is None.
    """
    from pricing.services import calculate_subtotal
    return calculate_subtotal(cart)
