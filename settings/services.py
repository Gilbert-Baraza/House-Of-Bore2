# settings/services.py
"""
settings/services.py
──────────────────────────────────────────────────────────────────────────────
Transactional business logic and update operations for Store Settings.

Handles safe modifications to the `StoreSettings` singleton model with explicit
AuditLog recording and immediate cache invalidation (`cache.delete()`).
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.db import transaction
from dashboard.services import create_audit_log
from .models import StoreSettings
from .selectors import (
    get_branding,
    get_currency_settings,
    get_seo_defaults,
    get_shipping_settings,
    get_store_settings as selector_get_store_settings,
    maintenance_enabled,
)


def get_store_settings() -> StoreSettings:
    """
    Retrieve the active StoreSettings instance.
    Delegates to the cached selector for optimal performance.
    """
    return selector_get_store_settings()


@transaction.atomic
def update_store_settings(user: Any, section_name: str, ip_address: str | None = None, **fields: Any) -> StoreSettings:
    """
    Update attributes of the StoreSettings singleton.
    Performs atomic database save, triggers cache invalidation, and logs an AuditLog entry.
    """
    instance = StoreSettings.load()

    # Update only provided fields that exist on the model
    updated_field_names = []
    for key, value in fields.items():
        if hasattr(instance, key):
            setattr(instance, key, value)
            updated_field_names.append(key)

    instance.save()

    # Create immutable audit record
    if user and hasattr(user, "is_authenticated") and user.is_authenticated:
        description = f"Updated store settings section [{section_name}]. Fields modified: {', '.join(updated_field_names) if updated_field_names else 'None'}"
        create_audit_log(
            user=user,
            action="UPDATE",
            description=description[:512],
            model_name="StoreSettings",
            object_id="1",
            ip_address=ip_address,
        )

    return instance


@transaction.atomic
def update_store_file_asset(user: Any, field_name: str, file_obj: Any, ip_address: str | None = None) -> StoreSettings:
    """
    Update an image or file asset on the StoreSettings singleton (e.g., logo, favicon, og_image).
    """
    instance = StoreSettings.load()
    if hasattr(instance, field_name) and file_obj:
        setattr(instance, field_name, file_obj)
        instance.save()

        if user and hasattr(user, "is_authenticated") and user.is_authenticated:
            create_audit_log(
                user=user,
                action="UPDATE",
                description=f"Updated store configuration file asset: {field_name}",
                model_name="StoreSettings",
                object_id="1",
                ip_address=ip_address,
            )

    return instance


# Exported aliases required by architectural contract
__all__ = [
    "get_store_settings",
    "update_store_settings",
    "update_store_file_asset",
    "get_branding",
    "get_currency_settings",
    "get_shipping_settings",
    "get_seo_defaults",
    "maintenance_enabled",
]
