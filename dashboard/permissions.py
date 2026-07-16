# dashboard/permissions.py
"""
dashboard/permissions.py
──────────────────────────────────────────────────────────────────────────────
Centralized Role-Based Access Control (RBAC) and authorization utilities for
the Custom Administration Dashboard.

Implements:
1. Authorization helpers: `has_role`, `has_dashboard_permission`.
2. View decorators: `@staff_required`, `@role_required`, `@dashboard_permission_required`.
3. Class-based view mixins: `StaffRequiredMixin`, `RoleRequiredMixin`, `DashboardPermissionRequiredMixin`.

Ensures that:
- Unauthenticated users are redirected to login (`accounts:login`).
- Non-staff users (`is_staff=False`) are rejected and served a branded
  "Access Denied" response instead of generic HTTP 403 errors.
- Role and permission checks are modular and DRY.
──────────────────────────────────────────────────────────────────────────────
"""

from functools import wraps
from typing import Any, Callable
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import StaffRole


# ─── DEFAULT ROLES DEFINITIONS ────────────────────────────────────────────────
DEFAULT_ROLES_CONFIG = {
    "super_admin": {
        "name": "Super Administrator",
        "description": "Full administrative control across all store operations and settings.",
        "permissions": ["*"],
    },
    "store_manager": {
        "name": "Store Manager",
        "description": "Comprehensive operational control over orders, products, inventory, and customers.",
        "permissions": [
            "orders.view_order", "orders.change_order",
            "products.view_product", "products.add_product", "products.change_product", "products.delete_product",
            "products.view_category", "products.add_category", "products.change_category", "products.delete_category",
            "products.view_brand", "products.add_brand", "products.change_brand", "products.delete_brand",
            "products.view_productvariant", "products.add_productvariant", "products.change_productvariant", "products.delete_productvariant",
            "inventory.view_inventory", "inventory.change_inventory",
            "inventory.adjust_inventory", "inventory.approve_adjustments",
            "inventory.process_returns", "inventory.view_valuation", "inventory.manage_reorder_levels",
            "fulfillment.view_fulfillment", "fulfillment.assign_orders", "fulfillment.pick_orders",
            "fulfillment.pack_orders", "fulfillment.dispatch_orders", "fulfillment.confirm_delivery",
            "fulfillment.manage_returns", "fulfillment.view_shipment_reports",
            "accounts.view_user", "accounts.change_user",
            "dashboard.view_reports", "dashboard.view_marketing",
            "crm.view_customer", "crm.change_customer", "crm.add_staffnote",
            "crm.view_analytics", "crm.export_customerdata",
            "settings.view_storesettings", "settings.change_storesettings",
            "settings.manage_branding", "settings.manage_policies",
            "settings.toggle_maintenance", "settings.manage_featureflags",
        ],
    },
    "inventory_manager": {
        "name": "Inventory Manager",
        "description": "Manages stock levels, reorder alerts, adjustments, and movements.",
        "permissions": [
            "products.view_product",
            "inventory.view_inventory", "inventory.change_inventory",
            "inventory.adjust_inventory", "inventory.approve_adjustments",
            "inventory.process_returns", "inventory.view_valuation", "inventory.manage_reorder_levels",
            "fulfillment.view_fulfillment", "fulfillment.pick_orders", "fulfillment.pack_orders",
            "fulfillment.manage_returns",
        ],
    },
    "fulfillment_manager": {
        "name": "Fulfillment & Logistics Manager",
        "description": "Supervises warehouse picking, packing, shipping dispatch, courier tracking, and RMAs.",
        "permissions": [
            "orders.view_order", "products.view_product",
            "inventory.view_inventory",
            "fulfillment.view_fulfillment", "fulfillment.assign_orders", "fulfillment.pick_orders",
            "fulfillment.pack_orders", "fulfillment.dispatch_orders", "fulfillment.confirm_delivery",
            "fulfillment.manage_returns", "fulfillment.view_shipment_reports",
        ],
    },
    "sales_manager": {
        "name": "Sales Manager",
        "description": "Oversees customer orders, pricing promotions, and revenue metrics.",
        "permissions": [
            "orders.view_order", "orders.change_order",
            "pricing.view_pricing", "pricing.change_pricing",
            "accounts.view_user", "dashboard.view_reports",
            "crm.view_customer", "crm.change_customer", "crm.add_staffnote",
            "crm.view_analytics", "crm.export_customerdata",
        ],
    },
    "customer_support": {
        "name": "Customer Support",
        "description": "Assists customers with order tracking, profile details, and reviews.",
        "permissions": [
            "orders.view_order",
            "accounts.view_user",
            "reviews.view_review", "reviews.change_review",
            "crm.view_customer", "crm.change_customer", "crm.add_staffnote",
        ],
    },
    "marketing_manager": {
        "name": "Marketing Manager",
        "description": "Manages campaigns, customer segmentations, and promotional pricing.",
        "permissions": [
            "pricing.view_pricing", "pricing.change_pricing",
            "accounts.view_user", "dashboard.view_marketing",
            "crm.view_customer", "crm.view_analytics", "crm.export_customerdata",
        ],
    },
    "content_manager": {
        "name": "Content Manager",
        "description": "Curates product descriptions, categories, images, and reviews.",
        "permissions": [
            "products.view_product", "products.add_product", "products.change_product",
            "products.view_category", "products.change_category",
            "reviews.view_review", "reviews.change_review",
        ],
    },
}


# ─── AUTHORIZATION HELPERS ────────────────────────────────────────────────────
def has_role(user: Any, roles: str | list[str] | tuple[str, ...]) -> bool:
    """
    Check if the user is authenticated, has staff access (`is_staff=True`),
    and holds at least one of the specified role codes (or is superuser/super_admin).
    """
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True

    if isinstance(roles, str):
        roles = [roles]

    # Check if user has super_admin role or any of the requested roles
    return user.staff_roles.filter(Q(code="super_admin") | Q(code__in=roles)).exists()


def has_dashboard_permission(user: Any, perm: str) -> bool:
    """
    Check if the staff user has the required permission either via Django's
    built-in permissions or via application-level StaffRole assignments.
    """
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True

    # Check standard Django permission
    if user.has_perm(perm):
        return True

    # Check if any assigned StaffRole grants this permission or is super_admin
    for role in user.staff_roles.all():
        if role.has_permission(perm):
            return True

    return False


def _handle_access_denied(request: HttpRequest) -> HttpResponse:
    """
    Render branded 'Access Denied' response with HTTP status 403 when an
    authenticated non-staff user attempts to access administrative pages.
    """
    return render(request, "dashboard/access_denied.html", status=403)


# ─── DECORATORS ───────────────────────────────────────────────────────────────
def staff_required(view_func: Callable) -> Callable:
    """
    Decorator enforcing that only authenticated staff users (`is_staff=True`)
    can access the view. Redirects unauthenticated users to login, and renders
    branded access denied page for non-staff users.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("accounts:login")
            return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
        if not request.user.is_staff:
            return _handle_access_denied(request)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def role_required(*roles: str) -> Callable:
    """
    Decorator enforcing that the user is staff AND holds at least one of the
    specified role codes (or is Super Administrator).
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                login_url = reverse("accounts:login")
                return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
            if not request.user.is_staff or not has_role(request.user, roles):
                return _handle_access_denied(request)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def dashboard_permission_required(*permissions: str) -> Callable:
    """
    Decorator enforcing that the user is staff AND holds all specified
    permissions across their assigned roles or Django permissions.
    """
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                login_url = reverse("accounts:login")
                return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
            if not request.user.is_staff:
                return _handle_access_denied(request)
            for perm in permissions:
                if not has_dashboard_permission(request.user, perm):
                    return _handle_access_denied(request)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# ─── CLASS-BASED VIEW MIXINS ──────────────────────────────────────────────────
class StaffRequiredMixin:
    """
    View mixin verifying that the current user is authenticated and is staff.
    """
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("accounts:login")
            return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
        if not request.user.is_staff:
            return _handle_access_denied(request)
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class RoleRequiredMixin(StaffRequiredMixin):
    """
    View mixin requiring the user to hold at least one role defined in `required_roles`.
    """
    required_roles: list[str] = []

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("accounts:login")
            return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
        if not request.user.is_staff or not has_role(request.user, self.required_roles):
            return _handle_access_denied(request)
        return super().dispatch(request, *args, **kwargs)


class DashboardPermissionRequiredMixin(StaffRequiredMixin):
    """
    View mixin requiring the user to hold all permissions listed in `required_permissions`.
    """
    required_permissions: list[str] = []

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            login_url = reverse("accounts:login")
            return HttpResponseRedirect(f"{login_url}?{REDIRECT_FIELD_NAME}={request.path}")
        if not request.user.is_staff:
            return _handle_access_denied(request)
        for perm in self.required_permissions:
            if not has_dashboard_permission(request.user, perm):
                return _handle_access_denied(request)
        return super().dispatch(request, *args, **kwargs)
