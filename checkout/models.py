# checkout/models.py
"""
checkout/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for the checkout flow pipeline.
Stores transient checkout progression details, snapshot addresses (CheckoutAddress),
and configuration flags for both guests and authenticated customers.
──────────────────────────────────────────────────────────────────────────────
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from accounts.models import Address


class CheckoutAddress(models.Model):
    """
    Independent address snapshot stored separately for checkout security
    and historical snapshot preservation.
    """
    recipient_name = models.CharField(
        max_length=150,
        help_text="Full name of the recipient."
    )
    phone_number = models.CharField(
        max_length=30,
        help_text="Contact number for delivery notifications."
    )
    company_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional company name."
    )
    address_line_1 = models.CharField(
        max_length=255,
        help_text="Street address, P.O. box, or business department."
    )
    address_line_2 = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Apartment, suite, unit, or building floor."
    )
    city = models.CharField(
        max_length=100,
        help_text="City or municipality."
    )
    county_or_state = models.CharField(
        max_length=100,
        help_text="State, province, or county."
    )
    postal_code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="ZIP or postal code."
    )
    country = models.CharField(
        max_length=2,
        choices=Address.COUNTRY_CHOICES,
        default="US",
        help_text="Standardized ISO 2-letter country code."
    )

    class Meta:
        verbose_name = "checkout address"
        verbose_name_plural = "checkout addresses"

    def __str__(self) -> str:
        return f"{self.recipient_name} - {self.city}, {self.country}"


class CheckoutSession(models.Model):
    """
    Temporary check-out state tracking customer progress during shipping,
    billing, and order validation steps.
    
    Enforces exactly one active checkout session per cart at a time.
    """
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="checkout_sessions",
        help_text="Optional customer account associated with this session."
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text="Django session key for anonymous guest checkouts."
    )
    cart = models.OneToOneField(
        "cart.Cart",
        on_delete=models.CASCADE,
        related_name="checkout_session",
        help_text="Shopping cart associated with this checkout flow."
    )
    shipping_address = models.ForeignKey(
        CheckoutAddress,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipping_sessions",
        help_text="Snapshotted shipping address."
    )
    billing_address = models.ForeignKey(
        CheckoutAddress,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_sessions",
        help_text="Snapshotted billing address."
    )
    billing_same_as_shipping = models.BooleanField(
        default=True,
        help_text="Indicates whether the billing address is identical to shipping."
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional customer checkout or delivery notes."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        help_text="Current state of checkout session progression."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        help_text="Timestamp when the checkout session is flagged as invalid/expired."
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "checkout session"
        verbose_name_plural = "checkout sessions"

    def __str__(self) -> str:
        return f"Checkout Session #{self.pk} (Cart #{self.cart_id})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

