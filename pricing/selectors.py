# pricing/selectors.py
"""
pricing/selectors.py
──────────────────────────────────────────────────────────────────────────────
Query selectors for retrieving active coupons and applicable promotions.
All database access for the pricing engine resides here.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Optional
from django.db.models import QuerySet
from django.utils import timezone
from pricing.models import Coupon, Promotion


def get_active_coupons() -> QuerySet[Coupon]:
    """
    Retrieve all coupons that are currently active and within their date/usage windows.
    """
    now = timezone.now()
    return Coupon.objects.filter(
        active=True,
        starts_at__lte=now
    ).exclude(
        expires_at__isnull=False,
        expires_at__lt=now
    )


def coupon_by_code(code: str) -> Optional[Coupon]:
    """
    Retrieve a coupon by its unique code (case-insensitive).
    Returns None if no coupon exists matching the code.
    Cached per code with a 10-minute TTL.
    """
    if not code:
        return None
    clean_code = code.strip().upper()
    from django.core.cache import cache
    cache_key = f"pricing:coupon:{clean_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "NOT_FOUND" else None

    coupon = Coupon.objects.filter(code__iexact=clean_code).first()
    cache.set(cache_key, coupon if coupon else "NOT_FOUND", 600)
    return coupon


def get_applicable_promotions() -> list[Promotion]:
    """
    Retrieve all promotions that are currently active and within their validity timeframe,
    ordered by priority descending so higher priority rules are evaluated first.
    Cached with a 10-minute TTL (`pricing:active_promotions`) to eliminate repetitive queries.
    """
    from django.core.cache import cache
    cached = cache.get("pricing:active_promotions")
    if cached is not None:
        return cached

    now = timezone.now()
    qs = Promotion.objects.filter(
        active=True,
        starts_at__lte=now
    ).exclude(
        expires_at__isnull=False,
        expires_at__lt=now
    ).prefetch_related("categories", "products").order_by("-priority", "-created_at")

    promotions = list(qs)
    cache.set("pricing:active_promotions", promotions, 600)
    return promotions
