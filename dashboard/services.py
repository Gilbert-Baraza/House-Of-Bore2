# dashboard/services.py
"""
dashboard/services.py
──────────────────────────────────────────────────────────────────────────────
Business logic and administrative services for the Custom Administration
Dashboard.

Implements:
1. Audit Logging functions (`log_action`, `log_login`, `log_create`, etc.).
2. Dashboard metrics & summary aggregation (`dashboard_statistics`, `get_dashboard_summary`).
3. Notification center operations (`staff_notifications`).
4. RBAC role management (`ensure_default_roles`, `assign_role`).
5. Staff profile update operations (`update_staff_contact`, `update_staff_avatar`, `update_staff_preferences`).
──────────────────────────────────────────────────────────────────────────────
"""

from datetime import timedelta
from typing import Any
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from orders.models import Order, OrderStatus, PaymentStatus
from payments.models import Payment, PaymentStatus as GatewayPaymentStatus
from .models import AuditLog, StaffPreference, StaffRole
from .permissions import DEFAULT_ROLES_CONFIG
from .selectors import (
    average_order_value,
    low_stock_products,
    new_customers,
    orders_today,
    pending_orders,
    processing_orders,
    recent_activity as select_recent_activity,
    recent_orders,
    revenue_today,
    total_customers,
    total_products,
)

User = get_user_model()


# ─── AUDIT LOGGING SERVICES ───────────────────────────────────────────────────
def create_audit_log(
    user: Any,
    action: str,
    description: str,
    model_name: str = "",
    object_id: str = "",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """
    Create and persist an audit log record for an administrative action.
    """
    if user and not user.is_authenticated:
        user = None

    return AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id) if object_id else "",
        description=description,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
    )


def log_action(
    user: Any,
    action: str,
    description: str,
    model_name: str = "",
    object_id: str = "",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Convenience helper for recording custom staff actions."""
    return create_audit_log(
        user=user,
        action=action,
        description=description,
        model_name=model_name,
        object_id=object_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_login(user: Any, ip_address: str | None = None, user_agent: str | None = None) -> AuditLog:
    """Record a staff authentication login event."""
    return create_audit_log(
        user=user,
        action="LOGIN",
        description=f"Staff user {user.email} logged into administrative dashboard.",
        model_name="User",
        object_id=str(user.pk),
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_logout(user: Any, ip_address: str | None = None, user_agent: str | None = None) -> AuditLog:
    """Record a staff authentication logout event."""
    return create_audit_log(
        user=user,
        action="LOGOUT",
        description=f"Staff user {user.email} logged out of administrative dashboard.",
        model_name="User",
        object_id=str(user.pk) if user and hasattr(user, "pk") else "",
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_create(
    user: Any,
    instance: Any,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Record the creation of a new database record by a staff user."""
    model_name = instance.__class__.__name__
    obj_id = str(instance.pk) if hasattr(instance, "pk") else ""
    desc = description or f"Created new {model_name} (ID: {obj_id})."
    return create_audit_log(
        user=user,
        action="CREATE",
        description=desc,
        model_name=model_name,
        object_id=obj_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_update(
    user: Any,
    instance: Any,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Record an update to an existing database record by a staff user."""
    model_name = instance.__class__.__name__
    obj_id = str(instance.pk) if hasattr(instance, "pk") else ""
    desc = description or f"Updated {model_name} (ID: {obj_id})."
    return create_audit_log(
        user=user,
        action="UPDATE",
        description=desc,
        model_name=model_name,
        object_id=obj_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_delete(
    user: Any,
    instance: Any,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Record the deletion of a database record by a staff user."""
    model_name = instance.__class__.__name__
    obj_id = str(instance.pk) if hasattr(instance, "pk") else ""
    desc = description or f"Deleted {model_name} (ID: {obj_id})."
    return create_audit_log(
        user=user,
        action="DELETE",
        description=desc,
        model_name=model_name,
        object_id=obj_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# ─── DASHBOARD STATISTICS & SUMMARY ───────────────────────────────────────────
def dashboard_statistics() -> dict[str, Any]:
    """
    Retrieve aggregated business KPI metrics for the dashboard homepage.
    """
    low_stock_qs = low_stock_products(limit=100)
    low_stock_count = len(low_stock_qs) if isinstance(low_stock_qs, list) else low_stock_qs.count()

    return {
        "revenue_today": revenue_today(),
        "orders_today": orders_today(),
        "pending_orders_count": pending_orders().count(),
        "processing_orders_count": processing_orders().count(),
        "total_products": total_products(),
        "total_customers": total_customers(),
        "low_stock_count": low_stock_count,
        "average_order_value": average_order_value(),
    }


def recent_activity(limit: int = 20) -> list[dict[str, Any]]:
    """
    Retrieve recent timeline activity events from audit logs and formatted
    business records.
    """
    logs = select_recent_activity(limit=limit)
    timeline = []
    for log in logs:
        timeline.append({
            "id": log.pk,
            "action": log.action,
            "model_name": log.model_name,
            "description": log.description,
            "timestamp": log.timestamp,
            "user_email": log.user.email if log.user else "System",
            "icon": _get_action_icon(log.action, log.model_name),
        })
    return timeline


def _get_action_icon(action: str, model_name: str) -> str:
    """Helper returning a Tailwind/heroicon identifier for activity items."""
    if action == "LOGIN":
        return "login"
    if action == "CREATE":
        return "plus-circle"
    if action == "DELETE":
        return "trash"
    if model_name == "Order":
        return "shopping-bag"
    if model_name == "Product":
        return "tag"
    return "check-circle"


def staff_notifications(user: Any = None, limit: int = 15) -> list[dict[str, Any]]:
    """
    Generate actionable staff notifications across inventory, orders, payments,
    and customer registrations.
    """
    notifications = []
    now = timezone.now()

    # 1. Low stock alerts
    low_stock_qs = low_stock_products(limit=5)
    for item in low_stock_qs:
        name = getattr(item, "product_variant", None)
        name_str = name.product.name if name and hasattr(name, "product") else str(item)
        qty = getattr(item, "available_quantity", 0)
        notifications.append({
            "id": f"stock-{getattr(item, 'pk', 0)}",
            "type": "low_stock",
            "type_label": "Low Stock",
            "title": "Low Stock Alert",
            "message": f"{name_str} has only {qty} units remaining in stock.",
            "url": "/dashboard/inventory/",
            "timestamp": now,
            "badge_class": "bg-amber-100 text-amber-800",
        })

    # 2. Pending orders needing attention
    pending_qs = pending_orders()[:5]
    for order in pending_qs:
        notifications.append({
            "id": f"order-{order.pk}",
            "type": "new_order",
            "type_label": "New Order",
            "title": "New Pending Order",
            "message": f"Order #{order.order_number} (${order.grand_total}) requires review or payment confirmation.",
            "url": f"/dashboard/orders/?status=pending",
            "timestamp": order.created_at,
            "badge_class": "bg-blue-100 text-blue-800",
        })

    # 3. Failed payment attempts within last 48 hours
    recent_failed = Payment.objects.filter(
        status=GatewayPaymentStatus.FAILED,
        created_at__gte=now - timedelta(days=2)
    ).select_related("order")[:5]
    for attempt in recent_failed:
        notifications.append({
            "id": f"payment-{attempt.pk}",
            "type": "failed_payment",
            "type_label": "Failed Payment",
            "title": "Payment Failed",
            "message": f"Payment attempt failed for Order #{attempt.order.order_number} (${attempt.amount}).",
            "url": f"/dashboard/orders/",
            "timestamp": attempt.created_at,
            "badge_class": "bg-red-100 text-red-800",
        })

    # 4. Recent customer registrations in last 24 hours
    recent_users = User.objects.filter(
        is_staff=False,
        date_joined__gte=now - timedelta(days=1)
    ).order_by("-date_joined")[:3]
    for c in recent_users:
        notifications.append({
            "id": f"user-{c.pk}",
            "type": "new_customer",
            "type_label": "New Customer",
            "title": "New Customer Registration",
            "message": f"Customer {c.email} joined the House of Bore catalog.",
            "url": "/dashboard/customers/",
            "timestamp": c.date_joined,
            "badge_class": "bg-emerald-100 text-emerald-800",
        })

    # Sort notifications by timestamp descending and slice
    notifications.sort(key=lambda x: x["timestamp"], reverse=True)
    return notifications[:limit]


def get_dashboard_summary() -> dict[str, Any]:
    """
    Aggregate all dashboard statistics, recent records, and notification
    metrics for the main dashboard view.
    """
    return {
        "statistics": dashboard_statistics(),
        "recent_orders": recent_orders(limit=6),
        "new_customers": new_customers(limit=6),
        "activity_feed": recent_activity(limit=8),
        "notifications": staff_notifications(limit=6),
    }


# ─── RBAC & ROLE SERVICES ─────────────────────────────────────────────────────
@transaction.atomic
def ensure_default_roles() -> int:
    """
    Ensure all default application roles are created in the database.
    Idempotent operation safe to run on startup or during tests.
    """
    created_count = 0
    for code, conf in DEFAULT_ROLES_CONFIG.items():
        obj, created = StaffRole.objects.get_or_create(
            code=code,
            defaults={
                "name": conf["name"],
                "description": conf["description"],
                "permissions": conf["permissions"],
            }
        )
        if created:
            created_count += 1
    return created_count


@transaction.atomic
def assign_role(user: Any, role_code: str) -> StaffRole:
    """
    Assign a StaffRole to a user by code. Creates default roles if not existing.
    """
    ensure_default_roles()
    role = StaffRole.objects.get(code=role_code)
    role.users.add(user)
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return role


# ─── STAFF PROFILE SERVICES ───────────────────────────────────────────────────
def get_or_create_staff_preferences(user: Any) -> StaffPreference:
    """Retrieve or create the StaffPreference model for the user."""
    pref, _ = StaffPreference.objects.get_or_create(user=user)
    return pref


@transaction.atomic
def update_staff_contact(user: Any, phone_number: str) -> UserProfile:
    """Update the staff member's contact phone number in UserProfile."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.phone_number = phone_number
    profile.save(update_fields=["phone_number", "updated_at"])
    return profile


@transaction.atomic
def update_staff_avatar(user: Any, avatar_file: Any) -> UserProfile:
    """Update the staff member's avatar image in UserProfile."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.avatar = avatar_file
    profile.save(update_fields=["avatar", "updated_at"])
    return profile


@transaction.atomic
def update_staff_preferences(
    user: Any,
    email_alerts: bool,
    low_stock_alerts: bool,
    new_order_alerts: bool,
    system_notification_alerts: bool,
    dark_mode: bool = False,
) -> StaffPreference:
    """Update the staff member's dashboard settings and notification preferences."""
    pref = get_or_create_staff_preferences(user)
    pref.email_alerts = email_alerts
    pref.low_stock_alerts = low_stock_alerts
    pref.new_order_alerts = new_order_alerts
    pref.system_notification_alerts = system_notification_alerts
    pref.dark_mode = dark_mode
    pref.save()
    return pref
