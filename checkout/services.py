# checkout/services.py
"""
checkout/services.py
──────────────────────────────────────────────────────────────────────────────
Business services for checkout progression.
Covers checkout creation, updating address data, totals calculation,
session verification, and cart validations.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
import datetime
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from checkout.models import CheckoutSession, CheckoutAddress
from checkout.selectors import get_checkout
from cart.selectors import get_cart
from cart.services import get_or_create_cart


@transaction.atomic
def get_or_create_checkout(request: HttpRequest) -> CheckoutSession:
    """
    Retrieve or initialize the active checkout session linked to the current cart.
    Automatically handles guest-session key and user account association updates.
    """
    cart = get_cart(request)
    if not cart:
        # Create empty cart to associate
        cart = get_or_create_cart(request)

    checkout_session = CheckoutSession.objects.filter(cart=cart, status="active").first()

    if not checkout_session:
        user = request.user if (hasattr(request, "user") and request.user.is_authenticated) else None
        session_obj = getattr(request, "session", None)
        session_key = getattr(session_obj, "session_key", None) if session_obj else None
        if not session_key and session_obj is not None:
            session_obj.create()
            session_key = session_obj.session_key

        checkout_session = CheckoutSession.objects.create(
            user=user,
            session_key=session_key if not user else None,
            cart=cart,
            expires_at=timezone.now() + datetime.timedelta(hours=24),
            status="active"
        )
    else:
        # Update user binding if they authenticated since creation
        if hasattr(request, "user") and request.user.is_authenticated and not checkout_session.user:
            checkout_session.user = request.user
            checkout_session.session_key = None
            checkout_session.save()

    return checkout_session


@transaction.atomic
def update_shipping(checkout_session: CheckoutSession, address_data: dict) -> CheckoutAddress:
    """
    Atomically update or create the shipping address associated with the session.
    """
    if checkout_session.shipping_address:
        address = checkout_session.shipping_address
        for key, val in address_data.items():
            setattr(address, key, val)
        address.save()
    else:
        address = CheckoutAddress.objects.create(**address_data)
        checkout_session.shipping_address = address
        checkout_session.save()
    return address


@transaction.atomic
def update_billing(checkout_session: CheckoutSession, address_data: dict, billing_same_as_shipping: bool) -> Optional[CheckoutAddress]:
    """
    Atomically update or create the billing address associated with the session.
    Frees and deletes independent billing addresses if billing_same_as_shipping is set to True.
    """
    checkout_session.billing_same_as_shipping = billing_same_as_shipping
    
    if billing_same_as_shipping:
        if checkout_session.billing_address:
            old_billing = checkout_session.billing_address
            checkout_session.billing_address = None
            checkout_session.save()
            old_billing.delete()
        else:
            checkout_session.save()
        return None

    if checkout_session.billing_address:
        address = checkout_session.billing_address
        for key, val in address_data.items():
            setattr(address, key, val)
        address.save()
    else:
        address = CheckoutAddress.objects.create(**address_data)
        checkout_session.billing_address = address
        checkout_session.save()
    return address


def validate_checkout(checkout_session: CheckoutSession) -> None:
    """
    Validate checkout requirements.
    Ensures the cart is not empty, products are active, stock is not exceeded,
    and required addresses are snapshotted.
    """
    # 1. Cart Empty Check
    cart = checkout_session.cart
    if not cart or cart.item_count() == 0:
        raise ValidationError("Your shopping cart is empty.")

    # 2. Inventory and Status Check
    for item in cart.items.all():
        if item.product_variant:
            if not item.product_variant.is_active or not item.product.is_active:
                raise ValidationError(f"The item option '{item.product.name} ({item.product_variant.get_options_summary()})' is no longer active or available.")
            if item.quantity > item.product_variant.stock_quantity:
                raise ValidationError(
                    f"The requested quantity ({item.quantity}) for '{item.product.name} ({item.product_variant.get_options_summary()})' exceeds available stock ({item.product_variant.stock_quantity})."
                )
        else:
            if not item.product.is_active:
                raise ValidationError(f"The item '{item.product.name}' is no longer active or available.")
            if item.quantity > item.product.stock_quantity:
                raise ValidationError(
                    f"The requested quantity ({item.quantity}) for '{item.product.name}' exceeds available stock ({item.product.stock_quantity})."
                )

    # 3. Address Complete Validation
    if not checkout_session.shipping_address:
        raise ValidationError("Shipping address has not been provided.")
    if not checkout_session.billing_same_as_shipping and not checkout_session.billing_address:
        raise ValidationError("Billing address has not been provided.")


def checkout_summary(checkout_session: CheckoutSession) -> dict:
    """
    Retrieve summary total pricing and full breakdown for checkout via pricing engine.
    """
    from pricing.services import pricing_breakdown
    breakdown = pricing_breakdown(cart=checkout_session.cart, shipping_address=checkout_session.shipping_address)
    # Ensure backwards compatibility for shipping_cost and tax_cost keys
    breakdown["shipping_cost"] = breakdown["shipping"]
    breakdown["tax_cost"] = breakdown["tax"]
    return breakdown


@transaction.atomic
def clear_checkout(request: HttpRequest) -> None:
    """
    Close the active checkout session by setting status to completed.
    """
    checkout = get_checkout(request)
    if checkout:
        checkout.status = "completed"
        checkout.save()
