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
from .product_views import (
    StaffBrandCreateView,
    StaffBrandDeleteView,
    StaffBrandUpdateView,
    StaffBrandsListView,
    StaffCategoriesListView,
    StaffCategoryCreateView,
    StaffCategoryDeleteView,
    StaffCategoryUpdateView,
    StaffOptionCreateView,
    StaffOptionValueCreateView,
    StaffOptionValueDeleteView,
    StaffOptionsListView,
    StaffProductCreateView,
    StaffProductDeleteView,
    StaffProductImageDeleteView,
    StaffProductImageMakePrimaryView,
    StaffProductImageUploadView,
    StaffProductsListView,
    StaffProductToggleActiveView,
    StaffProductUpdateView,
    StaffProductVariantCreateView,
    StaffProductVariantDeleteView,
    StaffProductVariantUpdateView,
)
from .views import (
    AccessDeniedView,
    DashboardHomeView,
    NotificationListView,
    StaffAvatarUpdateView,
    StaffContactUpdateView,
    StaffMarketingView,
    StaffPreferencesUpdateView,
    StaffProfileView,
    StaffReportsView,
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

    # Catalog & Product Management
    path("products/", StaffProductsListView.as_view(), name="products"),
    path("products/add/", StaffProductCreateView.as_view(), name="product_add"),
    path("products/<int:pk>/edit/", StaffProductUpdateView.as_view(), name="product_edit"),
    path("products/<int:pk>/delete/", StaffProductDeleteView.as_view(), name="product_delete"),
    path("products/<int:pk>/toggle-active/", StaffProductToggleActiveView.as_view(), name="product_toggle_active"),

    # Product Gallery Images
    path("products/<int:pk>/images/add/", StaffProductImageUploadView.as_view(), name="product_image_add"),
    path("products/images/<int:image_id>/delete/", StaffProductImageDeleteView.as_view(), name="product_image_delete"),
    path("products/images/<int:image_id>/make-primary/", StaffProductImageMakePrimaryView.as_view(), name="product_image_make_primary"),

    # Product Variants & SKUs
    path("products/<int:pk>/variants/add/", StaffProductVariantCreateView.as_view(), name="product_variant_add"),
    path("products/variants/<int:variant_id>/edit/", StaffProductVariantUpdateView.as_view(), name="product_variant_edit"),
    path("products/variants/<int:variant_id>/delete/", StaffProductVariantDeleteView.as_view(), name="product_variant_delete"),

    # Categories Management
    path("products/categories/", StaffCategoriesListView.as_view(), name="categories"),
    path("products/categories/add/", StaffCategoryCreateView.as_view(), name="category_add"),
    path("products/categories/<int:pk>/edit/", StaffCategoryUpdateView.as_view(), name="category_edit"),
    path("products/categories/<int:pk>/delete/", StaffCategoryDeleteView.as_view(), name="category_delete"),

    # Brands Management
    path("products/brands/", StaffBrandsListView.as_view(), name="brands"),
    path("products/brands/add/", StaffBrandCreateView.as_view(), name="brand_add"),
    path("products/brands/<int:pk>/edit/", StaffBrandUpdateView.as_view(), name="brand_edit"),
    path("products/brands/<int:pk>/delete/", StaffBrandDeleteView.as_view(), name="brand_delete"),

    # Product Options & Values Management
    path("products/options/", StaffOptionsListView.as_view(), name="options"),
    path("products/options/add/", StaffOptionCreateView.as_view(), name="option_add"),
    path("products/options/<int:option_id>/values/add/", StaffOptionValueCreateView.as_view(), name="option_value_add"),
    path("products/options/values/<int:value_id>/delete/", StaffOptionValueDeleteView.as_view(), name="option_value_delete"),

    # Staff Navigation Section Placeholders
    path("marketing/", StaffMarketingView.as_view(), name="marketing"),
    path("reports/", StaffReportsView.as_view(), name="reports"),
    path("settings/", include("settings.urls", namespace="settings")),
    path("users/", StaffUsersView.as_view(), name="users"),
]
