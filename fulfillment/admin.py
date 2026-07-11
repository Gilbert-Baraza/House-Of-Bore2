# fulfillment/admin.py
"""
fulfillment/admin.py
──────────────────────────────────────────────────────────────────────────────
Django administrative interfaces for `fulfillment` domain models.
Provides fallback / superuser inspection for fulfillment orders, picking items,
carrier shipments, immutable event logs, and RMA requests.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from .models import (
    FulfillmentEvent,
    FulfillmentItem,
    FulfillmentOrder,
    ReturnExchangeRequest,
    Shipment,
)


class FulfillmentItemInline(admin.TabularInline):
    model = FulfillmentItem
    extra = 0
    readonly_fields = ("order_item", "quantity")


class ShipmentInline(admin.TabularInline):
    model = Shipment
    extra = 0
    readonly_fields = ("created_at", "updated_at")


class FulfillmentEventInline(admin.TabularInline):
    model = FulfillmentEvent
    extra = 0
    readonly_fields = ("event_type", "description", "performed_by", "metadata", "created_at")
    can_delete = False


@admin.register(FulfillmentOrder)
class FulfillmentOrderAdmin(admin.ModelAdmin):
    list_display = ("order", "fulfillment_status", "priority", "warehouse", "assigned_staff", "created_at")
    list_filter = ("fulfillment_status", "priority", "warehouse", "created_at")
    search_fields = ("order__order_number", "order__user__email", "notes", "internal_notes")
    readonly_fields = ("created_at", "updated_at", "picking_started_at", "picking_completed_at", "packing_started_at", "packing_completed_at", "dispatched_at", "delivered_at")
    inlines = [FulfillmentItemInline, ShipmentInline, FulfillmentEventInline]


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("tracking_number", "fulfillment_order", "courier", "shipping_method", "shipment_status", "shipping_cost", "created_at")
    list_filter = ("courier", "shipment_status", "created_at")
    search_fields = ("tracking_number", "fulfillment_order__order__order_number")


@admin.register(FulfillmentEvent)
class FulfillmentEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "fulfillment_order", "event_type", "performed_by", "description")
    list_filter = ("event_type", "created_at")
    search_fields = ("fulfillment_order__order__order_number", "description", "event_type")
    readonly_fields = ("fulfillment_order", "event_type", "description", "performed_by", "metadata", "created_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ReturnExchangeRequest)
class ReturnExchangeRequestAdmin(admin.ModelAdmin):
    list_display = ("fulfillment_order", "request_type", "status", "inspected_by", "created_at")
    list_filter = ("request_type", "status", "created_at")
    search_fields = ("fulfillment_order__order__order_number", "reason", "customer_notes")
