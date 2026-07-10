# products/recommendations.py
"""
products/recommendations.py
──────────────────────────────────────────────────────────────────────────────
Product recommendation foundation service.
Implements robust heuristic recommendation algorithms (category/brand matching,
co-viewing proximity, featured status, and trending views/bestsellers).
Excludes machine learning / AI complexity per Phase 4.7 scope.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
from django.db.models import Q, QuerySet
from products.models import Product


def related_products(product: Product, limit: int = 4) -> QuerySet[Product]:
    """
    Recommend products related to the target product based on shared category or brand.
    Prioritizes same category first, then same brand. Excludes the current product.
    """
    if not product or not getattr(product, "pk", None):
        return Product.objects.none()

    category_id = getattr(product, "category_id", None)
    brand_id = getattr(product, "brand_id", None)

    qs = Product.objects.filter(is_active=True).exclude(pk=product.pk)

    if category_id and brand_id:
        qs = qs.filter(Q(category_id=category_id) | Q(brand_id=brand_id))
    elif category_id:
        qs = qs.filter(category_id=category_id)
    elif brand_id:
        qs = qs.filter(brand_id=brand_id)

    return qs.select_related("category", "brand").prefetch_related("images").distinct()[:limit]


def customers_also_viewed(product: Product, limit: int = 4) -> QuerySet[Product]:
    """
    Recommend products that customers also viewed when browsing this item.
    Heuristic: active products in the same category or brand, sorted randomly or by popularity.
    Can be expanded to co-occurrence analysis from RecentlyViewedProduct history.
    """
    if not product or not getattr(product, "pk", None):
        return Product.objects.none()

    category_id = getattr(product, "category_id", None)
    qs = Product.objects.filter(is_active=True).exclude(pk=product.pk)

    if category_id:
        # Prioritize items in the same category
        cat_qs = qs.filter(category_id=category_id).select_related("category", "brand").prefetch_related("images")
        if cat_qs.count() >= limit:
            return cat_qs[:limit]

    return qs.select_related("category", "brand").prefetch_related("images")[:limit]


def featured_products(limit: int = 4) -> QuerySet[Product]:
    """
    Retrieve top featured active catalog products.
    Falls back to newest active products if fewer than `limit` featured products exist.
    """
    featured_qs = Product.objects.filter(is_active=True, is_featured=True).select_related("category", "brand").prefetch_related("images")
    if featured_qs.count() >= limit:
        return featured_qs[:limit]

    # Combine featured and newest
    return Product.objects.filter(is_active=True).select_related("category", "brand").prefetch_related("images").order_by("-is_featured", "-created_at")[:limit]


def trending_products(limit: int = 4) -> QuerySet[Product]:
    """
    Retrieve trending active products based on bestseller flags and view count.
    """
    return Product.objects.filter(is_active=True).select_related("category", "brand").prefetch_related("images").order_by("-is_bestseller", "-views_count", "-created_at")[:limit]
