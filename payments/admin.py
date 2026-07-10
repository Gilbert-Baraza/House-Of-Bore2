# payments/admin.py
"""
payments/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin configuration for `Payment` and `PaymentWebhookLog`.
Enforces read-only audit inspection for historical transactions and webhooks.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from payments.models import Payment, PaymentWebhookLog


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "payment_reference",
        "order",
        "gateway",
        "amount",
        "currency",
        "status",
        "transaction_id",
        "created_at",
    ]
    list_filter = ["gateway", "status", "currency", "created_at"]
    search_fields = [
        "payment_reference",
        "order__order_number",
        "transaction_id",
    ]
    readonly_fields = [
        "payment_reference",
        "order",
        "gateway",
        "transaction_id",
        "amount",
        "currency",
        "status",
        "provider_response",
        "metadata",
        "initiated_at",
        "completed_at",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        ("Transaction Summary", {
            "fields": ("payment_reference", "order", "gateway", "status")
        }),
        ("Monetary Details", {
            "fields": ("amount", "currency", "transaction_id")
        }),
        ("Timestamps", {
            "fields": ("initiated_at", "completed_at", "created_at", "updated_at")
        }),
        ("Audit & Gateway Payloads", {
            "classes": ("collapse",),
            "fields": ("provider_response", "metadata")
        }),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentWebhookLog)
class PaymentWebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "gateway",
        "event_type",
        "event_id",
        "status",
        "created_at",
    ]
    list_filter = ["gateway", "status", "created_at"]
    search_fields = ["event_id", "event_type"]
    readonly_fields = [
        "gateway",
        "event_id",
        "event_type",
        "status",
        "payload",
        "headers",
        "error_message",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
