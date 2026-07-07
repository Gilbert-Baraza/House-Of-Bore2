"""
accounts/admin.py
──────────────────────────────────────────────────────────────────────────────
Registers the custom User model with Django's admin site.

WHY USE UserAdmin (not ModelAdmin)?
    Django's UserAdmin provides the full admin experience for user management
    out of the box: password change forms, permission management, group
    assignment, and the correct fieldsets layout. Using a plain ModelAdmin
    would break the password change workflow and expose the raw hashed
    password field.

    We extend UserAdmin and adjust only what differs from the default —
    the fieldsets and add_fieldsets that reference "username" — to match
    our email-based model.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, UserProfile, Address, PendingEmailChange, AccountActivity, UserSession


class AddressInline(admin.StackedInline):
    """
    Inline admin configuration for Address.
    Allows viewing and editing patron addresses within the User detail view.
    """
    model = Address
    extra = 0
    can_delete = True
    verbose_name = _("address")
    verbose_name_plural = _("addresses")
    fk_name = "user"


class UserProfileInline(admin.StackedInline):
    """
    Inline admin configuration for UserProfile.
    Allows editing profile details directly within the User detail view.
    """
    model = UserProfile
    can_delete = False
    verbose_name_plural = _("profile")
    fk_name = "user"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin configuration for the custom User model.

    Inherits all default behaviour from Django's UserAdmin and only
    overrides the sections that reference the removed `username` field.
    Everything else (password change, permissions, groups) works unchanged.
    """

    # ── List view ────────────────────────────────────────────────────────────
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)

    # ── Detail / change view ─────────────────────────────────────────────────
    # Override BaseUserAdmin.fieldsets to remove the "username" section.
    # The structure mirrors Django's default layout so the admin feels familiar.
    fieldsets = (
        # Section 1: credentials
        (None, {"fields": ("email", "password")}),
        # Section 2: personal info
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        # Section 3: permissions — identical to Django's default
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),  # collapsed by default to reduce clutter
            },
        ),
        # Section 4: important dates — identical to Django's default
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # ── Add user view ────────────────────────────────────────────────────────
    # Defines the fields shown on the "Add user" form in the admin.
    # BaseUserAdmin's default references "username" — we replace it with "email".
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    inlines = (UserProfileInline, AddressInline)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Standalone admin configuration for UserProfile."""
    list_display = ("user", "phone_number", "preferred_language", "preferred_currency", "marketing_emails", "updated_at")
    list_filter = ("preferred_language", "preferred_currency", "marketing_emails")
    search_fields = ("user__email", "phone_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Standalone admin configuration for Address."""
    list_display = ("label", "user", "recipient_name", "city", "country", "address_type", "is_default_shipping", "is_default_billing", "updated_at")
    list_filter = ("address_type", "is_default_shipping", "is_default_billing", "country")
    search_fields = ("user__email", "label", "recipient_name", "address_line_1", "city")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PendingEmailChange)
class PendingEmailChangeAdmin(admin.ModelAdmin):
    """Admin configuration for PendingEmailChange."""
    list_display = ("user", "new_email", "created_at", "is_expired")
    list_filter = ("created_at",)
    search_fields = ("user__email", "new_email", "token")
    readonly_fields = ("created_at",)


@admin.register(AccountActivity)
class AccountActivityAdmin(admin.ModelAdmin):
    """Admin configuration for AccountActivity audit log (read-only in production)."""
    list_display = ("user", "event_type", "ip_address", "timestamp")
    list_filter = ("event_type", "timestamp")
    search_fields = ("user__email", "ip_address", "user_agent")
    readonly_fields = ("user", "event_type", "ip_address", "user_agent", "details", "timestamp")


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """Admin configuration for UserSession monitoring."""
    list_display = ("user", "session_key", "ip_address", "last_activity", "created_at")
    list_filter = ("last_activity", "created_at")
    search_fields = ("user__email", "session_key", "ip_address", "user_agent")
    readonly_fields = ("created_at", "last_activity")

