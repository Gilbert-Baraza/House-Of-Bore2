# settings/permissions.py
"""
settings/permissions.py
──────────────────────────────────────────────────────────────────────────────
RBAC authorization constants and helpers for the Store Settings module.

Integrates directly with Phase 5.1 RBAC utilities (`dashboard.permissions`).
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Callable
from django.http import HttpRequest, HttpResponse
from dashboard.permissions import (
    DashboardPermissionRequiredMixin,
    dashboard_permission_required,
    has_dashboard_permission,
)

# Permission codenames
VIEW_SETTINGS = "settings.view_storesettings"
MANAGE_STORE_SETTINGS = "settings.change_storesettings"
MANAGE_BRANDING = "settings.manage_branding"
MANAGE_POLICIES = "settings.manage_policies"
TOGGLE_MAINTENANCE_MODE = "settings.toggle_maintenance"
MANAGE_FEATURE_FLAGS = "settings.manage_featureflags"

ALL_SETTINGS_PERMISSIONS = [
    VIEW_SETTINGS,
    MANAGE_STORE_SETTINGS,
    MANAGE_BRANDING,
    MANAGE_POLICIES,
    TOGGLE_MAINTENANCE_MODE,
    MANAGE_FEATURE_FLAGS,
]


class StoreSettingsPermissionMixin(DashboardPermissionRequiredMixin):
    """
    View mixin requiring specific settings permissions.
    If no specific permission is declared on the view, defaults to `VIEW_SETTINGS`.
    """
    required_permissions = [VIEW_SETTINGS]


def can_manage_section(user: Any, permission_code: str) -> bool:
    """
    Check if a staff user has permission to manage a specific settings section.
    """
    return has_dashboard_permission(user, permission_code)


__all__ = [
    "VIEW_SETTINGS",
    "MANAGE_STORE_SETTINGS",
    "MANAGE_BRANDING",
    "MANAGE_POLICIES",
    "TOGGLE_MAINTENANCE_MODE",
    "MANAGE_FEATURE_FLAGS",
    "ALL_SETTINGS_PERMISSIONS",
    "StoreSettingsPermissionMixin",
    "can_manage_section",
    "dashboard_permission_required",
]
