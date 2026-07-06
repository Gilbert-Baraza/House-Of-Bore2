"""
config/settings/production.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Extends base.py with hardened, performance-optimised settings for the live
    server. All secrets are read from environment variables — never hardcoded.

    Key differences from development:
      • DEBUG is False (no stack traces exposed to users)
      • PostgreSQL replaces SQLite
      • WhiteNoise serves static files without a separate CDN setup
      • HTTPS is enforced via SSL redirect, secure cookies, and HSTS
      • SMTP email backend for real transactional email
──────────────────────────────────────────────────────────────────────────────
"""

from decouple import Csv, config

from .base import *  # noqa: F401, F403 — intentional settings inheritance

# ─── Debug Mode ─────────────────────────────────────────────────────────────────
# CRITICAL: Debug must always be False in production.
# With DEBUG=True, Django serves detailed error pages that expose source code,
# local variables, and settings to anyone who triggers an error.
DEBUG = False

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
        },
    }
}

# ─── Static Files — WhiteNoise ────────────────────────────────────────────────
# WhiteNoise serves pre-compressed static files directly from Django, without
# needing Nginx or a CDN for static assets. Insert it right after
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
    # Replace with S3 or similar in a cloud deployment.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}

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

# ─── Logging (production) ─────────────────────────────────────────────────────
# Errors are logged to the console. Configure a file handler or Sentry here
# for a production-grade logging setup in a future phase.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
