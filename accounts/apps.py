"""
accounts/apps.py
──────────────────────────────────────────────────────────────────────────────
App configuration for the accounts app.
──────────────────────────────────────────────────────────────────────────────
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configuration for the accounts application."""

    # Use 64-bit integers for all auto-generated primary keys in this app.
    # Matches the project-wide DEFAULT_AUTO_FIELD setting in base.py.
    default_auto_field = "django.db.models.BigAutoField"

    name = "accounts"
    verbose_name = "Accounts"
