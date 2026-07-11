# dashboard/admin.py
"""
dashboard/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin interface registrations for the custom administration dashboard.
Allows developers and superusers to manage RBAC roles, inspect immutable audit
logs, and view staff preferences.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from .models import AuditLog, StaffPreference, StaffRole


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "user_count", "updated_at")
    search_fields = ("name", "code", "description")
    prepopulated_fields = {"code": ("name",)}
    filter_horizontal = ("users",)
    readonly_fields = ("created_at", "updated_at")

    def user_count(self, obj: StaffRole) -> int:
        return obj.users.count()
    user_count.short_description = "Assigned Users"  # type: ignore[attr-defined]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_id", "short_description", "ip_address")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("description", "object_id", "user__email", "ip_address")
    readonly_fields = ("user", "action", "model_name", "object_id", "description", "ip_address", "user_agent", "timestamp")
    date_hierarchy = "timestamp"

    def short_description(self, obj: AuditLog) -> str:
        return obj.description[:75] + ("..." if len(obj.description) > 75 else "")
    short_description.short_description = "Description"  # type: ignore[attr-defined]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(StaffPreference)
class StaffPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_alerts", "low_stock_alerts", "new_order_alerts", "dark_mode", "updated_at")
    list_filter = ("email_alerts", "low_stock_alerts", "new_order_alerts", "dark_mode")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
