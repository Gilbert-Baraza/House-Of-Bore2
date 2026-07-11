# dashboard/models.py
"""
dashboard/models.py
──────────────────────────────────────────────────────────────────────────────
Data models for the Custom Administration Dashboard and Role-Based Access Control
(RBAC) subsystem.

Includes:
1. StaffRole: Application-level RBAC roles with customizable permissions.
2. AuditLog: Immutable record of administrative and business operations.
3. StaffPreference: Per-user staff settings and notification preferences.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StaffRole(models.Model):
    """
    Application-level Role model for Role-Based Access Control (RBAC).

    Allows grouping permissions into business roles (e.g., Store Manager,
    Inventory Manager, Customer Support) without modifying core Django Groups.
    A staff user can be assigned one or more StaffRoles.
    """
    name = models.CharField(
        _("role name"),
        max_length=100,
        unique=True,
        help_text=_("Human-readable role title (e.g., Store Manager).")
    )
    code = models.SlugField(
        _("role code"),
        max_length=100,
        unique=True,
        help_text=_("Unique identifier code used in programmatic checks (e.g., store_manager).")
    )
    description = models.TextField(
        _("description"),
        blank=True,
        default="",
        help_text=_("Detailed explanation of the role's responsibilities and scope.")
    )
    permissions = models.JSONField(
        _("permissions"),
        default=list,
        blank=True,
        help_text=_("List of permission strings granted by this role (e.g., ['orders.view_order']).")
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="staff_roles",
        blank=True,
        verbose_name=_("assigned users"),
        help_text=_("Staff members assigned to this role.")
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("staff role")
        verbose_name_plural = _("staff roles")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def has_permission(self, perm: str) -> bool:
        """
        Check if this role grants the specified permission.
        Super Administrator (`super_admin`) automatically grants all permissions.
        """
        if self.code == "super_admin":
            return True
        return perm in self.permissions


class AuditLog(models.Model):
    """
    Immutable audit trail recording all critical staff actions, data modifications,
    and authentication events across the administrative dashboard.
    """
    ACTION_TYPES = [
        ("LOGIN", _("User Login")),
        ("LOGOUT", _("User Logout")),
        ("CREATE", _("Create Object")),
        ("UPDATE", _("Update Object")),
        ("DELETE", _("Delete Object")),
        ("VIEW", _("View Object")),
        ("EXPORT", _("Export Data")),
        ("ACTION", _("Custom Action")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("user"),
        help_text=_("Staff member who performed the action (null for system automated tasks).")
    )
    action = models.CharField(
        _("action type"),
        max_length=30,
        choices=ACTION_TYPES,
        db_index=True,
        help_text=_("Categorization of the administrative action.")
    )
    model_name = models.CharField(
        _("target model"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Name of the model being acted upon (e.g., Order, Product).")
    )
    object_id = models.CharField(
        _("object ID"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Primary key or identifier of the affected object.")
    )
    description = models.TextField(
        _("description"),
        help_text=_("Human-readable summary of the action and any changes made.")
    )
    ip_address = models.GenericIPAddressField(
        _("IP address"),
        null=True,
        blank=True,
        help_text=_("IP address from which the request originated.")
    )
    user_agent = models.CharField(
        _("user agent"),
        max_length=512,
        null=True,
        blank=True,
        help_text=_("Client browser and OS details.")
    )
    timestamp = models.DateTimeField(
        _("timestamp"),
        auto_now_add=True,
        db_index=True,
        help_text=_("Exact time the action occurred.")
    )

    class Meta:
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log entries")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["model_name", "-timestamp"]),
        ]

    def __str__(self) -> str:
        user_display = self.user.email if self.user else "System/Guest"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {user_display} - {self.action}: {self.description[:50]}"


class StaffPreference(models.Model):
    """
    Staff-specific settings and notification preferences for dashboard operations.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_preferences",
        verbose_name=_("user"),
    )
    email_alerts = models.BooleanField(
        _("email alerts"),
        default=True,
        help_text=_("Receive critical operational notifications via email.")
    )
    low_stock_alerts = models.BooleanField(
        _("low stock alerts"),
        default=True,
        help_text=_("Receive notifications when inventory falls below reorder thresholds.")
    )
    new_order_alerts = models.BooleanField(
        _("new order alerts"),
        default=True,
        help_text=_("Receive real-time notifications for newly placed customer orders.")
    )
    system_notification_alerts = models.BooleanField(
        _("system notification alerts"),
        default=True,
        help_text=_("Display in-app system notifications for failed payments and registrations.")
    )
    dark_mode = models.BooleanField(
        _("dark mode"),
        default=False,
        help_text=_("Enable dark theme across the staff administration dashboard.")
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("staff preference")
        verbose_name_plural = _("staff preferences")

    def __str__(self) -> str:
        return f"Preferences for {self.user.email}"
