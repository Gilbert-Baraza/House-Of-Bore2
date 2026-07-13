"""
config/settings/development.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Extends base.py with settings that are safe and convenient for local
    development only. Debug mode is enabled, SQLite is used (no external DB
    server needed), HTTPS restrictions are disabled, and emails are printed
    to the console.

    NEVER use these settings in production — DEBUG=True leaks stack traces
    and sensitive data to any browser that triggers an error.
──────────────────────────────────────────────────────────────────────────────
"""

from decouple import Csv, config

from .base import *  # noqa: F401, F403 — intentional settings inheritance

# ─── Debug Mode ─────────────────────────────────────────────────────────────────
# Enables detailed error pages with full stack traces and variable values.
# Only ever True in development.
DEBUG = True

# ─── Allowed Hosts ──────────────────────────────────────────────────────────────
# Django checks this list when DEBUG=False to prevent HTTP Host header attacks.
# In development with DEBUG=True, this check is bypassed anyway — but we keep
# sensible defaults so switching to DEBUG=False locally doesn't break anything.
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=Csv(),
)

# ─── Database — SQLite ──────────────────────────────────────────────────────────
# SQLite requires zero configuration and has no external dependencies.
# It lives in a single file at the project root, perfect for local development.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # BASE_DIR inherited from base.py
    }
}

# ─── Email Backend ───────────────────────────────────────────────────────────────
# Prints all outgoing emails to the terminal instead of actually sending them.
# This lets you inspect email content (password resets, order confirmations)
# without needing an SMTP server or creating test accounts.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ─── Security (relaxed for development) ─────────────────────────────────────────
# HTTPS-related settings are intentionally disabled here.
# Enabling them on localhost would redirect http:// → https:// and break
# the development server, which does not serve HTTPS.

# Do NOT redirect HTTP → HTTPS on localhost.
SECURE_SSL_REDIRECT = False

# Session and CSRF cookies do not require HTTPS in development.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Disable HSTS in development — it would instruct browsers to remember to
# use HTTPS for this domain, which would break future plain-HTTP dev sessions.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


# ─── Caching (development) ─────────────────────────────────────────────────────
# Use Redis if available (for full fidelity testing), with LocMemCache as
# fallback if Redis is not running locally. Override the base.py Redis cache.
try:
    import redis as _redis_lib
    _r = _redis_lib.Redis.from_url(
        config("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
        socket_connect_timeout=1,
    )
    _r.ping()
    # Redis is available — use it for full fidelity with production
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
            "KEY_PREFIX": "hob_dev",
            "TIMEOUT": 300,
        }
    }
except Exception:
    # Redis not available — fall back to in-memory cache for development
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "hob-dev-cache",
        }
    }
    # Also set Celery to eager mode when Redis is unavailable
    CELERY_TASK_ALWAYS_EAGER = True


# ─── Logging (development) ──────────────────────────────────────────────────────
# Override base.py logging: reduce console noise, keep file handlers from base.
LOGGING["loggers"]["django"]["level"] = "INFO"  # type: ignore[name-defined]
LOGGING["loggers"]["django.request"]["level"] = "DEBUG"  # type: ignore[name-defined]
LOGGING["root"]["level"] = "INFO"  # type: ignore[name-defined]


# ─── Browser Reload (development only) ──────────────────────────────────────────
# django-browser-reload automatically refreshes the browser when Python or
# template files change. It's part of the django-tailwind[reload] extras and
# is ONLY active when DEBUG=True (this file). Never enabled in production.
#
# HOW IT WORKS:
#   The middleware injects a small <script> tag before </body> on every HTML
#   response. That script opens a long-polling SSE connection to the
#   __reload__/ endpoint. When the dev server detects a file change, it sends
#   an event that triggers an instant page refresh — no manual F5 needed.
INSTALLED_APPS += ["django_browser_reload"]  # type: ignore[name-defined]

MIDDLEWARE += [  # type: ignore[name-defined]
    # Must be last in the list — it only acts on the final HTML response.
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]
