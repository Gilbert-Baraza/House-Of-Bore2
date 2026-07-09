"""
config/urls.py
──────────────────────────────────────────────────────────────────────────────
Root URL configuration for House-Of-Bore.

URLs for individual apps are registered here with include().
App-specific URL patterns live in each app's own urls.py file.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # App URL namespaces will be added here as each phase is implemented.
    path("", include("core.urls", namespace="core")),
    path("", include("products.urls", namespace="products")),
    path("reviews/", include("reviews.urls", namespace="reviews")),
    path("wishlist/", include("wishlist.urls", namespace="wishlist")),
    path("cart/", include("cart.urls", namespace="cart")),
    path("checkout/", include("checkout.urls", namespace="checkout")),
    path("pricing/", include("pricing.urls", namespace="pricing")),
    path("", include("orders.urls", namespace="orders")),
    path("", include("accounts.urls", namespace="accounts")),
]

# ─── Development-only URLs ────────────────────────────────────────────────────
# django-browser-reload: provides an SSE endpoint that the injected client
# script polls. The page reloads automatically whenever a file changes.
# Guarded by DEBUG so this endpoint is never exposed in production.
if settings.DEBUG:
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
