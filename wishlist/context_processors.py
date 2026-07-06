# wishlist/context_processors.py
"""
wishlist/context_processors.py
──────────────────────────────────────────────────────────────────────────────
Template context processor exposing wishlist status and item count.
──────────────────────────────────────────────────────────────────────────────
"""

from wishlist.selectors import get_user_wishlist_product_ids


def wishlist_status(request):
    """
    Exposes wishlist item count and set of saved product IDs to all templates.
    
    Uses cached product ID sets to guarantee zero database queries across catalog
    grids, product detail pages, and navbar badges on cache hits.
    """
    if hasattr(request, "user") and request.user.is_authenticated:
        ids = get_user_wishlist_product_ids(request.user)
        count = len(ids)
    else:
        ids = set()
        count = 0

    return {
        "wishlist_count": count,
        "user_wishlist_ids": ids,
    }
