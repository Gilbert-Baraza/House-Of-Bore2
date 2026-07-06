"""
config/urls.py
──────────────────────────────────────────────────────────────────────────────
Root URL configuration for House-Of-Bore.

URLs for individual apps are registered here with include().
App-specific URL patterns live in each app's own urls.py file.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # App URL namespaces will be added here as each phase is implemented.
    path("", include("core.urls", namespace="core")),
    path("", include("products.urls", namespace="products")),
    # e.g.:
    #   path("accounts/", include("accounts.urls", namespace="accounts")),
]

# ─── Development-only URLs ────────────────────────────────────────────────────
# django-browser-reload: provides an SSE endpoint that the injected client
# script polls. The page reloads automatically whenever a file changes.
# Guarded by DEBUG so this endpoint is never exposed in production.
if settings.DEBUG:
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
