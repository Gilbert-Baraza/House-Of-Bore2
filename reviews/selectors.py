# reviews/selectors.py
"""
reviews/selectors.py
──────────────────────────────────────────────────────────────────────────────
Read-only queries and aggregations for product reviews and ratings.

Encapsulates all database querying logic for reviews to maintain thin views
and prevent N+1 performance bottlenecks.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.db.models import Avg, Count, Q, QuerySet

from products.models import Product
from reviews.models import Review


def get_product_reviews(product: Product, approved_only: bool = True) -> QuerySet[Review]:
    """
    Returns a QuerySet of reviews for a given product.
    
    Uses select_related('user') to prevent N+1 queries when displaying author info.
    """
    qs = Review.objects.filter(product=product).select_related("user")
    if approved_only:
        qs = qs.filter(is_approved=True)
    return qs.order_by("-created_at")


def get_review_summary(product: Product) -> Dict[str, Any]:
    """
    Calculates aggregate review statistics for a product in a SINGLE database query.
    
    Returns:
        Dict containing:
            - average_rating: Decimal (e.g. 4.8 or 0.0)
            - review_count: int
            - five_star_count: int
            - four_star_count: int
            - three_star_count: int
            - two_star_count: int
            - one_star_count: int
            - rating_breakdown: dict mapping star (5..1) to count and percentage.
    
    Results are cached in Redis/memory and automatically invalidated via signals
    when a review is added, edited, or removed.
    """
    cache_key = f"product_review_summary_{product.id}"
    cached_summary = cache.get(cache_key)
    if cached_summary is not None:
        return cached_summary

    stats = Review.objects.filter(product=product, is_approved=True).aggregate(
        avg_rating=Avg("rating"),
        total_count=Count("id"),
        count_5=Count("id", filter=Q(rating=5)),
        count_4=Count("id", filter=Q(rating=4)),
        count_3=Count("id", filter=Q(rating=3)),
        count_2=Count("id", filter=Q(rating=2)),
        count_1=Count("id", filter=Q(rating=1)),
    )

    total_count = stats["total_count"] or 0
    raw_avg = stats["avg_rating"] or 0.0
    
    # Format average rating to 1 decimal place as Decimal
    avg_rating = Decimal(str(raw_avg)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if total_count > 0 else Decimal("0.0")

    def calc_pct(count: int) -> int:
        if total_count == 0:
            return 0
        return int(round((count / total_count) * 100))

    c5 = stats["count_5"] or 0
    c4 = stats["count_4"] or 0
    c3 = stats["count_3"] or 0
    c2 = stats["count_2"] or 0
    c1 = stats["count_1"] or 0

    rating_breakdown = {
        5: {"count": c5, "percentage": calc_pct(c5)},
        4: {"count": c4, "percentage": calc_pct(c4)},
        3: {"count": c3, "percentage": calc_pct(c3)},
        2: {"count": c2, "percentage": calc_pct(c2)},
        1: {"count": c1, "percentage": calc_pct(c1)},
    }

    summary = {
        "average_rating": avg_rating,
        "review_count": total_count,
        "five_star_count": c5,
        "four_star_count": c4,
        "three_star_count": c3,
        "two_star_count": c2,
        "one_star_count": c1,
        "rating_breakdown": rating_breakdown,
    }

    # Cache for 15 minutes (invalidation signals will clear earlier if needed)
    cache.set(cache_key, summary, 900)
    return summary


def get_user_review(product: Product, user: Any) -> Optional[Review]:
    """
    Returns an authenticated user's existing review for a product (even if unapproved,
    so they can edit/see their submission), or None if no review exists.
    """
    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        return None
    return Review.objects.filter(product=product, user=user).first()
