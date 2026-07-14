"""
config/settings/production.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Extends base.py with hardened, performance-optimised settings for the live
    server. All secrets are read from environment variables.

    Key differences from development:
      • DEBUG is False (no stack traces exposed to users)
      • PostgreSQL replaces SQLite
      • WhiteNoise serves static files without a separate CDN setup
      • HTTPS is enforced via SSL redirect, secure cookies, and HSTS
      • SMTP email backend for real transactional email
      • Celery tasks execute asynchronously via Redis (not eager)
      • Sentry error monitoring (conditional on SENTRY_DSN)
      • Cloudinary for media storage (conditional on CLOUDINARY_URL)
──────────────────────────────────────────────────────────────────────────────
"""

import logging

from decouple import Csv, config

from .base import *  # noqa: F401, F403 — intentional settings inheritance

# ─── Debug Mode ─────────────────────────────────────────────────────────────────
# CRITICAL: Debug must always be False in production.
# With DEBUG=True, Django serves detailed error pages that expose source code,
# local variables, and settings to anyone who triggers an error.
DEBUG = config("DEBUG", default=False, cast=bool)

# ─── Allowed Hosts ──────────────────────────────────────────────────────────────
# REQUIRED when DEBUG=False. Django rejects requests whose Host header does not
# match an entry in this list (prevents HTTP Host header poisoning attacks).
# Set in .env as a comma-separated string: e.g. "house-of-bore.com,www.house-of-bore.com"
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())

# ─── Database — PostgreSQL ───────────────────────────────────────────────────────
# PostgreSQL is used in production for reliability, concurrency, and performance.
# All credentials are read from environment variables — nothing is hardcoded.
# CONN_MAX_AGE=60 enables persistent database connections (connection pooling
# without a third-party pooler), reducing per-request connection overhead.
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,  # seconds — keep connections alive between requests
        "OPTIONS": {
            # Forces all queries to use a transaction, preventing partial writes
            # that could leave the database in an inconsistent state.
            "connect_timeout": 10,
            # PgBouncer compatibility: set to "prefer" when using PgBouncer
            # in transaction pooling mode. Comment out if not using PgBouncer.
            # "options": "-c search_path=public",
        },
    }
}

# ─── Static Files — WhiteNoise ────────────────────────────────────────────────
# WhiteNoise serves pre-compressed static files directly from Django, without
# needing Nginx or a CDN for static assets. Inserted right after
# SecurityMiddleware (index 1) so it can short-circuit requests early.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# CompressedManifestStaticFilesStorage:
#   • Adds a content-hash fingerprint to filenames (e.g. main.abc123.css)
#   • Enables far-future cache headers (files never change once deployed)
#   • Brotli/gzip compresses all text assets at collect time
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    # Default file storage for user uploads (MEDIA_ROOT).
    # Overridden below if Cloudinary is configured.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}


# ─── Cloudinary Media Storage ─────────────────────────────────────────────────
# When CLOUDINARY_URL is set, use Cloudinary for all user-uploaded media files.
# This offloads media serving to a global CDN with automatic image optimization.
_cloudinary_url = config("CLOUDINARY_URL", default="")
if _cloudinary_url:
    INSTALLED_APPS += ["cloudinary_storage", "cloudinary"]  # type: ignore[name-defined]
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }
    # Cloudinary SDK reads CLOUDINARY_URL from the environment automatically.
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"


# ─── Celery (production) ──────────────────────────────────────────────────────
# In production, tasks MUST execute asynchronously via Redis.
#Set to True in production — it would bypass the entire task queue.
CELERY_TASK_ALWAYS_EAGER = False


# ─── Security — HTTPS Enforcement ─────────────────────────────────────────────

# Redirects all plain HTTP requests to HTTPS.
# Ensure your server or load balancer terminates SSL before enabling this.
SECURE_SSL_REDIRECT = True

# Trust the X-Forwarded-Proto header from a reverse proxy (Nginx, load balancer).
# Without this, Django cannot detect that the original request was HTTPS and
# SECURE_SSL_REDIRECT would cause an infinite redirect loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── Security — Secure Cookies ─────────────────────────────────────────────────

# Prevents session cookie from being sent over plain HTTP connections.
# Attackers cannot steal session tokens via network sniffing.
SESSION_COOKIE_SECURE = True

# Prevents CSRF cookie from being sent over plain HTTP connections.
CSRF_COOKIE_SECURE = True

# Prevents JavaScript from accessing the session cookie (mitigates XSS attacks).
SESSION_COOKIE_HTTPONLY = True

# SameSite — prevent cross-site cookie leakage
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ─── Security — HSTS (HTTP Strict Transport Security) ─────────────────────────
# HSTS tells browsers to ALWAYS use HTTPS for this domain for the next year,
# even if the user types "http://". This prevents protocol downgrade attacks.
#
# ⚠️  START with a small value (e.g. 300 seconds) to test, then increase to
#     31536000 (1 year) once you are certain HTTPS is working correctly.
#     A misconfigured HSTS can lock users out of your site for months.
SECURE_HSTS_SECONDS = 31536000  # 1 year

# Apply HSTS to all subdomains (e.g. www.house-of-bore.com, api.house-of-bore.com).
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Allows the domain to be included in browser HSTS preload lists.
# Only enable after the domain has been registered at https://hstspreload.org/
SECURE_HSTS_PRELOAD = True

# ─── Security — Content Security Policy (foundation) ─────────────────────────
# A restrictive CSP prevents XSS by controlling which sources can load scripts,
# styles, images, etc. Start with report-only mode, then enforce.
# Implemented via Nginx headers (see deploy/nginx/house_of_bore.conf) rather
# than Django middleware to avoid template complexity with nonces.

# ─── CSRF Trusted Origins ─────────────────────────────────────────────────────
# Required for CSRF validation when requests come through a reverse proxy.
# Set in .env as: CSRF_TRUSTED_ORIGINS=https://house-of-bore.com,https://www.house-of-bore.com
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# ─── Email — SMTP ─────────────────────────────────────────────────────────────
# Sends real transactional emails (order confirmations, password resets, etc.)
# Configure SMTP credentials in .env. Gmail shown as example — use a
# transactional email service (SendGrid, Mailgun, SES) in production.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="House of Bore <noreply@house-of-bore.com>",
)


# ─── Caching (production — Redis with django-redis) ──────────────────────────
# Override base.py cache with django-redis for production features:
# connection pooling, compression, and Sentinel support.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
        },
        "KEY_PREFIX": "hob",
        "TIMEOUT": 300,
    }
}


# ─── Logging (production) ─────────────────────────────────────────────────────
# Override base.py logging levels for production: less verbose, focus on
# warnings and errors. Console handler uses structured format for log aggregation.
LOGGING["loggers"]["django"]["level"] = "WARNING"  # type: ignore[name-defined]
LOGGING["loggers"]["django.request"]["level"] = "ERROR"  # type: ignore[name-defined]
LOGGING["loggers"]["payments"]["level"] = "WARNING"  # type: ignore[name-defined]
LOGGING["loggers"]["celery"]["level"] = "WARNING"  # type: ignore[name-defined]
LOGGING["root"]["level"] = "WARNING"  # type: ignore[name-defined]


# ─── Sentry Error Monitoring ─────────────────────────────────────────────────
# Conditional initialization: Sentry is only activated when SENTRY_DSN is set
# in the environment. This allows the same codebase to run without Sentry
# during staging or early deployment phases.
_sentry_dsn = config("SENTRY_DSN", default="")
if _sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=_sentry_dsn,
            # Capture 10% of transactions for performance monitoring.
            # Increase in staging, decrease in high-traffic production.
            traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float),
            # Associate errors with the latest Git commit for release tracking.
            release=config("SENTRY_RELEASE", default="house-of-bore@latest"),
            environment=config("SENTRY_ENVIRONMENT", default="production"),
            # Send user context (email, ID) with errors for debugging.
            send_default_pii=True,
        )
    except ImportError:
        logger = logging.getLogger("django")
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Install with: pip install sentry-sdk[django]"
        )
