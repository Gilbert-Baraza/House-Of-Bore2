# settings/context_processors.py
"""
settings/context_processors.py
──────────────────────────────────────────────────────────────────────────────
Global context processor injecting Store Settings into every template context.

Exposes:
- `store_settings`: Singleton StoreSettings instance.
- `branding`: Branding colors, logo, and announcement banner details.
- `feature_flags`: Boolean flags (`wishlist`, `reviews`, `compare`, etc.).
- `seo_defaults`: Default meta titles, descriptions, and Open Graph assets.
- `currency_settings`: Currency symbol, code, and tax display rules.
- `shipping_settings`: Free shipping threshold and delivery message.
- `social_links`: Configured social media profile links.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.http import HttpRequest
from .selectors import (
    get_active_feature_flags,
    get_branding_assets,
    get_currency_settings,
    get_seo_defaults,
    get_shipping_settings,
    get_social_links,
    get_store_settings,
)


def store_settings(request: HttpRequest) -> dict[str, Any]:
    """
    Template context processor exposing site configuration across all templates.
    Fetches the StoreSettings singleton exactly once per request render.
    """
    settings_instance = get_store_settings()
    return {
        "store_settings": settings_instance,
        "branding": get_branding_assets(settings_instance),
        "feature_flags": get_active_feature_flags(settings_instance),
        "seo_defaults": get_seo_defaults(settings_instance),
        "currency_settings": get_currency_settings(settings_instance),
        "shipping_settings": get_shipping_settings(settings_instance),
        "social_links": get_social_links(settings_instance),
    }
