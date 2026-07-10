# wishlist/services.py
"""
wishlist/services.py
──────────────────────────────────────────────────────────────────────────────
Business operations and mutating services for customer wishlists.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Optional, Tuple
from django.db import transaction
from django.http import HttpRequest

from cart.services import add_to_cart
from products.models import Product
from wishlist.models import Wishlist, WishlistItem
from wishlist.selectors import invalidate_user_wishlist_cache


@transaction.atomic
def add_to_wishlist(user: Any, product: Product) -> Tuple[WishlistItem, bool]:
    """
    Adds a product to the customer's wishlist.
    
    Automatically creates a Wishlist for the user if one does not already exist.
    
    Args:
        user: The authenticated user.
        product: The product to save.
        
    Returns:
        Tuple[WishlistItem, bool]: The saved item and whether it was newly created.
        
    Raises:
        ValueError: If user is unauthenticated or product is inactive/missing.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        raise ValueError("User must be authenticated to save items to a wishlist.")
    if not product or not getattr(product, "is_active", True):
        raise ValueError("Cannot add an inactive or invalid product to wishlist.")

    wishlist, _ = Wishlist.objects.get_or_create(user=user)
    item, created = wishlist.items.get_or_create(product=product)
    if created:
        wishlist.save(update_fields=["updated_at"])
        invalidate_user_wishlist_cache(user)
    return item, created


@transaction.atomic
def remove_from_wishlist(user: Any, product: Product) -> bool:
    """
    Removes a product from the customer's wishlist.
    
    Returns:
        bool: True if an item was successfully removed, False otherwise.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated or not product:
        return False
    try:
        wishlist = user.wishlist
    except Wishlist.DoesNotExist:
        return False

    removed = wishlist.remove_product(product)
    if removed:
        invalidate_user_wishlist_cache(user)
    return removed


@transaction.atomic
def clear_wishlist(user: Any) -> int:
    """
    Removes all items from the customer's wishlist.
    
    Returns:
        int: The number of items deleted.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return 0
    try:
        wishlist = user.wishlist
    except Wishlist.DoesNotExist:
        return 0

    count = wishlist.clear()
    if count > 0:
        invalidate_user_wishlist_cache(user)
    return count


@transaction.atomic
def move_wishlist_item_to_cart(request: HttpRequest, product: Product, variant_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Safely transfers a wishlist item directly to the active shopping cart and removes it from the wishlist upon success.
    
    Returns:
        Tuple[bool, str]: (success status, status code/reason e.g. "SUCCESS", "VARIANT_REQUIRED", "OUT_OF_STOCK")
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return False, "UNAUTHENTICATED"
    if not product or not getattr(product, "is_active", True):
        return False, "INACTIVE_PRODUCT"

    # Check if product requires variant selection when variant_id is not specified
    if not variant_id and product.variants.filter(is_active=True).exists():
        return False, "VARIANT_REQUIRED"

    try:
        add_to_cart(request, product_id=product.pk, quantity=1, variant_id=variant_id)
    except Exception as exc:
        err_msg = str(exc)
        if "stock" in err_msg.lower() or "unavailable" in err_msg.lower():
            return False, "OUT_OF_STOCK"
        return False, err_msg

    remove_from_wishlist(request.user, product)
    return True, "SUCCESS"
