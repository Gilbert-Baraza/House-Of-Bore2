# cart/services.py
"""
cart/services.py
──────────────────────────────────────────────────────────────────────────────
Business logic and service operations for the shopping cart system.
Enforces stock validation, price snapshotting, quantity constraints, and
safe session-to-persistent cart merging upon authentication.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Optional, Dict, Any
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from cart.models import Cart, CartItem
from cart.selectors import get_cart
from products.models import Product


def get_or_create_cart(request: HttpRequest) -> Cart:
    """
    Retrieve or initialize an active shopping cart for the current request.
    
    If authenticated, returns or creates a persistent user cart.
    If anonymous, ensures a session key exists and returns or creates a session cart.
    """
    if hasattr(request, "user") and request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    session_obj = getattr(request, "session", None)
    if session_obj is None:
        raise ValidationError({"session": "Active session required for anonymous shopping cart."})

    if not session_obj.session_key:
        session_obj.create()
    
    cart, _ = Cart.objects.get_or_create(session_key=session_obj.session_key)
    # Persist the guest cart ID in session to survive login key rotation
    session_obj["guest_cart_id"] = cart.id
    return cart


@transaction.atomic
def add_to_cart(request: HttpRequest, product_id: int, quantity: int = 1, variant_id: Optional[int] = None) -> CartItem:
    """
    Add a product to the shopping cart or increment its quantity if already present.
    Supports ProductVariant selection.
    """
    if quantity < 1:
        raise ValidationError({"quantity": "Please specify a valid quantity of at least 1."})

    product = Product.objects.filter(pk=product_id).first()
    if not product or not product.is_active:
        raise ValidationError("This item is currently unavailable or has been removed from the catalog.")

    variant = None
    if variant_id:
        from products.models import ProductVariant
        variant = ProductVariant.objects.filter(pk=variant_id, product=product, is_active=True).first()
        if not variant:
            raise ValidationError("The selected product option is no longer available.")
    else:
        # Check if product has required active variants
        from products.models import ProductVariant
        active_variants = list(ProductVariant.objects.filter(product=product, is_active=True))
        if len(active_variants) == 1:
            variant = active_variants[0]
        elif len(active_variants) > 1:
            raise ValidationError("Please select product options (such as color or size) before adding to bag.")

    max_stock = variant.stock_quantity if variant else product.stock_quantity
    if max_stock <= 0:
        raise ValidationError("This item is currently out of stock.")

    cart = get_or_create_cart(request)
    item = CartItem.objects.filter(cart=cart, product=product, product_variant=variant).first()
    unit_price = variant.get_price() if variant else product.price

    if item:
        new_quantity = item.quantity + quantity
        if new_quantity > max_stock:
            raise ValidationError(
                f"Cannot add {quantity} more. Only {max_stock} units are available in stock."
            )
        item.quantity = new_quantity
        item.unit_price = unit_price
        item.save()
        return item

    if quantity > max_stock:
        raise ValidationError(
            f"Only {max_stock} units are available in stock."
        )

    item = CartItem.objects.create(
        cart=cart,
        product=product,
        product_variant=variant,
        quantity=quantity,
        unit_price=unit_price
    )
    return item


@transaction.atomic
def update_quantity(request: HttpRequest, item_id: int, quantity: int, action: Optional[str] = None) -> Optional[CartItem]:
    """
    Update the requested quantity for a specific line item in the bag.
    
    If quantity <= 0, the item is removed from the cart.
    Enforces stock availability and active product status per variant.
    Supports relative action parameters (increase/decrease) to prevent HTML name collisions.
    """
    cart = get_cart(request)
    if not cart:
        raise ValidationError("Shopping cart not found.")

    item = CartItem.objects.filter(cart=cart, pk=item_id).select_related("product", "product_variant").first()
    if not item:
        raise ValidationError("Cart item not found.")

    # Apply relative quantity changes if an action is specified
    if action == "decrease":
        quantity = item.quantity - 1
    elif action == "increase":
        quantity = item.quantity + 1

    if quantity <= 0:
        item.delete()
        return None

    if item.product_variant:
        if not item.product_variant.is_active or not item.product.is_active:
            item.delete()
            raise ValidationError("This item option is no longer available and has been removed from your bag.")
        max_stock = item.product_variant.stock_quantity
        current_price = item.product_variant.get_price()
    else:
        if not item.product.is_active:
            item.delete()
            raise ValidationError("This item is no longer available and has been removed from your bag.")
        max_stock = item.product.stock_quantity
        current_price = item.product.price

    if quantity > max_stock:
        raise ValidationError(f"Only {max_stock} units are available in stock.")

    item.quantity = quantity
    item.unit_price = current_price
    item.save()
    return item


@transaction.atomic
def remove_from_cart(request: HttpRequest, item_id: int) -> bool:
    """
    Remove a specific line item from the shopping cart.
    Returns True if an item was deleted, False otherwise.
    """
    cart = get_cart(request)
    if not cart:
        return False
    
    deleted_count, _ = CartItem.objects.filter(cart=cart, pk=item_id).delete()
    return deleted_count > 0


@transaction.atomic
def clear_cart(request: HttpRequest) -> None:
    """
    Remove all line items from the current shopping cart.
    """
    cart = get_cart(request)
    if cart:
        cart.items.all().delete()
        if hasattr(cart, "_cached_breakdown"):
            delattr(cart, "_cached_breakdown")


@transaction.atomic
def merge_carts(request: HttpRequest, user: Any) -> Optional[Cart]:
    """
    Safely merge an anonymous guest session cart into an authenticated user's persistent cart.
    Supports ProductVariant matching.
    """
    guest_cart = None
    if isinstance(request, Cart):
        guest_cart = request
    else:
        session_obj = getattr(request, "session", None)
        guest_cart_id = session_obj.get("guest_cart_id") if session_obj else None
        if guest_cart_id:
            guest_cart = Cart.objects.filter(pk=guest_cart_id, user__isnull=True).prefetch_related("items__product", "items__product_variant").first()

        if not guest_cart and session_obj:
            session_key = getattr(session_obj, "session_key", None)
            if session_key:
                guest_cart = Cart.objects.filter(session_key=session_key, user__isnull=True).prefetch_related("items__product", "items__product_variant").first()

    if not guest_cart or guest_cart.user == user:
        return Cart.objects.filter(user=user).first()

    user_cart = Cart.objects.filter(user=user).prefetch_related("items__product", "items__product_variant").first()

    # Case 1: User has no existing cart. Reassign guest cart directly.
    if not user_cart:
        guest_cart.user = user
        guest_cart.session_key = None
        guest_cart.save()
        if "guest_cart_id" in request.session:
            del request.session["guest_cart_id"]
        return guest_cart

    # Case 2: Both guest and user carts exist. Perform line item merge.
    if guest_cart.pk == user_cart.pk:
        return user_cart

    # Map user cart items in memory to eliminate N+1 queries in loop
    user_items_dict = {(item.product_id, getattr(item, "product_variant_id", None)): item for item in user_cart.items.all()}

    adjusted_due_to_stock = False

    for guest_item in guest_cart.items.all():
        product = guest_item.product
        variant = guest_item.product_variant
        if not product.is_active:
            continue
        if variant and not variant.is_active:
            continue

        max_stock = variant.stock_quantity if variant else product.stock_quantity
        if max_stock <= 0:
            continue
        current_price = variant.get_price() if variant else product.price

        user_item = user_items_dict.get((product.id, variant.id if variant else None))
        if user_item:
            merged_quantity = user_item.quantity + guest_item.quantity
            if merged_quantity > max_stock:
                adjusted_due_to_stock = True
            user_item.quantity = min(merged_quantity, max_stock)
            user_item.unit_price = current_price
            user_item.save()
        else:
            merged_quantity = min(guest_item.quantity, max_stock)
            if guest_item.quantity > max_stock:
                adjusted_due_to_stock = True
            CartItem.objects.create(
                cart=user_cart,
                product=product,
                product_variant=variant,
                quantity=merged_quantity,
                unit_price=current_price
            )

    if adjusted_due_to_stock:
        try:
            messages.warning(request, "Some items in your cart were adjusted or removed due to limited stock.")
        except Exception:
            # Prevent failures in test contexts where messages middleware is not loaded
            pass

    guest_cart.delete()
    if "guest_cart_id" in request.session:
        del request.session["guest_cart_id"]
    return user_cart


def calculate_totals(cart: Optional[Cart]) -> Dict[str, Any]:
    """
    Calculate summary statistics and full pricing breakdown for a shopping cart via pricing engine.
    """
    from pricing.services import pricing_breakdown
    return pricing_breakdown(cart)
