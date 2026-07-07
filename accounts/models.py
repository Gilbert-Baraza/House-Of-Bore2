"""
accounts/models.py
──────────────────────────────────────────────────────────────────────────────
Custom User model for House-Of-Bore.

DESIGN DECISIONS
────────────────
1.  AbstractUser (not AbstractBaseUser)
    We extend AbstractUser rather than the lower-level AbstractBaseUser.
    AbstractUser already provides: password hashing, last_login, is_active,
    is_staff, is_superuser, groups, user_permissions, date_joined, and the
    full permission framework. Building on top of it means we get a
    production-ready auth system for free, and only need to adjust the
    identifier field from username → email.

2.  Email as USERNAME_FIELD
    Using email as the unique identifier is the standard expectation for
    modern e-commerce sites. Customers identify themselves by email, not a
    chosen username. This also eliminates a whole class of UX friction
    ("I forgot my username").

3.  username = None
    AbstractUser declares `username` as a required field. Setting it to None
    and removing it from REQUIRED_FIELDS completely drops it from the model
    and the admin creation form, keeping the schema clean.

4.  Minimal fields (Phase 1.2 scope)
    Additional profile fields (phone, avatar, address) will be added in
    later phases via a separate UserProfile model or direct extension.
    Keeping the User model minimal now avoids premature abstraction.

WHY BEFORE OTHER MIGRATIONS?
─────────────────────────────
Django's AUTH_USER_MODEL setting must be established before any migration
is applied. All other apps that reference the User model (orders, reviews,
cart, etc.) will have a ForeignKey to AUTH_USER_MODEL. If we change
AUTH_USER_MODEL after those migrations exist, Django cannot automatically
reconcile the difference — you would need to drop the database and start
fresh, or write a complex data migration. Doing it first costs nothing;
doing it later is extremely painful.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Custom User model for House-Of-Bore.

    Replaces Django's built-in auth.User as the project's authentication
    model. Uses email as the unique login identifier instead of username.

    All authentication behaviour (password hashing, permissions, groups,
    admin flags) is inherited from AbstractUser unchanged.
    """

    # Remove the username field entirely. AbstractUser declares it as required;
    # setting it to None removes it from the model schema and all forms.
    username = None  # type: ignore[assignment]

    # Email is now the unique identifier used for login.
    # unique=True enforces a database-level constraint — no two accounts
    # can share the same address.
    email = models.EmailField(
        _("email address"),
        unique=True,
        help_text=_("Required. A valid email address."),
    )

    # Email verification indicators (Phase 3.3 scope)
    email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Designates whether this user has verified their email address."),
    )
    email_verified_at = models.DateTimeField(
        _("email verified at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when the email address was verified."),
    )

    # Tell Django which field to use as the login identifier.
    # This affects: authenticate(), createsuperuser, and all auth forms.
    USERNAME_FIELD = "email"

    # Fields prompted by `createsuperuser` in addition to email and password.
    # AbstractUser's default includes "username" — we clear that here since
    # we've removed the username field.
    REQUIRED_FIELDS: list[str] = []

    # Swap in our custom manager so that create_user() and create_superuser()
    # use email instead of username.
    objects: UserManager = UserManager()  # type: ignore[assignment]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        """
        Return the user's full name, falling back to their email address.

        Convenience property used in templates and admin displays.
        """
        name = self.get_full_name()
        return name if name else self.email

    def verify_email(self) -> None:
        """
        Mark the customer's email address as verified and record the timestamp.
        """
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at"])


def validate_not_in_future(value: Any) -> None:
    """Validator to ensure date of birth is not in the future."""
    if value and value > timezone.now().date():
        raise ValidationError(_("Date of birth cannot be in the future."))


class UserProfile(models.Model):
    """
    Customer-specific profile attributes and preferences.
    
    Separates authentication credentials (on User) from personal profile data.
    Automatically created via post_save signal when a new User is registered.
    """
    LANGUAGE_CHOICES = [
        ("en", _("English")),
        ("fr", _("French")),
        ("it", _("Italian")),
        ("ar", _("Arabic")),
    ]
    CURRENCY_CHOICES = [
        ("USD", _("USD ($)")),
        ("EUR", _("EUR (€)")),
        ("GBP", _("GBP (£)")),
        ("CHF", _("CHF (CHF)")),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("user"),
    )
    phone_number = models.CharField(
        _("phone number"),
        max_length=30,
        blank=True,
        help_text=_("Customer phone number for order updates and concierge contact."),
    )
    avatar = models.ImageField(
        _("avatar"),
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Profile picture. Max size 2MB."),
    )
    date_of_birth = models.DateField(
        _("date of birth"),
        blank=True,
        null=True,
        validators=[validate_not_in_future],
        help_text=_("Optional date of birth for birthday rewards."),
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=10,
        default="en",
        choices=LANGUAGE_CHOICES,
        help_text=_("Preferred communication language."),
    )
    preferred_currency = models.CharField(
        _("preferred currency"),
        max_length=3,
        default="USD",
        choices=CURRENCY_CHOICES,
        help_text=_("Preferred display currency."),
    )
    marketing_emails = models.BooleanField(
        _("marketing emails"),
        default=True,
        help_text=_("Receive exclusive catalog invitations and luxury updates."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("user profile")
        verbose_name_plural = _("user profiles")

    def __str__(self) -> str:
        return f"Profile for {self.user.email}"


class Address(models.Model):
    """
    Customer Address Book model for shipping and billing addresses.
    
    Stores patron addresses separately from User/UserProfile to allow multiple
    addresses per customer, distinct shipping/billing defaults, and seamless
    checkout integration.
    """
    COUNTRY_CHOICES = [
        ("US", _("United States")),
        ("CA", _("Canada")),
        ("GB", _("United Kingdom")),
        ("FR", _("France")),
        ("IT", _("Italy")),
        ("DE", _("Germany")),
        ("CH", _("Switzerland")),
        ("AE", _("United Arab Emirates")),
        ("SA", _("Saudi Arabia")),
        ("JP", _("Japan")),
        ("AU", _("Australia")),
    ]
    ADDRESS_TYPE_CHOICES = [
        ("shipping", _("Shipping Only")),
        ("billing", _("Billing Only")),
        ("both", _("Shipping & Billing")),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("user"),
    )
    label = models.CharField(
        _("label"),
        max_length=50,
        help_text=_("e.g., Home, Office, Parents"),
    )
    recipient_name = models.CharField(
        _("recipient name"),
        max_length=150,
    )
    phone_number = models.CharField(
        _("phone number"),
        max_length=30,
        help_text=_("Contact phone number for delivery and verification."),
    )
    company_name = models.CharField(
        _("company name"),
        max_length=100,
        blank=True,
    )
    address_line_1 = models.CharField(
        _("address line 1"),
        max_length=255,
    )
    address_line_2 = models.CharField(
        _("address line 2"),
        max_length=255,
        blank=True,
    )
    city = models.CharField(
        _("city"),
        max_length=100,
    )
    county_or_state = models.CharField(
        _("county / state / province"),
        max_length=100,
    )
    postal_code = models.CharField(
        _("postal code"),
        max_length=20,
        blank=True,
    )
    country = models.CharField(
        _("country"),
        max_length=2,
        choices=COUNTRY_CHOICES,
        default="US",
    )
    address_type = models.CharField(
        _("address type"),
        max_length=10,
        choices=ADDRESS_TYPE_CHOICES,
        default="both",
    )
    is_default_shipping = models.BooleanField(
        _("default shipping address"),
        default=False,
    )
    is_default_billing = models.BooleanField(
        _("default billing address"),
        default=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default_shipping", "-is_default_billing", "-updated_at"]

    def __str__(self) -> str:
        return f"{self.label} ({self.recipient_name}) - {self.city}, {self.country}"

    @property
    def formatted_address(self) -> str:
        """
        Return a clean, multi-line string representation of the address.
        """
        lines = [self.recipient_name]
        if self.company_name:
            lines.append(self.company_name)
        lines.append(self.address_line_1)
        if self.address_line_2:
            lines.append(self.address_line_2)

        city_line = f"{self.city}, {self.county_or_state}"
        if self.postal_code:
            city_line += f" {self.postal_code}"
        lines.append(city_line)

        country_display = self.get_country_display() if hasattr(self, "get_country_display") else self.country
        lines.append(str(country_display))
        return "\n".join(lines)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Save the address and atomically enforce that only one default shipping
        and one default billing address exist per user.
        """
        super().save(*args, **kwargs)
        if self.is_default_shipping:
            Address.objects.filter(
                user=self.user, is_default_shipping=True
            ).exclude(pk=self.pk).update(is_default_shipping=False)
        if self.is_default_billing:
            Address.objects.filter(
                user=self.user, is_default_billing=True
            ).exclude(pk=self.pk).update(is_default_billing=False)

