# orders/admin.py
"""
orders/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin interface configuration for historical Orders and line item snapshots.
Enforces read-only safety on immutable monetary and product fields.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """
    Read-only tabular inline displaying the exact snapshotted line items of an order.
    """
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = [
        "product",
        "product_name",
        "product_slug",
        "sku",
        "variant_description",
        "quantity",
        "unit_price",
        "line_total",
    ]
    fields = [
        "product_name",
        "sku",
        "variant_description",
        "quantity",
        "unit_price",
        "line_total",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    Admin configuration for Order management.
    Allows controlled status transitions while keeping snapshotted address
    and financial breakdown fields read-only.
    """
    list_display = [
        "order_number",
        "user_display",
        "status",
        "payment_status",
        "fulfillment_status",
        "grand_total",
        "currency",
        "created_at",
    ]
    list_filter = [
        "status",
        "payment_status",
        "fulfillment_status",
        "created_at",
    ]
    search_fields = [
        "order_number",
        "user__email",
        "user__first_name",
        "user__last_name",
        "session_key",
    ]
    readonly_fields = [
        "order_number",
        "user",
        "checkout_session",
        "session_key",
        "shipping_address_snapshot",
        "billing_address_snapshot",
        "subtotal",
        "discount_total",
        "shipping_total",
        "tax_total",
        "grand_total",
        "currency",
        "created_at",
        "updated_at",
    ]
    inlines = [OrderItemInline]
    fieldsets = [
        ("Order Identification", {
            "fields": ("order_number", "user", "checkout_session", "session_key", "created_at", "updated_at")
        }),
        ("Lifecycle & Status Workflow", {
            "fields": ("status", "payment_status", "fulfillment_status", "customer_notes")
        }),
        ("Financial Totals (Locked Snapshots)", {
            "fields": ("subtotal", "discount_total", "shipping_total", "tax_total", "grand_total", "currency")
        }),
        ("Address Snapshots", {
            "fields": ("shipping_address_snapshot", "billing_address_snapshot"),
            "classes": ("collapse",)
        }),
    ]

    @admin.display(description="Customer", ordering="user__email")
    def user_display(self, obj: Order) -> str:
        if obj.user:
            return f"{obj.user.email or obj.user.username}"
        return f"Guest ({obj.session_key[:8]}...)" if obj.session_key else "Guest"
