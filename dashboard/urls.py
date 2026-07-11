# dashboard/urls.py
"""
dashboard/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing configuration for the Custom Administration Dashboard.

Registers routes for:
- Dashboard Homepage (`/dashboard/`)
- Staff Profile Management (`/dashboard/profile/` and POST handlers)
- Notification Center (`/dashboard/notifications/`)
- Branded Access Denied page (`/dashboard/access-denied/`)
- Navigation section placeholders (`/dashboard/orders/`, `/dashboard/products/`, etc.)
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import include, path
from crm.views import CustomerListView
from .order_views import (
    StaffOrderCreateFulfillmentView,
    StaffOrderDetailView,
    StaffOrderNotesUpdateView,
    StaffOrdersListView,
    StaffOrderTransitionView,
)
from .views import (
    AccessDeniedView,
    DashboardHomeView,
    NotificationListView,
    StaffAvatarUpdateView,
    StaffContactUpdateView,
    StaffMarketingView,
    StaffPreferencesUpdateView,
    StaffProductsView,
    StaffProfileView,
    StaffReportsView,
    StaffSettingsView,
    StaffUsersView,
)

app_name = "dashboard"

urlpatterns = [
    # Dashboard Home
    path("", DashboardHomeView.as_view(), name="home"),

    # Staff Profile & Preferences
    path("profile/", StaffProfileView.as_view(), name="profile"),
    path("profile/contact/", StaffContactUpdateView.as_view(), name="profile_contact"),
    path("profile/avatar/", StaffAvatarUpdateView.as_view(), name="profile_avatar"),
    path("profile/preferences/", StaffPreferencesUpdateView.as_view(), name="profile_preferences"),

    # Notification Center
    path("notifications/", NotificationListView.as_view(), name="notifications"),

    # Security & Error Handling
    path("access-denied/", AccessDeniedView.as_view(), name="access_denied"),

    # Orders Management (Full Administrative Control)
    path("orders/", StaffOrdersListView.as_view(), name="orders"),
    path("orders/<str:order_number>/", StaffOrderDetailView.as_view(), name="order_detail"),
    path("orders/<str:order_number>/transition/", StaffOrderTransitionView.as_view(), name="order_transition"),
    path("orders/<str:order_number>/notes/", StaffOrderNotesUpdateView.as_view(), name="order_notes"),
    path("orders/<str:order_number>/create-fulfillment/", StaffOrderCreateFulfillmentView.as_view(), name="order_create_fulfillment"),

    # Customer Relationship Management (CRM Module)
    path("crm/", include("crm.urls")),
    path("customers/", CustomerListView.as_view(), name="customers"),

    # Staff Navigation Section Placeholders
    path("products/", StaffProductsView.as_view(), name="products"),
    path("marketing/", StaffMarketingView.as_view(), name="marketing"),
    path("reports/", StaffReportsView.as_view(), name="reports"),
    path("settings/", StaffSettingsView.as_view(), name="settings"),
    path("users/", StaffUsersView.as_view(), name="users"),
]
