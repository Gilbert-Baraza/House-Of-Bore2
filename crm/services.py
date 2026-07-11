# crm/services.py
"""
crm/services.py
──────────────────────────────────────────────────────────────────────────────
Core business logic and service layer for Customer Relationship Management.
Responsible for constructing 360° customer profile snapshots, unifying multi-channel
interaction timelines, managing private administrative notes, and securely
exporting auditable customer records.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from accounts.models import AccountActivity
from dashboard.services import create_audit_log
from orders.models import Order, OrderStatus
from reviews.models import Review
from wishlist.models import Wishlist, WishlistItem
from .models import CustomerInteractionRecord, CustomerStaffNote

User = get_user_model()


def build_customer_profile(user: User) -> Dict[str, Any]:
    """
    Construct a complete 360° customer profile containing identity, financial KPIs,
    address snapshots, catalog preferences, and recent order activity.
    """
    cache_key = f"crm_customer_profile_360_{user.pk}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Financial & Order metrics
    orders_qs = user.orders.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.FAILED])
    order_metrics = orders_qs.aggregate(
        total_orders=Count("id"),
        lifetime_revenue=Sum("grand_total"),
        avg_order_value=Avg("grand_total"),
    )
    total_orders = order_metrics["total_orders"] or 0
    lifetime_value = order_metrics["lifetime_revenue"] or Decimal("0.00")
    avg_order_value = round(order_metrics["avg_order_value"] or Decimal("0.00"), 2)

    last_order = orders_qs.order_by("-created_at").first()
    last_purchase_date = last_order.created_at if last_order else None
    last_order_number = last_order.order_number if last_order else None

    # Preferred shipping / payment method inference
    preferred_payment = last_order.get_payment_method_display() if hasattr(last_order, "get_payment_method_display") else "Credit Card / PayPal"
    preferred_shipping = last_order.shipping_method if (last_order and hasattr(last_order, "shipping_method")) else "Standard Luxury Express"

    # Wishlist summary
    wishlist = getattr(user, "wishlist", None)
    wishlist_count = wishlist.items.count() if wishlist else 0
    recent_wishlist = list(wishlist.items.select_related("product").order_by("-added_at")[:4]) if wishlist else []

    # Recently viewed / reviewed items
    recent_reviews = list(user.reviews.select_related("product").order_by("-created_at")[:5])

    # Contact & address profiles
    addresses = list(user.addresses.all().order_by("-address_type", "label"))
    primary_phone = ""
    for addr in addresses:
        if addr.phone_number:
            primary_phone = addr.phone_number
            break

    profile_data = {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name() or user.email,
        "phone_number": primary_phone,
        "is_active": user.is_active,
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "receive_marketing": getattr(getattr(user, "profile", None), "receive_marketing", True),
        "total_orders": total_orders,
        "lifetime_value": lifetime_value,
        "average_order_value": avg_order_value,
        "last_purchase_date": last_purchase_date,
        "last_order_number": last_order_number,
        "preferred_payment": preferred_payment,
        "preferred_shipping": preferred_shipping,
        "wishlist_count": wishlist_count,
        "recent_wishlist_items": recent_wishlist,
        "recent_reviews": recent_reviews,
        "addresses": addresses,
    }

    cache.set(cache_key, profile_data, timeout=600)  # 10 minute cache TTL
    return profile_data


def customer_timeline(user: User, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Construct an immutable, timestamped chronological timeline of all customer interactions across
    account authentication, order lifecycle, reviews, wishlists, and administrative staff notes.
    """
    events: List[Dict[str, Any]] = []

    # 1. Account Activity (Registrations, Logins, Password Resets)
    for act in AccountActivity.objects.filter(user=user).order_by("-timestamp")[:30]:
        events.append({
            "id": f"act_{act.pk}",
            "timestamp": act.timestamp,
            "event_type": "security",
            "title": act.get_event_type_display(),
            "description": f"IP: {act.ip_address or 'Unknown'} — {act.user_agent[:60]}",
            "badge_color": "blue",
            "icon": "shield",
        })

    # 2. Order Placements & Lifecycle Events
    for ord_obj in user.orders.all().order_by("-created_at")[:30]:
        events.append({
            "id": f"ord_{ord_obj.pk}",
            "timestamp": ord_obj.created_at,
            "event_type": "order",
            "title": f"Order #{ord_obj.order_number} Placed",
            "description": f"Grand Total: ${ord_obj.grand_total} USD ({ord_obj.item_count} items) — Status: {ord_obj.get_status_display()}",
            "badge_color": "emerald" if ord_obj.status == OrderStatus.PAID else "amber",
            "icon": "shopping-bag",
            "url": f"/dashboard/orders/{ord_obj.order_number}/",
        })
        if ord_obj.status == OrderStatus.DELIVERED:
            events.append({
                "id": f"ord_del_{ord_obj.pk}",
                "timestamp": ord_obj.updated_at,
                "event_type": "fulfillment",
                "title": f"Order #{ord_obj.order_number} Delivered",
                "description": "Garment shipment confirmed delivered to patron address.",
                "badge_color": "neutral",
                "icon": "check-circle",
            })
        elif ord_obj.status == OrderStatus.CANCELLED or ord_obj.payment_status == PaymentStatus.REFUNDED:
            events.append({
                "id": f"ord_ret_{ord_obj.pk}",
                "timestamp": ord_obj.updated_at,
                "event_type": "return",
                "title": f"Order #{ord_obj.order_number} {ord_obj.get_status_display()}",
                "description": getattr(ord_obj, "notes", "") or "Return or cancellation processed.",
                "badge_color": "rose",
                "icon": "refresh-cw",
            })

    # 3. Product Reviews
    for rev in user.reviews.select_related("product").order_by("-created_at")[:20]:
        events.append({
            "id": f"rev_{rev.pk}",
            "timestamp": rev.created_at,
            "event_type": "review",
            "title": f"Submitted {rev.rating}-Star Review for {rev.product.name}",
            "description": rev.title or rev.comment[:100],
            "badge_color": "purple",
            "icon": "star",
        })

    # 4. Wishlist Additions
    if hasattr(user, "wishlist") and user.wishlist:
        for witem in user.wishlist.items.select_related("product").order_by("-added_at")[:15]:
            events.append({
                "id": f"wish_{witem.pk}",
                "timestamp": witem.added_at,
                "event_type": "wishlist",
                "title": f"Added to Wishlist: {witem.product.name}",
                "description": f"Catalog price: ${witem.product.price} USD",
                "badge_color": "indigo",
                "icon": "heart",
            })

    # 5. Internal Staff Notes & Concierge Interactions
    for note in user.staff_notes.select_related("author").order_by("-created_at")[:20]:
        events.append({
            "id": f"note_{note.pk}",
            "timestamp": note.created_at,
            "event_type": "staff_note",
            "title": f"Internal Note Added ({note.get_category_display()})",
            "description": f'"{note.note}" — By {note.author.email if note.author else "System"}',
            "badge_color": "amber",
            "icon": "lock",
        })

    for irec in user.interaction_records.select_related("performed_by").order_by("-timestamp")[:20]:
        events.append({
            "id": f"irec_{irec.pk}",
            "timestamp": irec.timestamp,
            "event_type": "interaction",
            "title": f"Concierge Contact: {irec.get_interaction_type_display()}",
            "description": f"{irec.summary} — By {irec.performed_by.email if irec.performed_by else 'System'}",
            "badge_color": "emerald",
            "icon": "phone",
        })

    # Sort all events descending by timestamp
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[:limit]


@transaction.atomic
def add_staff_note(
    customer: User,
    author: User,
    note: str,
    category: str = "general",
    is_pinned: bool = False,
) -> CustomerStaffNote:
    """
    Persist a private administrative note attached to a customer profile,
    record an audit log, and clear cached customer summaries.
    """
    note = note.strip()
    if not note:
        raise ValueError("Staff note text cannot be empty.")

    staff_note = CustomerStaffNote.objects.create(
        customer=customer,
        author=author,
        note=note,
        category=category,
        is_pinned=is_pinned,
    )

    create_audit_log(
        user=author,
        action="CREATE",
        model_name="CustomerStaffNote",
        object_id=str(staff_note.pk),
        description=f"Added private {staff_note.get_category_display()} note for patron {customer.email}.",
    )

    cache.delete(f"crm_customer_profile_360_{customer.pk}")
    return staff_note


@transaction.atomic
def log_customer_interaction(
    customer: User,
    performed_by: User,
    interaction_type: str,
    summary: str,
    details: str = "",
    timestamp: Optional[Any] = None,
) -> CustomerInteractionRecord:
    """
    Record manual offline or concierge correspondence (phone call, email, salon visit).
    """
    summary = summary.strip()
    if not summary:
        raise ValueError("Interaction summary cannot be empty.")

    record = CustomerInteractionRecord.objects.create(
        customer=customer,
        performed_by=performed_by,
        interaction_type=interaction_type,
        summary=summary,
        details=details.strip(),
        timestamp=timestamp or timezone.now(),
    )

    create_audit_log(
        user=performed_by,
        action="CREATE",
        model_name="CustomerInteractionRecord",
        object_id=str(record.pk),
        description=f"Logged {record.get_interaction_type_display()} interaction for patron {customer.email}.",
    )
    cache.delete(f"crm_customer_profile_360_{customer.pk}")
    return record


def export_customer_data(user: User, performed_by: User) -> Dict[str, Any]:
    """
    Generate an auditable, secure JSON bundle containing the 360° customer profile,
    order history, address book, and reviews. Omits internal staff notes unless
    the requesting staff member possesses the 'crm.add_staffnote' permission.
    """
    profile = build_customer_profile(user)
    
    # Order ledger
    orders_data = []
    for ord_obj in user.orders.prefetch_related("items").all().order_by("-created_at"):
        orders_data.append({
            "order_number": ord_obj.order_number,
            "status": ord_obj.get_status_display(),
            "payment_status": ord_obj.get_payment_status_display(),
            "subtotal": str(ord_obj.subtotal),
            "shipping_total": str(ord_obj.shipping_total),
            "tax_total": str(ord_obj.tax_total),
            "grand_total": str(ord_obj.grand_total),
            "created_at": ord_obj.created_at.isoformat(),
            "items": [
                {"sku": i.sku, "product_name": i.product_name, "quantity": i.quantity, "line_total": str(i.line_total)}
                for i in ord_obj.items.all()
            ],
        })

    # Address book
    addresses_data = [
        {
            "label": addr.label,
            "recipient_name": addr.recipient_name,
            "phone_number": addr.phone_number,
            "address_line_1": addr.address_line_1,
            "city": addr.city,
            "county_or_state": addr.county_or_state,
            "postal_code": addr.postal_code,
            "country": addr.country,
        }
        for addr in user.addresses.all()
    ]

    # Reviews
    reviews_data = [
        {
            "product": rev.product.name,
            "rating": rev.rating,
            "title": rev.title,
            "comment": rev.comment,
            "created_at": rev.created_at.isoformat(),
        }
        for rev in user.reviews.select_related("product").all()
    ]

    export_bundle = {
        "export_metadata": {
            "generated_at": timezone.now().isoformat(),
            "performed_by": performed_by.email,
            "subject_account_id": user.pk,
            "subject_email": user.email,
        },
        "identity_profile": {
            "first_name": profile["first_name"],
            "last_name": profile["last_name"],
            "email": profile["email"],
            "phone_number": profile["phone_number"],
            "date_joined": profile["date_joined"].isoformat() if profile["date_joined"] else None,
            "receive_marketing": profile["receive_marketing"],
        },
        "financial_summary": {
            "total_orders": profile["total_orders"],
            "lifetime_value_usd": str(profile["lifetime_value"]),
            "average_order_value_usd": str(profile["average_order_value"]),
        },
        "addresses": addresses_data,
        "orders": orders_data,
        "reviews": reviews_data,
    }

    # Only include internal staff notes if user has explicit note authorization
    if performed_by.has_perm("crm.add_staffnote") or performed_by.is_superuser:
        export_bundle["internal_staff_notes"] = [
            {
                "id": note.pk,
                "author": note.author.email if note.author else "System",
                "category": note.get_category_display(),
                "note": note.note,
                "is_pinned": note.is_pinned,
                "created_at": note.created_at.isoformat(),
            }
            for note in user.staff_notes.select_related("author").all().order_by("-created_at")
        ]

    create_audit_log(
        user=performed_by,
        action="EXPORT",
        model_name="User",
        object_id=str(user.pk),
        description=f"Exported 360° customer data bundle for patron {user.email}.",
    )

    return export_bundle
