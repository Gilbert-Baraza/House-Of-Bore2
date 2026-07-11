# crm/models.py
"""
crm/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for Customer Relationship Management (CRM) module.
Provides private administrative staff notes (`CustomerStaffNote`) and manual
concierge interaction tracking (`CustomerInteractionRecord`) while registering
comprehensive granular RBAC permissions for patron data governance.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomerStaffNote(models.Model):
    """
    Private staff-only administrative notes attached to a customer profile.
    Never exposed to customer-facing views or APIs.
    """
    CATEGORY_CHOICES = [
        ("general", _("General Inquiry")),
        ("vip", _("VIP & Concierge Preferences")),
        ("support", _("Customer Support")),
        ("order_issue", _("Order / Shipping Escalation")),
        ("billing", _("Billing & Financial Ledger")),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_notes",
        verbose_name=_("customer"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_staff_notes",
        verbose_name=_("author"),
    )
    note = models.TextField(
        _("note text"),
        help_text=_("Private administrative observation or VIP preference note."),
    )
    category = models.CharField(
        _("category"),
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="general",
        db_index=True,
    )
    is_pinned = models.BooleanField(
        _("pinned to top"),
        default=False,
        help_text=_("Keep this note pinned to the top of the customer overview card."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("customer staff note")
        verbose_name_plural = _("customer staff notes")
        ordering = ["-is_pinned", "-created_at"]
        permissions = [
            ("view_customer", "Can view customer profiles"),
            ("change_customer", "Can modify customer profiles and preferences"),
            ("add_staffnote", "Can add private staff notes"),
            ("view_analytics", "Can view CRM analytics"),
            ("export_customerdata", "Can export customer profile and order history data"),
        ]

    def __str__(self) -> str:
        author_email = self.author.email if self.author else "System"
        return f"Note on {self.customer.email} by {author_email} ({self.get_category_display()})"


class CustomerInteractionRecord(models.Model):
    """
    Manual communication log for recording offline or direct concierge contact
    (phone calls, bespoke email threads, in-person salon visits).
    """
    INTERACTION_TYPE_CHOICES = [
        ("phone", _("Phone Call")),
        ("email", _("Email Correspondence")),
        ("in_person", _("In-Person Salon Consultation")),
        ("support_ticket", _("Support Ticket Inquiry")),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="interaction_records",
        verbose_name=_("customer"),
    )
    interaction_type = models.CharField(
        _("interaction type"),
        max_length=50,
        choices=INTERACTION_TYPE_CHOICES,
        db_index=True,
    )
    summary = models.CharField(
        _("summary headline"),
        max_length=255,
    )
    details = models.TextField(
        _("detailed summary"),
        blank=True,
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logged_interactions",
        verbose_name=_("performed by"),
    )
    timestamp = models.DateTimeField(
        _("timestamp"),
        default=timezone.now,
        db_index=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("customer interaction record")
        verbose_name_plural = _("customer interaction records")
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.get_interaction_type_display()} with {self.customer.email} on {self.timestamp:%Y-%m-%d}"
