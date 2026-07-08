# checkout/selectors.py
"""
checkout/selectors.py
──────────────────────────────────────────────────────────────────────────────
Read-only selectors for checkout session status, totals, and addresses.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
from django.http import HttpRequest
from checkout.models import CheckoutSession, CheckoutAddress
from cart.selectors import get_cart


def get_checkout(request: HttpRequest) -> Optional[CheckoutSession]:
    """
    Retrieve the active checkout session associated with the current cart.
    Returns None if no active cart or checkout session is found.
    """
    cart = get_cart(request)
    if not cart:
        return None
    return CheckoutSession.objects.filter(
        cart=cart, status="active"
    ).select_related(
        "shipping_address", "billing_address", "cart"
    ).first()


def get_shipping_address(checkout_session: Optional[CheckoutSession]) -> Optional[CheckoutAddress]:
    """
    Retrieve the shipping address snapshotted on the checkout session.
    """
    return checkout_session.shipping_address if checkout_session else None


def get_billing_address(checkout_session: Optional[CheckoutSession]) -> Optional[CheckoutAddress]:
    """
    Retrieve the billing address snapshotted on the checkout session.
    Falls back to shipping if 'billing_same_as_shipping' is True.
    """
    if not checkout_session:
        return None
    if checkout_session.billing_same_as_shipping:
        return checkout_session.shipping_address
    return checkout_session.billing_address
