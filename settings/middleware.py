# settings/middleware.py
"""
settings/middleware.py
──────────────────────────────────────────────────────────────────────────────
Middleware enforcing global maintenance mode across the public storefront.

If `StoreSettings.maintenance_mode_enabled` is True:
- Public storefront requests (`/`, `/products/`, `/cart/`, etc.) receive a
  branded HTTP 503 (`Service Unavailable`) response rendered via
  `settings/maintenance_page.html`.
- Authenticated staff users (`is_staff=True`) bypass maintenance mode and can
  continue browsing, testing, and administering the site without disruption.
- Administrative paths (`/dashboard/`, `/admin/`), authentication paths
  (`/login`, `/logout`), static assets (`/static/`), and uploaded media
  (`/media/`) bypass maintenance mode automatically.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Callable
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from .selectors import (
    get_branding_assets,
    get_social_links,
    get_store_settings,
    maintenance_enabled,
)


class MaintenanceModeMiddleware:
    """
    Middleware checking whether the public storefront should display the maintenance screen.
    Does not require server restarts upon configuration toggle.
    """
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if maintenance_enabled(request):
            settings_instance = get_store_settings()
            context = {
                "store_settings": settings_instance,
                "branding": get_branding_assets(),
                "social_links": get_social_links(),
            }
            return render(request, "settings/maintenance_page.html", context, status=503)

        return self.get_response(request)
