# wishlist/admin.py
"""
wishlist/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin configuration for Wishlist and WishlistItem models.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from wishlist.models import Wishlist, WishlistItem


class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0
    raw_id_fields = ["product"]
    readonly_fields = ["added_at"]


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ["user", "get_item_count", "created_at", "updated_at"]
    list_select_related = ["user"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [WishlistItemInline]

    @admin.display(description=_("Item Count"))
    def get_item_count(self, obj: Wishlist) -> int:
        return obj.item_count()


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["product", "get_user", "added_at"]
    list_select_related = ["wishlist__user", "product"]
    search_fields = ["product__name", "wishlist__user__email"]
    readonly_fields = ["added_at"]
    raw_id_fields = ["wishlist", "product"]

    @admin.display(description=_("User"), ordering="wishlist__user")
    def get_user(self, obj: WishlistItem) -> str:
        return str(obj.wishlist.user)
