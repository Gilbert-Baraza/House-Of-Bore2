# cart/admin.py
"""
cart/admin.py
──────────────────────────────────────────────────────────────────────────────
Admin configuration for the shopping cart system.
Provides tabular inline management for cart line items.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    """
    Inline tabular editor for line items inside a shopping cart.
    """
    model = CartItem
    extra = 0
    readonly_fields = ("created_at", "updated_at", "subtotal_display")
    fields = ("product", "quantity", "unit_price", "subtotal_display", "created_at")

    def subtotal_display(self, obj: CartItem) -> str:
        if obj.pk:
            return f"${obj.subtotal():.2f}"
        return "$0.00"
    subtotal_display.short_description = "Subtotal"  # type: ignore[attr-defined]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """
    Admin configuration for shopping carts.
    """
    list_display = ("id", "owner_display", "item_count_display", "subtotal_display", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("user__email", "user__first_name", "user__last_name", "session_key")
    readonly_fields = ("created_at", "updated_at", "subtotal_display", "item_count_display")
    inlines = [CartItemInline]
    fieldsets = (
        ("Ownership", {
            "fields": ("user", "session_key")
        }),
        ("Summary", {
            "fields": ("item_count_display", "subtotal_display")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def owner_display(self, obj: Cart) -> str:
        if obj.user:
            return f"User: {obj.user.email}"
        return f"Guest: {str(obj.session_key)[:12]}..."
    owner_display.short_description = "Owner"  # type: ignore[attr-defined]

    def subtotal_display(self, obj: Cart) -> str:
        return f"${obj.subtotal():.2f}"
    subtotal_display.short_description = "Total Value"  # type: ignore[attr-defined]

    def item_count_display(self, obj: Cart) -> int:
        return obj.item_count()
    item_count_display.short_description = "Items"  # type: ignore[attr-defined]
