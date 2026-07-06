# wishlist/selectors.py
"""
wishlist/selectors.py
──────────────────────────────────────────────────────────────────────────────
Read-only queries and caching helpers for customer wishlists.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Optional, Set
from django.core.cache import cache
from django.db.models import QuerySet

from products.models import Product
from wishlist.models import Wishlist, WishlistItem


def get_user_wishlist(user: Any) -> Optional[Wishlist]:
    """
    Returns the wishlist for an authenticated user with all items and product details
    prefetched to prevent N+1 queries. Returns None if unauthenticated or missing.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return None
    return Wishlist.objects.with_products().filter(user=user).first()


def get_wishlist_products(user: Any) -> QuerySet[Product]:
    """
    Returns a QuerySet of active products saved in the user's wishlist, ordered by added_at.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return Product.objects.none()
    
    return (
        Product.objects.filter(
            wishlisted_by__wishlist__user=user,
            is_active=True,
        )
        .select_related("category", "brand")
        .prefetch_related("images")
        .order_by("-wishlisted_by__added_at")
    )


def get_user_wishlist_product_ids(user: Any) -> Set[int]:
    """
    Returns a cached set of product IDs saved in the user's wishlist.
    
    Ensures O(1) in-memory checking in template loops and navbar badges across the entire
    platform without executing any database queries on cache hits.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return set()

    cache_key = f"user_wishlist_ids_{user.id}"
    cached_ids = cache.get(cache_key)
    if cached_ids is not None:
        return cached_ids

    ids = set(
        WishlistItem.objects.filter(wishlist__user=user).values_list("product_id", flat=True)
    )
    # Cache for 15 minutes; automatically cleared by post_save/post_delete signals
    cache.set(cache_key, ids, 900)
    return ids


def wishlist_contains(user: Any, product: Product) -> bool:
    """
    Checks if a specific product is in the user's wishlist using the cached ID set.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated or not product:
        return False
    return product.id in get_user_wishlist_product_ids(user)


def invalidate_user_wishlist_cache(user: Any) -> None:
    """
    Explicitly clears the cached wishlist product IDs for the user.
    Useful after bulk deletions or programmatic mutations.
    """
    if user and hasattr(user, "is_authenticated") and user.is_authenticated:
        cache.delete(f"user_wishlist_ids_{user.id}")
