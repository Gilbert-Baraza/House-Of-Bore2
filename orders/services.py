# orders/services.py
"""
orders/services.py
──────────────────────────────────────────────────────────────────────────────
Service layer encapsulating all business logic for Order creation, numbering,
address and product snapshots, pricing locks, and status transitions.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from checkout.models import CheckoutSession
from checkout.services import validate_checkout
from orders.models import (
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
)
from pricing.services import pricing_breakdown


def generate_order_number() -> str:
    """
    Generate a unique, human-readable order number independent of database primary keys.
    Format: HOB-YYYYMMDD-000001
    """
    today_str = timezone.now().strftime("%Y%m%d")
    prefix = f"HOB-{today_str}-"

    # Find the latest order for today with this exact prefix
    latest_order = (
        Order.objects.filter(order_number__startswith=prefix)
        .order_by("-order_number")
        .first()
    )

    if latest_order:
        try:
            last_seq = int(latest_order.order_number.split("-")[-1])
            seq = last_seq + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    # Ensure uniqueness loop under concurrency
    for _ in range(100):
        order_number = f"{prefix}{seq:06d}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number
        seq += 1

    # Fallback timestamp microsecond suffix if extreme concurrency encountered
    micro_str = timezone.now().strftime("%H%M%S%f")[:8]
    return f"HOB-{today_str}-{micro_str}"


def snapshot_addresses(checkout_session: CheckoutSession) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extract immutable JSON dictionaries from the checkout session's shipping and billing addresses.
    """
    shipping_addr = checkout_session.shipping_address
    billing_addr = checkout_session.billing_address
    if checkout_session.billing_same_as_shipping:
        billing_addr = shipping_addr

    def _addr_to_dict(addr: Any) -> Dict[str, Any]:
        if not addr:
            return {}
        return {
            "recipient_name": getattr(addr, "recipient_name", ""),
            "phone_number": getattr(addr, "phone_number", ""),
            "company_name": getattr(addr, "company_name", ""),
            "address_line_1": getattr(addr, "address_line_1", ""),
            "address_line_2": getattr(addr, "address_line_2", ""),
            "city": getattr(addr, "city", ""),
            "county_or_state": getattr(addr, "county_or_state", ""),
            "postal_code": getattr(addr, "postal_code", ""),
            "country": getattr(addr, "country", "US"),
        }

    return _addr_to_dict(shipping_addr), _addr_to_dict(billing_addr)


def calculate_order_totals(checkout_session: CheckoutSession) -> Dict[str, Decimal]:
    """
    Run the pricing engine against the validated cart and snapshotted shipping address
    to lock exact financial totals for the order.
    """
    cart = checkout_session.cart
    shipping_addr = checkout_session.shipping_address
    breakdown = pricing_breakdown(cart=cart, shipping_address=shipping_addr)

    return {
        "subtotal": breakdown.get("subtotal", Decimal("0.00")),
        "discount_total": breakdown.get("discount", Decimal("0.00")) + breakdown.get("coupon_discount", Decimal("0.00")),
        "shipping_total": breakdown.get("shipping", Decimal("0.00")),
        "tax_total": breakdown.get("tax", Decimal("0.00")),
        "grand_total": breakdown.get("grand_total", Decimal("0.00")),
    }


def snapshot_products(order: Order, cart: Any) -> List[OrderItem]:
    """
    Extract immutable line item snapshots from the shopping cart and link them to the order.
    Never depends on live Product models after creation.
    """
    order_items = []
    if not cart or not hasattr(cart, "items"):
        return order_items

    for cart_item in cart.items.all().select_related("product", "product_variant"):
        product = cart_item.product
        variant = cart_item.product_variant

        if variant:
            sku = variant.sku
            variant_desc = variant.get_description()
            unit_price = cart_item.unit_price or variant.get_price()
        else:
            sku = getattr(product, "sku", f"PRD-{product.id}")
            variant_desc = ""
            unit_price = cart_item.unit_price or getattr(product, "price", Decimal("0.00"))

        item = OrderItem.objects.create(
            order=order,
            product=product,
            product_name=getattr(product, "name", "Product"),
            product_slug=getattr(product, "slug", ""),
            sku=sku,
            variant_description=variant_desc,
            quantity=cart_item.quantity,
            unit_price=unit_price,
            line_total=Decimal(str(cart_item.quantity)) * Decimal(str(unit_price)),
        )
        order_items.append(item)

    return order_items


@transaction.atomic
def create_order(request: HttpRequest, checkout_session: CheckoutSession, customer_notes: str = "") -> Order:
    """
    Validate checkout, calculate totals, generate order number, persist order and item snapshots,
    lock pricing, mark checkout session completed, and clear the shopping cart.
    """
    # 1. Strict validation before order placement
    validate_checkout(checkout_session)

    # 2. Calculate locked totals
    totals = calculate_order_totals(checkout_session)

    # 3. Snapshot addresses
    shipping_snap, billing_snap = snapshot_addresses(checkout_session)

    # 4. Generate order number
    order_number = generate_order_number()

    # 5. Determine customer account or guest session association
    user = None
    if request and hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    elif checkout_session.user:
        user = checkout_session.user

    session_key = getattr(request.session, "session_key", None) if request and hasattr(request, "session") else None
    if not session_key and checkout_session.session_key:
        session_key = checkout_session.session_key

    # 6. Create permanent Order record with concurrency collision retry protection
    order = None
    for _ in range(3):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    order_number=order_number,
                    user=user,
                    checkout_session=checkout_session,
                    session_key=session_key,
                    status=OrderStatus.PENDING,
                    payment_status=PaymentStatus.AWAITING_PAYMENT,
                    fulfillment_status=FulfillmentStatus.UNFULFILLED,
                    shipping_address_snapshot=shipping_snap,
                    billing_address_snapshot=billing_snap,
                    subtotal=totals["subtotal"],
                    discount_total=totals["discount_total"],
                    shipping_total=totals["shipping_total"],
                    tax_total=totals["tax_total"],
                    grand_total=totals["grand_total"],
                    currency="USD",
                    customer_notes=customer_notes.strip(),
                )
            break
        except IntegrityError:
            order_number = generate_order_number()

    if not order:
        raise ValidationError("Unable to generate a unique order number after multiple attempts. Please retry.")

    # 7. Create immutable OrderItem snapshots
    snapshot_products(order, checkout_session.cart)

    # 8. Complete checkout session and clear cart items
    checkout_session.status = "completed"
    checkout_session.save(update_fields=["status"])

    if checkout_session.cart:
        checkout_session.cart.items.all().delete()
        if hasattr(checkout_session.cart, "_cached_breakdown"):
            delattr(checkout_session.cart, "_cached_breakdown")

    return order


@transaction.atomic
def transition_order_status(order: Order, new_status: str, note: str = "") -> Order:
    """
    Perform a controlled status transition on an order and update financial/fulfillment flags as needed.
    """
    valid_statuses = dict(OrderStatus.choices)
    if new_status not in valid_statuses:
        raise ValidationError(f"Invalid order status: {new_status}")

    order.status = new_status
    if new_status == OrderStatus.PAID:
        order.payment_status = PaymentStatus.PAID
    elif new_status == OrderStatus.CANCELLED:
        if order.payment_status == PaymentStatus.PAID:
            order.payment_status = PaymentStatus.REFUNDED
    elif new_status == OrderStatus.DELIVERED:
        order.fulfillment_status = FulfillmentStatus.FULFILLED

    if note:
        order.customer_notes = f"{order.customer_notes}\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {note}".strip()

    order.save()
    return order
