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

from .models import User


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
