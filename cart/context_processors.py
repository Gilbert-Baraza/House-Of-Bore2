# cart/context_processors.py
"""
cart/context_processors.py
──────────────────────────────────────────────────────────────────────────────
Global template context processor exposing shopping cart metrics.
Powers the live item count badge and subtotal across the site navigation.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Dict, Any
from django.http import HttpRequest
from cart.selectors import get_cart, cart_item_count, cart_total


def cart(request: HttpRequest) -> Dict[str, Any]:
    """
    Expose shopping cart state and financial metrics globally to all template contexts.
    
    Returns:
        dict containing:
        - cart: Active Cart model instance (or None if empty/non-existent).
        - cart_item_count: Total physical unit count (integer).
        - cart_subtotal: Total monetary value (Decimal).
    """
    try:
        cart_obj = get_cart(request)
        count = cart_item_count(cart_obj)
        subtotal = cart_total(cart_obj)
    except Exception:
        # Prevent rendering failures if DB tables or sessions are inaccessible during setup
        cart_obj = None
        count = 0
        subtotal = Decimal("0.00")

    return {
        "cart": cart_obj,
        "cart_item_count": count,
        "cart_subtotal": subtotal,
    }
