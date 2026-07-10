# notifications/admin.py
"""
notifications/admin.py
──────────────────────────────────────────────────────────────────────────────
Read-only Django Admin interfaces for auditing outbound communications,
inspecting delivery logs, and verifying multi-channel event history.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from notifications.models import Notification, NotificationDeliveryLog


class NotificationDeliveryLogInline(admin.TabularInline):
    model = NotificationDeliveryLog
    extra = 0
    can_delete = False
    readonly_fields = [
        "channel",
        "provider",
        "recipient",
        "status",
        "error_details",
        "retry_count",
        "created_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "channel",
        "event",
        "recipient",
        "subject",
        "status",
        "provider",
        "retry_count",
        "created_at",
        "sent_at",
    ]
    list_select_related = ["user", "order", "payment"]
    list_filter = ["status", "channel", "event", "provider", "created_at"]
    search_fields = ["recipient", "subject", "order__order_number", "payment__payment_reference", "error_message"]
    readonly_fields = [
        "user",
        "order",
        "payment",
        "channel",
        "event",
        "recipient",
        "subject",
        "status",
        "provider",
        "error_message",
        "metadata",
        "retry_count",
        "sent_at",
        "created_at",
        "updated_at",
    ]
    inlines = [NotificationDeliveryLogInline]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationDeliveryLog)
class NotificationDeliveryLogAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "notification_id",
        "channel",
        "provider",
        "recipient",
        "status",
        "retry_count",
        "created_at",
    ]
    list_select_related = ["notification"]
    list_filter = ["status", "channel", "provider", "created_at"]
    search_fields = ["recipient", "error_details", "notification__pk"]
    readonly_fields = [
        "notification",
        "channel",
        "provider",
        "recipient",
        "status",
        "error_details",
        "retry_count",
        "created_at",
    ]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
