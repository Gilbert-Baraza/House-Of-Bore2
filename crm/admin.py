# crm/admin.py
from django.contrib import admin
from .models import CustomerInteractionRecord, CustomerStaffNote


@admin.register(CustomerStaffNote)
class CustomerStaffNoteAdmin(admin.ModelAdmin):
    list_display = ["customer", "author", "category", "is_pinned", "created_at"]
    list_filter = ["category", "is_pinned", "created_at"]
    search_fields = ["customer__email", "note"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CustomerInteractionRecord)
class CustomerInteractionRecordAdmin(admin.ModelAdmin):
    list_display = ["customer", "interaction_type", "summary", "performed_by", "timestamp"]
    list_filter = ["interaction_type", "timestamp"]
    search_fields = ["customer__email", "summary", "details"]
    readonly_fields = ["created_at"]
