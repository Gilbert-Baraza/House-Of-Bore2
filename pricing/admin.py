# pricing/admin.py
"""
pricing/admin.py
──────────────────────────────────────────────────────────────────────────────
Django admin configuration for Coupon and Promotion management.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from pricing.models import Coupon, Promotion


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "minimum_order_amount", "active", "starts_at", "expires_at", "usage_count", "usage_limit")
    list_filter = ("active", "discount_type", "starts_at", "expires_at")
    search_fields = ("code", "description")
    readonly_fields = ("usage_count", "created_at", "updated_at")
    fieldsets = (
        ("Coupon Details", {
            "fields": ("code", "description", "active")
        }),
        ("Discount Rules", {
            "fields": ("discount_type", "discount_value", "minimum_order_amount", "maximum_discount_amount")
        }),
        ("Validity & Usage Limits", {
            "fields": ("starts_at", "expires_at", "usage_limit", "usage_count")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "promotion_type", "discount_type", "discount_value", "priority", "active", "starts_at", "expires_at")
    list_filter = ("active", "promotion_type", "discount_type", "starts_at", "expires_at")
    search_fields = ("name", "description")
    filter_horizontal = ("categories", "products")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Promotion Details", {
            "fields": ("name", "description", "promotion_type", "active", "priority")
        }),
        ("Discount Rules", {
            "fields": ("discount_type", "discount_value", "rules_config")
        }),
        ("Applicability Scope", {
            "fields": ("categories", "products")
        }),
        ("Validity Window", {
            "fields": ("starts_at", "expires_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
