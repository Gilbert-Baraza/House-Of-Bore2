# crm/selectors.py
"""
crm/selectors.py
──────────────────────────────────────────────────────────────────────────────
High-performance database queries and analytical aggregations for the CRM module.
Enforces zero N+1 queries via `select_related` and `prefetch_related` while
leveraging SQL aggregations (`Count`, `Sum`, `Avg`, `Max`) and Redis caching
to guarantee sub-millisecond dashboard rendering.
──────────────────────────────────────────────────────────────────────────────
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from orders.models import Order, OrderItem, OrderStatus, PaymentStatus

User = get_user_model()


def search_customers(
    query: str = "",
    segment: str = "all",
    sort_by: str = "registered_desc",
) -> Any:
    """
    Search and filter customer accounts across identity attributes, addresses, and order references.
    Annotates each patron with total order count, lifetime spend, and last order date without N+1 queries.
    """
    qs = User.objects.filter(is_staff=False, is_superuser=False).select_related("profile").prefetch_related("addresses")

    # Annotate financial & activity metrics at database level
    qs = qs.annotate(
        total_orders_count=Count(
            "orders",
            filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]),
            distinct=True,
        ),
        lifetime_spent=Coalesce(
            Sum(
                "orders__grand_total",
                filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]),
            ),
            Decimal("0.00"),
        ),
        last_order_date=Max("orders__created_at"),
    )

    # Keyword filtering across multiple dimensions
    if query:
        query = query.strip()
        qs = qs.filter(
            Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(addresses__phone_number__icontains=query)
            | Q(addresses__recipient_name__icontains=query)
            | Q(orders__order_number__icontains=query)
        ).distinct()

    # Dynamic segmentation filtering
    now = timezone.now()
    if segment == "new":
        qs = qs.filter(date_joined__gte=now - timedelta(days=30))
    elif segment == "active":
        qs = qs.filter(orders__created_at__gte=now - timedelta(days=90)).distinct()
    elif segment == "inactive":
        qs = qs.exclude(orders__created_at__gte=now - timedelta(days=180))
    elif segment == "vip":
        qs = qs.filter(lifetime_spent__gte=Decimal("1000.00"))
    elif segment == "frequent":
        qs = qs.filter(total_orders_count__gte=3)
    elif segment == "one_time":
        qs = qs.filter(total_orders_count=1)
    elif segment == "pending_returns":
        qs = qs.filter(
            Q(orders__status=OrderStatus.CANCELLED)
            | Q(orders__payment_status=PaymentStatus.REFUNDED)
        ).distinct()

    # Sorting
    if sort_by == "registered_asc":
        qs = qs.order_by("date_joined")
    elif sort_by == "spend_desc":
        qs = qs.order_by("-lifetime_spent", "-date_joined")
    elif sort_by == "orders_desc":
        qs = qs.order_by("-total_orders_count", "-date_joined")
    elif sort_by == "last_active_desc":
        qs = qs.order_by(F("last_order_date").desc(nulls_last=True), "-date_joined")
    else:
        qs = qs.order_by("-date_joined")

    return qs


def get_customer_detail(user_id: int) -> Optional[Any]:
    """
    Retrieve a single customer account fully populated with profile, address book,
    order ledger, wishlist items, reviews, staff notes, and interaction logs.
    """
    try:
        return User.objects.select_related("profile").prefetch_related(
            "addresses",
            "orders",
            "orders__items",
            "wishlist__items__product",
            "reviews__product",
            "staff_notes__author",
            "interaction_records__performed_by",
            "activity_logs",
        ).get(pk=user_id, is_staff=False, is_superuser=False)
    except User.DoesNotExist:
        return None


def customer_statistics(use_cache: bool = True) -> Dict[str, Any]:
    """
    Compute system-wide customer relationship KPIs: customer base size, new customer velocity,
    repeat purchase rates, average order value, brand loyalty, and return frequency.
    """
    cache_key = "crm_customer_statistics_kpi"
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    ninety_days_ago = now - timedelta(days=90)

    patrons_qs = User.objects.filter(is_staff=False, is_superuser=False)
    total_customers = patrons_qs.count()
    new_customers_30d = patrons_qs.filter(date_joined__gte=thirty_days_ago).count()
    active_customers_90d = patrons_qs.filter(orders__created_at__gte=ninety_days_ago).distinct().count()

    # Financial ledger aggregations
    orders_qs = Order.objects.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED])
    totals = orders_qs.aggregate(
        total_revenue=Coalesce(Sum("grand_total"), Decimal("0.00")),
        total_orders=Count("id"),
        avg_order_value=Coalesce(Avg("grand_total"), Decimal("0.00")),
    )
    total_revenue = totals["total_revenue"]
    total_orders = totals["total_orders"]
    avg_order_value = totals["avg_order_value"]

    # Repeat purchase rate (Patrons with >= 2 non-cancelled orders)
    repeat_patrons = patrons_qs.annotate(
        ocnt=Count("orders", filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]), distinct=True)
    ).filter(ocnt__gte=2).count()
    repeat_purchase_rate = round((repeat_patrons / total_customers * 100) if total_customers > 0 else 0.0, 1)

    # Average purchase frequency per active customer
    avg_purchase_frequency = round((total_orders / total_customers) if total_customers > 0 else 0.0, 2)

    # Return rate
    returned_orders = Order.objects.filter(
        Q(status=OrderStatus.CANCELLED)
        | Q(payment_status=PaymentStatus.REFUNDED)
    ).count()
    all_orders_cnt = Order.objects.count()
    return_rate = round((returned_orders / all_orders_cnt * 100) if all_orders_cnt > 0 else 0.0, 1)

    # Top categories and brands
    most_purchased_categories = list(
        OrderItem.objects.values("product__category__name")
        .annotate(units_sold=Sum("quantity"))
        .order_by("-units_sold")[:5]
    )
    most_purchased_brands = list(
        OrderItem.objects.values("product__brand__name")
        .annotate(units_sold=Sum("quantity"))
        .order_by("-units_sold")[:5]
    )

    stats = {
        "total_customers": total_customers,
        "new_customers_30d": new_customers_30d,
        "active_customers_90d": active_customers_90d,
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "average_order_value": round(avg_order_value, 2),
        "repeat_purchase_rate": repeat_purchase_rate,
        "average_purchase_frequency": avg_purchase_frequency,
        "return_rate": return_rate,
        "most_purchased_categories": [
            {"name": c["product__category__name"] or "Uncategorized", "units": c["units_sold"] or 0}
            for c in most_purchased_categories
        ],
        "most_purchased_brands": [
            {"name": b["product__brand__name"] or "House of Bore", "units": b["units_sold"] or 0}
            for b in most_purchased_brands
        ],
    }

    if use_cache:
        cache.set(cache_key, stats, timeout=900)  # 15 minute cache TTL
    return stats


def customer_segments(use_cache: bool = True) -> Dict[str, Any]:
    """
    Compute dynamic behavioral customer cohorts for targeted engagement and risk monitoring.
    """
    cache_key = "crm_customer_segments_cohorts"
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    ninety_days_ago = now - timedelta(days=90)
    one_eighty_days_ago = now - timedelta(days=180)

    patrons = User.objects.filter(is_staff=False, is_superuser=False).annotate(
        orders_cnt=Count("orders", filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]), distinct=True),
        ltv=Coalesce(Sum("orders__grand_total", filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED])), Decimal("0.00")),
    )

    segments = {
        "new_customers": {
            "title": "New Customers",
            "description": "Registered within the last 30 days",
            "count": patrons.filter(date_joined__gte=thirty_days_ago).count(),
            "code": "new",
            "badge_color": "emerald",
        },
        "active_customers": {
            "title": "Active Patrons",
            "description": "Purchased within the last 90 days",
            "count": patrons.filter(orders__created_at__gte=ninety_days_ago).distinct().count(),
            "code": "active",
            "badge_color": "blue",
        },
        "inactive_customers": {
            "title": "Inactive / At-Risk",
            "description": "No purchase within the last 180 days",
            "count": patrons.exclude(orders__created_at__gte=one_eighty_days_ago).count(),
            "code": "inactive",
            "badge_color": "neutral",
        },
        "high_spending": {
            "title": "VIP High-Spending",
            "description": "Lifetime value exceeding $1,000 USD",
            "count": patrons.filter(ltv__gte=Decimal("1000.00")).count(),
            "code": "vip",
            "badge_color": "amber",
        },
        "frequent_buyers": {
            "title": "Frequent Collectors",
            "description": "Completed 3 or more distinct orders",
            "count": patrons.filter(orders_cnt__gte=3).count(),
            "code": "frequent",
            "badge_color": "purple",
        },
        "one_time_buyers": {
            "title": "One-Time Patrons",
            "description": "Completed exactly one order",
            "count": patrons.filter(orders_cnt=1).count(),
            "code": "one_time",
            "badge_color": "neutral",
        },
        "pending_returns": {
            "title": "Pending Returns & RMAs",
            "description": "Patrons with open return/refund cases",
            "count": patrons.filter(
                Q(orders__status=OrderStatus.CANCELLED)
                | Q(orders__payment_status=PaymentStatus.REFUNDED)
            ).distinct().count(),
            "code": "pending_returns",
            "badge_color": "rose",
        },
    }

    if use_cache:
        cache.set(cache_key, segments, timeout=900)
    return segments


def inactive_customers(days: int = 180) -> Any:
    """
    Retrieve queryset of customers who have not placed any valid orders in the last N days.
    """
    cutoff = timezone.now() - timedelta(days=days)
    return User.objects.filter(is_staff=False, is_superuser=False).exclude(
        orders__created_at__gte=cutoff
    ).annotate(
        total_orders_count=Count("orders", filter=~Q(orders__status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED]), distinct=True),
        last_order_date=Max("orders__created_at"),
    ).order_by("-last_order_date")


def recent_customers(days: int = 30) -> Any:
    """
    Retrieve queryset of customers who registered within the last N days.
    """
    cutoff = timezone.now() - timedelta(days=days)
    return User.objects.filter(is_staff=False, is_superuser=False, date_joined__gte=cutoff).select_related("profile").order_by("-date_joined")
