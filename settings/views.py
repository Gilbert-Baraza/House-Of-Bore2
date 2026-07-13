# settings/views.py
"""
settings/views.py
──────────────────────────────────────────────────────────────────────────────
Thin dashboard presentation views for managing Store Settings.

Enforces Role-Based Access Control via `StoreSettingsPermissionMixin` and specific
section permissions (`MANAGE_BRANDING`, `MANAGE_POLICIES`, `TOGGLE_MAINTENANCE_MODE`, etc.).
Delegates data updates to `services.py` and queries to `selectors.py`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import TemplateView, View

from .forms import (
    BrandingForm,
    CurrencyTaxForm,
    EmailSettingsForm,
    FeatureFlagsForm,
    MaintenanceModeForm,
    SeoDefaultsForm,
    ShippingSettingsForm,
    SocialMediaForm,
    StorePoliciesForm,
    StoreProfileForm,
)
from .permissions import (
    MANAGE_BRANDING,
    MANAGE_FEATURE_FLAGS,
    MANAGE_POLICIES,
    MANAGE_STORE_SETTINGS,
    TOGGLE_MAINTENANCE_MODE,
    VIEW_SETTINGS,
    StoreSettingsPermissionMixin,
)
from .selectors import get_store_settings
from .services import update_store_file_asset, update_store_settings


def get_client_ip(request: HttpRequest) -> str | None:
    """
    Extract accurate client IP address, supporting reverse proxies (`X-Forwarded-For` / `X-Real-IP`).
    """
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip.strip()
    return request.META.get("REMOTE_ADDR")


class BaseSettingsSectionView(StoreSettingsPermissionMixin, View):
    """
    Abstract base view for GET/POST forms modifying a single StoreSettings section.
    """
    form_class: Any = None
    template_name: str = ""
    section_title: str = ""
    section_code: str = ""
    file_fields: list[str] = []
    required_permissions = [MANAGE_STORE_SETTINGS]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        instance = get_store_settings()
        form = self.form_class(instance=instance)
        context = {
            "form": form,
            "settings": instance,
            "section_title": self.section_title,
            "active_nav": "settings",
            "active_tab": self.section_code,
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        instance = get_store_settings()
        form = self.form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            client_ip = get_client_ip(request)
            # Update regular fields through service
            update_store_settings(
                user=request.user,
                section_name=self.section_title,
                ip_address=client_ip,
                **form.cleaned_data,
            )
            # Update uploaded file assets if any were submitted
            for file_field in self.file_fields:
                if file_field in request.FILES:
                    update_store_file_asset(
                        user=request.user,
                        field_name=file_field,
                        file_obj=request.FILES[file_field],
                        ip_address=client_ip,
                    )

            messages.success(request, f"{self.section_title} settings saved successfully.")
            return redirect(f"dashboard:settings:{self.section_code}")
        else:
            messages.error(request, f"Please correct the errors below when updating {self.section_title}.")
            context = {
                "form": form,
                "settings": instance,
                "section_title": self.section_title,
                "active_nav": "settings",
                "active_tab": self.section_code,
            }
            return render(request, self.template_name, context)


class SettingsDashboardView(StoreSettingsPermissionMixin, TemplateView):
    """
    Main overview dashboard hub for Store Settings (`/dashboard/settings/`).
    Displays summary status cards across all 10 configuration sections.
    """
    template_name = "dashboard/settings/dashboard.html"
    required_permissions = [VIEW_SETTINGS]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        instance = get_store_settings()
        context.update({
            "settings": instance,
            "active_nav": "settings",
            "active_tab": "overview",
        })
        return context


class StoreProfileView(BaseSettingsSectionView):
    form_class = StoreProfileForm
    template_name = "dashboard/settings/store_profile.html"
    section_title = "Store Profile"
    section_code = "profile"
    file_fields = ["logo", "favicon"]
    required_permissions = [MANAGE_STORE_SETTINGS]


class BrandingView(BaseSettingsSectionView):
    form_class = BrandingForm
    template_name = "dashboard/settings/branding.html"
    section_title = "Branding & Theme"
    section_code = "branding"
    file_fields = ["default_placeholder_image"]
    required_permissions = [MANAGE_BRANDING, MANAGE_STORE_SETTINGS]


class CurrencyTaxView(BaseSettingsSectionView):
    form_class = CurrencyTaxForm
    template_name = "dashboard/settings/currency.html"
    section_title = "Currency & Tax Configuration"
    section_code = "currency"
    required_permissions = [MANAGE_STORE_SETTINGS]


class ShippingSettingsView(BaseSettingsSectionView):
    form_class = ShippingSettingsForm
    template_name = "dashboard/settings/shipping.html"
    section_title = "Shipping Settings"
    section_code = "shipping"
    required_permissions = [MANAGE_STORE_SETTINGS]


class EmailSettingsView(BaseSettingsSectionView):
    form_class = EmailSettingsForm
    template_name = "dashboard/settings/email.html"
    section_title = "Email Configuration"
    section_code = "email"
    required_permissions = [MANAGE_STORE_SETTINGS]


class SeoDefaultsView(BaseSettingsSectionView):
    form_class = SeoDefaultsForm
    template_name = "dashboard/settings/seo.html"
    section_title = "SEO Defaults"
    section_code = "seo"
    file_fields = ["default_og_image"]
    required_permissions = [MANAGE_STORE_SETTINGS]


class SocialMediaView(BaseSettingsSectionView):
    form_class = SocialMediaForm
    template_name = "dashboard/settings/social_media.html"
    section_title = "Social Media Links"
    section_code = "social"
    required_permissions = [MANAGE_STORE_SETTINGS]


class FeatureFlagsView(BaseSettingsSectionView):
    form_class = FeatureFlagsForm
    template_name = "dashboard/settings/feature_flags.html"
    section_title = "Feature Flags"
    section_code = "flags"
    required_permissions = [MANAGE_FEATURE_FLAGS, MANAGE_STORE_SETTINGS]


class MaintenanceModeView(BaseSettingsSectionView):
    form_class = MaintenanceModeForm
    template_name = "dashboard/settings/maintenance.html"
    section_title = "Maintenance Mode"
    section_code = "maintenance"
    required_permissions = [TOGGLE_MAINTENANCE_MODE, MANAGE_STORE_SETTINGS]


class StorePoliciesView(BaseSettingsSectionView):
    form_class = StorePoliciesForm
    template_name = "dashboard/settings/policies.html"
    section_title = "Store Policies"
    section_code = "policies"
    required_permissions = [MANAGE_POLICIES, MANAGE_STORE_SETTINGS]
