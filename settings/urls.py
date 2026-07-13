# settings/urls.py
"""
settings/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing configuration for Store Settings inside the dashboard (`/dashboard/settings/`).
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from .views import (
    BrandingView,
    CurrencyTaxView,
    EmailSettingsView,
    FeatureFlagsView,
    MaintenanceModeView,
    SeoDefaultsView,
    SettingsDashboardView,
    ShippingSettingsView,
    SocialMediaView,
    StorePoliciesView,
    StoreProfileView,
)

app_name = "settings"

urlpatterns = [
    # Dashboard Settings Hub Overview
    path("", SettingsDashboardView.as_view(), name="overview"),

    # Individual Configuration Sections
    path("profile/", StoreProfileView.as_view(), name="profile"),
    path("branding/", BrandingView.as_view(), name="branding"),
    path("currency/", CurrencyTaxView.as_view(), name="currency"),
    path("shipping/", ShippingSettingsView.as_view(), name="shipping"),
    path("email/", EmailSettingsView.as_view(), name="email"),
    path("seo/", SeoDefaultsView.as_view(), name="seo"),
    path("social-media/", SocialMediaView.as_view(), name="social"),
    path("feature-flags/", FeatureFlagsView.as_view(), name="flags"),
    path("maintenance/", MaintenanceModeView.as_view(), name="maintenance"),
    path("policies/", StorePoliciesView.as_view(), name="policies"),
]
