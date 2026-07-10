# products/recently_viewed.py
"""
products/recently_viewed.py
──────────────────────────────────────────────────────────────────────────────
Service logic for tracking and retrieving recently viewed products.
Supports both guest session tracking and authenticated database persistence
with automatic pruning to 20 maximum items per user/session.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional, List
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from products.models import Product, RecentlyViewedProduct


def track_recently_viewed(request: HttpRequest, product: Product) -> None:
    """
    Record that a user or guest has viewed a product.
    For authenticated users: stores in RecentlyViewedProduct and prunes items beyond the most recent 20.
    For guest users: stores up to 20 unique product IDs in request.session['recently_viewed'].
    """
    if not product or not getattr(product, "is_active", True) or not getattr(product, "pk", None):
        return

    if hasattr(request, "user") and request.user.is_authenticated:
        # Update or create database entry with current timestamp
        RecentlyViewedProduct.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={"viewed_at": timezone.now()}
        )
        # Prune oldest items above 20
        user_items = RecentlyViewedProduct.objects.filter(user=request.user).order_by("-viewed_at")
        if user_items.count() > 20:
            item_ids_to_keep = list(user_items.values_list("pk", flat=True)[:20])
            RecentlyViewedProduct.objects.filter(user=request.user).exclude(pk__in=item_ids_to_keep).delete()
    else:
        # Session-based tracking for guests
        session_obj = getattr(request, "session", None)
        if session_obj is not None:
            recently_viewed: List[int] = session_obj.get("recently_viewed", [])
            # Remove product.pk if it exists so we can re-insert at index 0 (most recent)
            if product.pk in recently_viewed:
                recently_viewed.remove(product.pk)
            recently_viewed.insert(0, product.pk)
            # Prune at 20 items
            recently_viewed = recently_viewed[:20]
            session_obj["recently_viewed"] = recently_viewed
            session_obj.modified = True


def get_recently_viewed(request: HttpRequest, limit: int = 10, exclude_product: Optional[Product] = None) -> QuerySet[Product]:
    """
    Retrieve recently viewed products for the current request (authenticated or guest).
    Returns a prefetched Product QuerySet ordered by most recently viewed.
    """
    exclude_id = exclude_product.pk if exclude_product and exclude_product.pk else None

    if hasattr(request, "user") and request.user.is_authenticated:
        qs = RecentlyViewedProduct.objects.filter(
            user=request.user,
            product__is_active=True
        )
        if exclude_id:
            qs = qs.exclude(product_id=exclude_id)
        
        recent_product_ids = list(qs.order_by("-viewed_at").values_list("product_id", flat=True)[:limit])
    else:
        session_obj = getattr(request, "session", None)
        recent_ids: List[int] = list(session_obj.get("recently_viewed", [])) if session_obj else []
        if exclude_id and exclude_id in recent_ids:
            recent_ids.remove(exclude_id)
        recent_product_ids = recent_ids[:limit]

    if not recent_product_ids:
        return Product.objects.none()

    # Preserve exact viewing order using conditional Case/When sorting
    preserved_order = models.Case(
        *[models.When(pk=pk, then=pos) for pos, pk in enumerate(recent_product_ids)],
        output_field=models.IntegerField()
    )

    return Product.objects.filter(pk__in=recent_product_ids, is_active=True).select_related(
        "category", "brand"
    ).prefetch_related("images").order_by(preserved_order)
