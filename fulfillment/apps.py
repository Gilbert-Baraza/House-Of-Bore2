# fulfillment/apps.py
"""
fulfillment/apps.py
──────────────────────────────────────────────────────────────────────────────
AppConfig for the `fulfillment` application. Ensures signal handlers and RBAC
permissions are registered when Django starts.
──────────────────────────────────────────────────────────────────────────────
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FulfillmentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fulfillment"
    verbose_name = _("Order Fulfillment & Shipping Operations")

    def ready(self) -> None:
        try:
            import fulfillment.signals  # noqa: F401
        except ImportError:
            pass
