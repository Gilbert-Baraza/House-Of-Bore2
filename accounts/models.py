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

from django.contrib.auth.models import AbstractUser
from django.db import models
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
