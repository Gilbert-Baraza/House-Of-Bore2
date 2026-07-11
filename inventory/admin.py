from django.contrib import admin

from .models import Inventory, InventoryMovement


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("product_variant", "available_quantity", "reserved_quantity", "damaged_quantity", "reorder_level")
    search_fields = ("product_variant__sku", "product_variant__product__name")
    list_filter = ("reorder_level",)


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("inventory", "movement_type", "quantity", "previous_quantity", "new_quantity", "created_at")
    readonly_fields = ("inventory", "movement_type", "quantity", "previous_quantity", "new_quantity", "reference_type", "reference_id", "performed_by", "notes", "created_at")
    search_fields = ("inventory__product_variant__sku", "notes")
