# cart/apps.py
"""
cart/apps.py
──────────────────────────────────────────────────────────────────────────────
App configuration for the cart application.
──────────────────────────────────────────────────────────────────────────────
"""

from django.apps import AppConfig


class CartConfig(AppConfig):
    """Configuration for the shopping cart application."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "cart"
    verbose_name = "Shopping Cart"

    def ready(self) -> None:
        import cart.signals  # noqa: F401
