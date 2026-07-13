# settings/selectors.py
"""
settings/selectors.py
──────────────────────────────────────────────────────────────────────────────
Optimized read-only selectors for retrieving current store settings, branding
assets, active feature flags, currency/tax options, shipping thresholds, SEO
defaults, and maintenance mode status.

Leverages Django cache via `StoreSettings.load()` to avoid repeated database
lookups across high-frequency storefront queries.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from .models import StoreSettings


def get_store_settings() -> StoreSettings:
    """
    Retrieve the cached StoreSettings singleton instance.
    Returns the loaded model instance with zero DB hits on cache hits.
    """
    return StoreSettings.load()


def get_branding_assets() -> dict[str, Any]:
    """
    Get current store branding assets and theme colors.
    """
    settings = get_store_settings()
    return {
        "store_name": settings.store_name,
        "business_name": settings.business_name,
        "store_description": settings.store_description,
        "logo": settings.logo if settings.logo else None,
        "logo_url": settings.logo.url if settings.logo and hasattr(settings.logo, "url") else None,
        "favicon": settings.favicon if settings.favicon else None,
        "favicon_url": settings.favicon.url if settings.favicon and hasattr(settings.favicon, "url") else None,
        "primary_color": settings.primary_color,
        "secondary_color": settings.secondary_color,
        "accent_color": settings.accent_color,
        "footer_text": settings.footer_text,
        "announcement_banner_enabled": settings.announcement_banner_enabled,
        "announcement_banner_text": settings.announcement_banner_text,
        "default_placeholder_image": settings.default_placeholder_image if settings.default_placeholder_image else None,
    }


def get_branding() -> dict[str, Any]:
    """Alias for get_branding_assets()."""
    return get_branding_assets()


def get_branding_context() -> dict[str, Any]:
    """Alias for get_branding_assets()."""
    return get_branding_assets()


def get_active_feature_flags() -> dict[str, bool]:
    """
    Retrieve all active feature flags as a dictionary of booleans.
    Storefront views and templates respect these flags to show/hide features.
    """
    settings = get_store_settings()
    return {
        "wishlist": settings.feature_wishlist,
        "reviews": settings.feature_reviews,
        "compare": settings.feature_compare,
        "recently_viewed": settings.feature_recently_viewed,
        "promotions": settings.feature_promotions,
        "guest_checkout": settings.feature_guest_checkout,
    }


def get_feature_flags() -> dict[str, bool]:
    """Alias for get_active_feature_flags()."""
    return get_active_feature_flags()


def is_feature_enabled(feature_name: str) -> bool:
    """
    Check if a specific feature flag is currently enabled.
    Accepts full model attribute names ('feature_wishlist') or short names ('wishlist').
    """
    settings = get_store_settings()
    if not feature_name.startswith("feature_"):
        attr_name = f"feature_{feature_name}"
    else:
        attr_name = feature_name
    return getattr(settings, attr_name, False)


def get_seo_defaults() -> dict[str, Any]:
    """
    Retrieve default SEO metadata values for the site.
    """
    settings = get_store_settings()
    return {
        "default_meta_title": settings.default_meta_title,
        "default_meta_description": settings.default_meta_description,
        "default_og_image": settings.default_og_image if settings.default_og_image else None,
        "default_og_image_url": settings.default_og_image.url if settings.default_og_image and hasattr(settings.default_og_image, "url") else None,
        "default_social_share_description": settings.default_social_share_description,
        "robots_index_preference": settings.robots_index_preference,
    }


def get_currency_settings() -> dict[str, Any]:
    """
    Retrieve default currency, decimal precision, and tax calculation settings.
    """
    settings = get_store_settings()
    return {
        "default_currency": settings.default_currency,
        "currency_symbol": settings.currency_symbol,
        "decimal_precision": settings.decimal_precision,
        "tax_enabled": settings.tax_enabled,
        "tax_percentage": settings.tax_percentage,
        "tax_display_mode": settings.tax_display_mode,
    }


def get_shipping_settings() -> dict[str, Any]:
    """
    Retrieve shipping rules, thresholds, and estimated delivery messaging.
    """
    settings = get_store_settings()
    return {
        "free_shipping_threshold": settings.free_shipping_threshold,
        "flat_shipping_rate": settings.flat_shipping_rate,
        "local_pickup_enabled": settings.local_pickup_enabled,
        "estimated_delivery_message": settings.estimated_delivery_message,
        "default_shipping_policy": settings.default_shipping_policy,
    }


def get_social_links() -> dict[str, str]:
    """
    Retrieve configured social media URLs.
    """
    settings = get_store_settings()
    return {
        "facebook_url": settings.facebook_url,
        "instagram_url": settings.instagram_url,
        "twitter_url": settings.twitter_url,
        "tiktok_url": settings.tiktok_url,
        "youtube_url": settings.youtube_url,
        "linkedin_url": settings.linkedin_url,
    }


def get_store_policies() -> dict[str, str]:
    """
    Retrieve markdown text content for legal store policies.
    """
    settings = get_store_settings()
    return {
        "privacy_policy": settings.privacy_policy,
        "terms_and_conditions": settings.terms_and_conditions,
        "shipping_policy": settings.shipping_policy,
        "returns_policy": settings.returns_policy,
        "refund_policy": settings.refund_policy,
    }


def maintenance_enabled(request: Any = None) -> bool:
    """
    Check if maintenance mode is enabled globally.
    If an HTTP request object is passed, check if the user is authenticated staff
    or accessing an administrative path. Staff and admin paths bypass maintenance mode.
    """
    settings = get_store_settings()
    if not settings.maintenance_mode_enabled:
        return False

    if request is not None:
        # Check if user is staff
        if hasattr(request, "user") and request.user.is_authenticated and getattr(request.user, "is_staff", False):
            return False

        # Check if path is dashboard, admin, login, or static/media
        path = getattr(request, "path", "")
        if (
            path.startswith("/dashboard/") or
            path.startswith("/admin/") or
            path.startswith("/login") or
            path.startswith("/logout") or
            path.startswith("/static/") or
            path.startswith("/media/") or
            path.startswith("/__reload__")
        ):
            return False

    return True


def is_maintenance_mode_enabled(request: Any = None) -> bool:
    """Alias for maintenance_enabled(request)."""
    return maintenance_enabled(request)
