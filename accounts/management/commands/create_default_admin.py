"""
accounts/management/commands/create_default_admin.py
──────────────────────────────────────────────────────────────────────────────
Management command to automatically create a default superuser account during
automated, non-interactive deployments on platforms such as Render Free.

WHY THIS COMMAND EXISTS:
    Platforms like Render Free deploy applications via automated CI/CD build
    and release pipelines (`build.sh`). Interactive terminal sessions or
    interactive prompts (`python manage.py createsuperuser`) cannot be used
    during automated builds or non-interactive container deployments without
    hanging or crashing the deployment pipeline.

    This command safely bootstraps the initial administrator account without
    requiring manual intervention or interactive terminal input.

BEHAVIOUR & IDEMPOTENCY:
    1. Reads `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and
       `DJANGO_SUPERUSER_PASSWORD` exclusively from environment/settings.
    2. Validates that all three required credentials exist and are non-empty.
       If any value is missing or empty, prints a clear warning and exits
       gracefully with status code 0 (never fails deployment due to absent vars).
    3. Checks if an administrator with the configured identifier (email or
       username depending on the custom User model) already exists. If found,
       skips account creation to guarantee strict idempotency across repeated
       deployments.
    4. Creates the superuser using `get_user_model().objects.create_superuser()`
       inside an atomic database transaction.

SECURITY:
    - Never commits, hardcodes, or exposes administrator credentials.
    - Credentials must exist only in deployment environment variables.
    - Never logs passwords or sensitive variables in terminal outputs or tracebacks.
──────────────────────────────────────────────────────────────────────────────
"""

import sys
from typing import Any
from decouple import config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.utils import timezone

class Command(BaseCommand):
    """
    Automated, idempotent, non-interactive superuser creation command.
    Safe for production execution during CI/CD and PaaS deployments.
    """
    help = "Creates a default superuser from environment variables if one does not already exist."

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Execute the superuser creation flow.
        """
        # Read credentials exclusively from settings or environment variables
        username = str(getattr(settings, "DJANGO_SUPERUSER_USERNAME", "") or config("DJANGO_SUPERUSER_USERNAME", default="")).strip()
        email = str(getattr(settings, "DJANGO_SUPERUSER_EMAIL", "") or config("DJANGO_SUPERUSER_EMAIL", default="")).strip()
        password = str(getattr(settings, "DJANGO_SUPERUSER_PASSWORD", "") or config("DJANGO_SUPERUSER_PASSWORD", default="")).strip()

        # 1. Validation: Verify all required credentials exist and are non-empty
        if not username or not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: Missing environment variables.\n"
                    "Skipping default admin creation.\n"
                    "Required environment variables are missing."
                )
            )
            return

        User = get_user_model()
        model_field_names = {f.name for f in User._meta.get_fields() if hasattr(f, "name")}

        # 2. Idempotency Check: Verify whether the administrator account already exists
        # Check by USERNAME_FIELD first (primary unique identifier in Django auth)
        username_field = getattr(User, "USERNAME_FIELD", "username")
        identifier_value = email if username_field == "email" else username

        # Check existing user matching primary login identifier
        existing_query = models.Q(**{username_field: identifier_value})

        # Additionally check email or username fields if present on the active model
        # to prevent duplicate creation errors or partial matches
        if "email" in model_field_names and username_field != "email":
            existing_query |= models.Q(email__iexact=email)
        if "username" in model_field_names and username_field != "username":
            existing_query |= models.Q(username__iexact=username)

        try:
            if User._default_manager.filter(existing_query).exists():
                self.stdout.write(
                    self.style.WARNING(
                        "WARNING: Default administrator already exists.\n"
                        "Skipping creation."
                    )
                )
                return
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"ERROR: Failed to query existing administrator accounts: {type(exc).__name__}"
                )
            )
            raise CommandError("Database query failure during default superuser check.") from exc

        # 3. Administrator Creation
        try:
            superuser_kwargs = self._prepare_superuser_kwargs(
                User, username_field, model_field_names, username, email, password
            )
            with transaction.atomic():
                User._default_manager.create_superuser(**superuser_kwargs)

            self.stdout.write(
                self.style.SUCCESS(
                    "SUCCESS: Default administrator created successfully."
                )
            )
        except Exception as exc:
            # Catch unexpected exceptions without exposing passwords or sensitive values
            self.stderr.write(
                self.style.ERROR(
                    f"ERROR: An unexpected exception occurred during default superuser creation: {type(exc).__name__}"
                )
            )
            # Return a non-zero exit status for genuine creation errors when credentials were provided
            raise CommandError("Failed to create default administrator.") from exc

    def _prepare_superuser_kwargs(
        self,
        User: Any,
        username_field: str,
        model_field_names: set[str],
        username: str,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        """
        Prepare keyword arguments for create_superuser, ensuring compatibility
        with custom User models and populating any required extra fields.
        """
        kwargs: dict[str, Any] = {
            "password": password,
        }

        # Set the USERNAME_FIELD value
        if username_field == "email":
            kwargs["email"] = email
        else:
            kwargs[username_field] = username
            if "email" in model_field_names:
                kwargs["email"] = email

        # Populate username if present on the model and not yet set
        if "username" in model_field_names and "username" not in kwargs:
            kwargs["username"] = username

        # Populate any additional REQUIRED_FIELDS declared on the custom User model
        required_fields = getattr(User, "REQUIRED_FIELDS", [])
        for field_name in required_fields:
            if field_name in kwargs:
                continue
            if field_name == "username" and "username" in model_field_names:
                kwargs["username"] = username
            elif field_name == "email" and "email" in model_field_names:
                kwargs["email"] = email
            else:
                # Dynamically assign sensible defaults for project-specific custom mandatory fields
                kwargs[field_name] = self._get_default_for_field(User, field_name)

        return kwargs

    def _get_default_for_field(self, User: Any, field_name: str) -> Any:
        """
        Inspect model field definitions to return sensible default values for
        custom required fields without hardcoding project-specific values.
        """
        try:
            field = User._meta.get_field(field_name)
            if field.has_default():
                return field.get_default()
            if isinstance(field, (models.CharField, models.TextField, models.SlugField)):
                return ""
            if isinstance(field, models.BooleanField):
                return True
            if isinstance(field, models.IntegerField):
                return 0
            if isinstance(field, models.FloatField):
                return 0.0
            if isinstance(field, models.DateField):
                return timezone.now().date()
            if isinstance(field, models.DateTimeField):
                return timezone.now()
        except Exception:
            pass
        return ""
