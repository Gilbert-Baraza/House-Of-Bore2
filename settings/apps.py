# settings/apps.py
"""
settings/apps.py
──────────────────────────────────────────────────────────────────────────────
App configuration for the Store Settings module.
──────────────────────────────────────────────────────────────────────────────
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SettingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "settings"
    verbose_name = _("Store Settings & Configuration")
