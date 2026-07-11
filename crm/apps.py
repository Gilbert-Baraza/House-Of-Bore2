# crm/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm"
    verbose_name = _("Customer Relationship Management")

    def ready(self) -> None:
        import crm.signals  # noqa: F401
