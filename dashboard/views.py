# dashboard/views.py
"""
dashboard/views.py
──────────────────────────────────────────────────────────────────────────────
Thin presentation views for the Custom Administration Dashboard.

Keeps views lean by delegating queries to `selectors.py` and state-changing
operations to `services.py`. Enforces authentication and RBAC permissions cleanly
via `permissions.py` mixins.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import TemplateView, View

from accounts.models import UserProfile
from .forms import StaffAvatarForm, StaffContactForm, StaffPreferenceForm
from .permissions import StaffRequiredMixin, _handle_access_denied
from .services import (
    get_dashboard_summary,
    get_or_create_staff_preferences,
    log_update,
    staff_notifications,
    update_staff_avatar,
    update_staff_contact,
    update_staff_preferences,
)


class DashboardHomeView(StaffRequiredMixin, TemplateView):
    """
    Main administration dashboard homepage view.
    Displays real-time KPI metrics, recent orders, new customers, and activity feed.
    """
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        summary = get_dashboard_summary()
        context.update(summary)
        context["active_nav"] = "dashboard"
        return context


class StaffProfileView(StaffRequiredMixin, TemplateView):
    """
    Displays the staff member's administrative profile, role assignments,
    avatar, contact details, and notification preferences.
    """
    template_name = "dashboard/profile.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        preferences = get_or_create_staff_preferences(user)

        context["profile"] = profile
        context["preferences"] = preferences
        context["contact_form"] = StaffContactForm(instance=profile)
        context["avatar_form"] = StaffAvatarForm(instance=profile)
        context["preference_form"] = StaffPreferenceForm(instance=preferences)
        context["active_nav"] = "profile"
        return context


class StaffContactUpdateView(StaffRequiredMixin, View):
    """
    Handles POST requests to update a staff member's contact phone number.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = StaffContactForm(request.POST, instance=profile)
        if form.is_valid():
            phone = form.cleaned_data["phone_number"]
            update_staff_contact(request.user, phone)
            log_update(request.user, profile, description=f"Updated contact details for {request.user.email}", ip_address=request.META.get("REMOTE_ADDR"))
            messages.success(request, "Contact details updated successfully.")
        else:
            messages.error(request, "Invalid phone number submitted.")
        return redirect("dashboard:profile")


class StaffAvatarUpdateView(StaffRequiredMixin, View):
    """
    Handles POST requests to update a staff member's profile avatar image.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = StaffAvatarForm(request.POST, request.FILES, instance=profile)
        if form.is_valid() and "avatar" in request.FILES:
            update_staff_avatar(request.user, request.FILES["avatar"])
            log_update(request.user, profile, description=f"Updated profile avatar for {request.user.email}", ip_address=request.META.get("REMOTE_ADDR"))
            messages.success(request, "Profile avatar updated successfully.")
        else:
            messages.error(request, "Failed to update profile avatar. Please check file format and size.")
        return redirect("dashboard:profile")


class StaffPreferencesUpdateView(StaffRequiredMixin, View):
    """
    Handles POST requests to update notification and theme preferences.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        preferences = get_or_create_staff_preferences(request.user)
        form = StaffPreferenceForm(request.POST, instance=preferences)
        if form.is_valid():
            update_staff_preferences(
                user=request.user,
                email_alerts=form.cleaned_data["email_alerts"],
                low_stock_alerts=form.cleaned_data["low_stock_alerts"],
                new_order_alerts=form.cleaned_data["new_order_alerts"],
                system_notification_alerts=form.cleaned_data["system_notification_alerts"],
                dark_mode=form.cleaned_data["dark_mode"],
            )
            log_update(request.user, preferences, description=f"Updated dashboard preferences for {request.user.email}", ip_address=request.META.get("REMOTE_ADDR"))
            messages.success(request, "Dashboard preferences saved successfully.")
        else:
            messages.error(request, "Failed to save dashboard preferences.")
        return redirect("dashboard:profile")


class NotificationListView(StaffRequiredMixin, TemplateView):
    """
    Dedicated notification center listing low stock items, new orders,
    failed payments, and customer registrations.
    """
    template_name = "dashboard/notifications.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["notifications"] = staff_notifications(user=self.request.user, limit=50)
        context["active_nav"] = "notifications"
        return context


class AccessDeniedView(View):
    """
    Renders the branded 'Access Denied' page with HTTP status 403.
    Accessed directly or rendered by decorators/mixins upon permission failures.
    """
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return _handle_access_denied(request)


# ─── SECTION PLACEHOLDER VIEWS ────────────────────────────────────────────────
class BaseSectionPlaceholderView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/placeholder_section.html"
    section_name = ""
    section_title = ""
    section_description = ""
    icon = ""
    active_nav = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "section_name": self.section_name,
            "section_title": self.section_title,
            "section_description": self.section_description,
            "icon": self.icon,
            "active_nav": self.active_nav,
        })
        return context


class StaffOrdersView(BaseSectionPlaceholderView):
    section_name = "Orders Management"
    section_title = "Customer Orders"
    section_description = "Track order fulfillment, payment verification, and shipment lifecycles."
    icon = "orders"
    active_nav = "orders"


class StaffProductsView(BaseSectionPlaceholderView):
    section_name = "Catalog & Products"
    section_title = "Product Catalog"
    section_description = "Manage luxury garments, variants, pricing tiers, and collections."
    icon = "products"
    active_nav = "products"


class StaffCustomersView(BaseSectionPlaceholderView):
    section_name = "Customer Relationship Management"
    section_title = "Customers & Patrons"
    section_description = "Review customer accounts, VIP order histories, and concierge notes."
    icon = "customers"
    active_nav = "customers"


class StaffMarketingView(BaseSectionPlaceholderView):
    section_name = "Marketing & Promotions"
    section_title = "Marketing Campaigns"
    section_description = "Configure promotional rules, seasonal discounts, and email newsletters."
    icon = "marketing"
    active_nav = "marketing"


class StaffReportsView(BaseSectionPlaceholderView):
    section_name = "Business Intelligence"
    section_title = "Reports & Analytics"
    section_description = "Analyze revenue trends, category performance, and inventory velocity."
    icon = "reports"
    active_nav = "reports"


class StaffSettingsView(BaseSectionPlaceholderView):
    section_name = "Store Configurations"
    section_title = "Store Settings"
    section_description = "Manage global store preferences, tax calculation rules, and payment gateways."
    icon = "settings"
    active_nav = "settings"


class StaffUsersView(BaseSectionPlaceholderView):
    section_name = "RBAC & Staff Directory"
    section_title = "Staff Users & Roles"
    section_description = "Manage administrative personnel, assign roles, and audit security logs."
    icon = "users"
    active_nav = "users"
