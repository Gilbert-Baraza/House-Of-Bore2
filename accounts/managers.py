"""
accounts/managers.py
──────────────────────────────────────────────────────────────────────────────
Custom manager for the User model.

WHY A CUSTOM MANAGER?
    Django's default UserManager assumes `username` is the primary identifier.
    Our User model uses `email` as USERNAME_FIELD, so we override `create_user`
    and `create_superuser` to enforce email normalisation and validation.

    Without this, `python manage.py createsuperuser` and `User.objects.create_user()`
    would still reference `username` internally and behave unexpectedly.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib.auth.models import UserManager as DjangoUserManager


class UserManager(DjangoUserManager):
    """
    Custom manager that uses email as the primary identifier.

    Inherits all default behaviour from Django's UserManager and only
    overrides the two factory methods to make email mandatory.
    """

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields,
    ) -> "User":  # type: ignore[name-defined]  # forward ref resolved at runtime
        """
        Core factory method used by `create_user` and `create_superuser`.

        Normalises the email address (lowercases the domain part) and raises
        a clear error if email is omitted, rather than letting Django raise a
        confusing IntegrityError later.
        """
        if not email:
            raise ValueError("An email address is required to create a user.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":  # type: ignore[name-defined]
        """Create and return a regular (non-staff, non-superuser) user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":  # type: ignore[name-defined]
        """
        Create and return a superuser.

        Called by `python manage.py createsuperuser`.
        Enforces that `is_staff` and `is_superuser` are both True — Django's
        admin will refuse access if either flag is missing.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)
