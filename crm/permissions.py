# crm/permissions.py
"""
crm/permissions.py
──────────────────────────────────────────────────────────────────────────────
Access control mixins and permission verification helpers for CRM endpoints.
Enforces strict segregation of duties across staff roles (Store Manager, Sales,
Support, Marketing, and Super Admin).
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from dashboard.permissions import DashboardPermissionRequiredMixin, has_dashboard_permission

CRM_VIEW_PERMISSION = "crm.view_customer"
CRM_CHANGE_PERMISSION = "crm.change_customer"
CRM_NOTE_PERMISSION = "crm.add_staffnote"
CRM_ANALYTICS_PERMISSION = "crm.view_analytics"
CRM_EXPORT_PERMISSION = "crm.export_customerdata"


class CRMPermissionRequiredMixin(DashboardPermissionRequiredMixin):
    """
    Base view mixin enforcing that the requesting staff member holds the core
    CRM viewing permission ('crm.view_customer').
    """
    required_permissions = [CRM_VIEW_PERMISSION]


def can_view_customer(user: Any) -> bool:
    return has_dashboard_permission(user, CRM_VIEW_PERMISSION)


def can_change_customer(user: Any) -> bool:
    return has_dashboard_permission(user, CRM_CHANGE_PERMISSION)


def can_add_staff_note(user: Any) -> bool:
    return has_dashboard_permission(user, CRM_NOTE_PERMISSION)


def can_view_analytics(user: Any) -> bool:
    return has_dashboard_permission(user, CRM_ANALYTICS_PERMISSION)


def can_export_customer_data(user: Any) -> bool:
    return has_dashboard_permission(user, CRM_EXPORT_PERMISSION)
