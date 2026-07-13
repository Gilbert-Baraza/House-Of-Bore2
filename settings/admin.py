# settings/admin.py
"""
settings/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin configuration for StoreSettings singleton.
Ensures singleton integrity by preventing addition of multiple rows or deletion.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import admin
from django.http import HttpRequest
from .models import StoreSettings


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Store Profile", {
            "fields": ("store_name", "business_name", "store_description", "logo", "favicon", "email", "phone", "whatsapp", "physical_address", "business_hours")
        }),
        ("Branding & Theme", {
            "fields": ("primary_color", "secondary_color", "accent_color", "footer_text", "announcement_banner_enabled", "announcement_banner_text", "default_placeholder_image")
        }),
        ("Currency & Tax Configuration", {
            "fields": ("default_currency", "currency_symbol", "decimal_precision", "tax_enabled", "tax_percentage", "tax_display_mode")
        }),
        ("Shipping Settings", {
            "fields": ("free_shipping_threshold", "flat_shipping_rate", "local_pickup_enabled", "estimated_delivery_message", "default_shipping_policy")
        }),
        ("Email Settings", {
            "fields": ("store_sender_name", "reply_to_email", "customer_support_email", "order_notification_recipients")
        }),
        ("SEO Defaults", {
            "fields": ("default_meta_title", "default_meta_description", "default_og_image", "default_social_share_description", "robots_index_preference")
        }),
        ("Social Media Links", {
            "fields": ("facebook_url", "instagram_url", "twitter_url", "tiktok_url", "youtube_url", "linkedin_url")
        }),
        ("Maintenance Mode", {
            "fields": ("maintenance_mode_enabled", "maintenance_message", "maintenance_return_date")
        }),
        ("Feature Flags", {
            "fields": ("feature_wishlist", "feature_reviews", "feature_compare", "feature_recently_viewed", "feature_promotions", "feature_guest_checkout")
        }),
        ("Store Policies", {
            "fields": ("privacy_policy", "terms_and_conditions", "shipping_policy", "returns_policy", "refund_policy"),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Only allow addition if no instance exists yet
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Never allow deletion of the singleton configuration row
        return False
