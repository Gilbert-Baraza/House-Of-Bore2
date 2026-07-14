"""
config/settings/base.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Contains every setting that is identical across development and
    production. Environment-specific files (development.py / production.py)
    import from here and only override what differs.

    Keeping shared settings here prevents duplication and ensures a single
    source of truth for app registration, middleware, templates, etc.
──────────────────────────────────────────────────────────────────────────────
"""

from pathlib import Path

from decouple import Csv, config

# ─── Paths ─────────────────────────────────────────────────────────────────────
# Resolve the project root (two levels above this file: settings/ → config/ → root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Logs Directory ────────────────────────────────────────────────────────────
# Ensure the logs directory exists for rotating file handlers.
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# ─── Security ──────────────────────────────────────────────────────────────────
# SECRET_KEY is read exclusively from the environment.
SECRET_KEY = config("SECRET_KEY")


# ─── Application Definition ────────────────────────────────────────────────────
# Split into three groups for readability and to make it easy to identify
# which apps are first-party vs third-party vs Django built-ins.

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]


LOCAL_APPS = [
    "accounts",      # Custom user model, authentication, profiles
    "core",          # Home page, static pages (about, contact)
    "products",      # Product catalogue, categories, variants
    "cart",          # Shopping cart (session-based)
    "checkout",      # Checkout progress and session management
    "pricing",       # Centralized pricing engine, promotions, coupons
    "orders",        # Order management and history
    "payments",      # Payment gateway integration
    "reviews",       # Product reviews and ratings
    "wishlist",      # User product wishlists
    "dashboard",     # Staff/seller or customer account dashboard
    "notifications", # Centralized, event-driven transactional communications
    "inventory",     # Inventory management, ledger, and stock controls
    "fulfillment",   # Order fulfillment, picking, packing, shipping, and returns workflow
    "crm",           # Customer Relationship Management (CRM) 360° profile & timeline
    "settings",      # Store configuration, branding, policies & feature flags
]


THIRD_PARTY_APPS = [
    # Third-party apps required in all environments
]

DEV_ONLY_APPS = [
    # django-tailwind
    "tailwind",
    "theme",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

DJANGO_ENV = config("DJANGO_ENV", default="development")

if DJANGO_ENV == "development":
    INSTALLED_APPS += DEV_ONLY_APPS

# ─── Middleware ─────────────────────────────────────────────────────────────────
# Order matters — security and session middleware must come first.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise (static files) is inserted here in production.py (index 1).
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Protects against clickjacking by setting the X-Frame-Options header.
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Enforces configurable zero-downtime maintenance mode for public storefront visitors.
    "settings.middleware.MaintenanceModeMiddleware",
]

ROOT_URLCONF = "config.urls"


# ─── Templates ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Include the project-level templates/ directory so base.html and
        # shared components are resolved before app-level templates.
        "DIRS": [BASE_DIR / "templates"],
        # Also allow each app to have its own templates/<app_name>/ folder.
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                # Exposes the current HttpRequest object to all templates.
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                # Makes the authenticated User object available in templates.
                "django.contrib.auth.context_processors.auth",
                # Makes Django messages (flash alerts) available in templates.
                "django.contrib.messages.context_processors.messages",
                "wishlist.context_processors.wishlist_status",
                "cart.context_processors.cart",
                "settings.context_processors.store_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ─── Authentication ─────────────────────────────────────────────────────────────
# AUTH_USER_MODEL tells Django to use our custom User model instead of the
# default django.contrib.auth.User.
#
#    Custom User model created in accounts/models.py.
#    This is set before any migration is applied — see accounts/models.py
#    for a full explanation of why changing AUTH_USER_MODEL later is so difficult.
#
AUTH_USER_MODEL = "accounts.User"

# Where to redirect unauthenticated users who try to access a protected view.
LOGIN_URL = "/login/"

# Where to redirect users after a successful login (if no 'next' param present).
LOGIN_REDIRECT_URL = "/"

# Where to redirect users after they log out.
LOGOUT_REDIRECT_URL = "/"

# Authentication backends supporting case-insensitive email login and default ModelBackend
AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailAuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# ─── Password Validation ────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        # Rejects passwords that are too similar to the user's personal info.
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        # Enforces a minimum password length (default: 8 characters).
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        # Rejects commonly used passwords (checked against a built-in list).
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        # Rejects passwords that are entirely numeric.
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ─── Internationalization ────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"

# East Africa Time — adjust to your deployment region if needed.
# Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIME_ZONE = "Africa/Nairobi"

# Enable Django's translation framework (required for i18n middleware).
USE_I18N = True

# Store all datetimes as UTC in the database; convert to TIME_ZONE for display.
# This is the safest approach for production systems handling multiple timezones.
USE_TZ = True


# ─── Static Files ───────────────────────────────────────────────────────────────
# URL prefix for static files served in development.
STATIC_URL = "/static/"

# Additional directories where Django will look for static files.
# The project-level static/ folder holds global CSS, JS, images, and fonts.
STATICFILES_DIRS = [BASE_DIR / "static"]

# The directory where 'collectstatic' gathers all static files for deployment.
# This folder should be served by WhiteNoise (production) or a web server.
STATIC_ROOT = BASE_DIR / "staticfiles"


# ─── Media Files ────────────────────────────────────────────────────────────────
# URL prefix for user-uploaded files (product images, avatars, etc.).
MEDIA_URL = "/media/"

# Filesystem path where uploaded files are saved.
# This directory must be writable by the web server process.
MEDIA_ROOT = BASE_DIR / "media"


# ─── Default Primary Key ────────────────────────────────────────────────────────
# Use BigAutoField (64-bit integer) for all auto-generated primary keys.
# More future-proof than the default 32-bit AutoField for large tables.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Tailwind CSS ───────────────────────────────────────────────────────────────
# Tells django-tailwind which app holds the Tailwind configuration.
# This app is created by `python manage.py tailwind init`.

# On Windows, Python cannot always locate 'npm' through the system PATH because
# npm is registered as 'npm.cmd' (a batch wrapper). Specifying the full path to
# npm.cmd ensures `manage.py tailwind install` and `tailwind build` work reliably.


# ─── Security Headers (applied in all environments) ────────────────────────────

# Prevents the page from being embedded in a <frame>, <iframe>, or <object>.
# DENY is stricter than SAMEORIGIN and appropriate for e-commerce checkouts.
X_FRAME_OPTIONS = "DENY"

# Sets the X-Content-Type-Options: nosniff header.
# Prevents browsers from guessing (sniffing) the MIME type, which can lead
# to security vulnerabilities when serving user-uploaded content.
SECURE_CONTENT_TYPE_NOSNIFF = True

# Controls the Referer header sent with outgoing requests.
# "strict-origin-when-cross-origin" sends full URL for same-origin but only
# the origin for cross-origin requests — good balance of privacy and analytics.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ─── Cookie Security (base defaults — overridden per environment) ──────────────

# Prevent JavaScript from reading session cookies (XSS mitigation).
SESSION_COOKIE_HTTPONLY = True

# SameSite="Lax" blocks cross-site POST requests from sending cookies,
# preventing CSRF attacks while allowing normal navigation links.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True

# ─── Upload & Payload Limits ───────────────────────────────────────────────────

# Maximum size (bytes) for file uploads held in memory before writing to disk.
# 10 MB — prevents denial-of-service via oversized uploads.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# Maximum size (bytes) for the entire request body (POST data + files).
# 5 MB — protects webhook endpoints from oversized payloads.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB


# ─── Notifications & Email Defaults ─────────────────────────────────────────────
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="House of Bore <noreply@houseofbore.com>")


# ─── Redis ──────────────────────────────────────────────────────────────────────
# Central Redis URL used by cache, sessions, Celery, and rate limiting.
REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/0")


# ─── Caching ───────────────────────────────────────────────────────────────────
# Django 4.0+ native Redis cache backend. Uses the same Redis instance as Celery
# but on a different database number to prevent key collisions.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "db": 1,
        },
        "KEY_PREFIX": "hob",
        "TIMEOUT": 300,  # 5 minutes default TTL
    }
}


# ─── Sessions ──────────────────────────────────────────────────────────────────
# Cache-backed sessions provide faster reads than database sessions while
# automatically persisting through Django's cache framework (backed by Redis).
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days


# ─── Celery Configuration ───────────────────────────────────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)

# In development, execute tasks eagerly without requiring a live Redis daemon.
# Overridden to False in production.py.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# Serialization
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Task execution limits — prevent runaway tasks from consuming resources.
CELERY_TASK_SOFT_TIME_LIMIT = 300   # 5 minutes soft limit (raises SoftTimeLimitExceeded)
CELERY_TASK_TIME_LIMIT = 600        # 10 minutes hard kill
CELERY_TASK_ACKS_LATE = True        # Acknowledge tasks after execution, not before
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fetch one task at a time (fair scheduling)

# Result expiry — discard results after 24 hours to prevent Redis bloat.
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # 24 hours

# Task routing — group tasks by priority for future worker scaling.
CELERY_TASK_ROUTES = {
    "payments.tasks.*": {"queue": "high_priority"},
    "notifications.tasks.*": {"queue": "high_priority"},
    "orders.tasks.*": {"queue": "default"},
    "inventory.tasks.*": {"queue": "default"},
    "fulfillment.tasks.*": {"queue": "default"},
    "core.tasks.*": {"queue": "low_priority"},
}

# ─── Celery Beat — Periodic Task Schedule ───────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # ── Orders ──────────────────────────────────────────────────────────────
    "expire-pending-payments": {
        "task": "orders.tasks.expire_pending_payments",
        "schedule": crontab(minute=0),  # Every hour, on the hour
        "options": {"queue": "default"},
    },
    "clear-abandoned-carts": {
        "task": "orders.tasks.clear_abandoned_carts",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3:00 AM
        "options": {"queue": "low_priority"},
    },

    # ── Inventory ───────────────────────────────────────────────────────────
    "generate-inventory-alerts": {
        "task": "inventory.tasks.generate_inventory_alerts",
        "schedule": crontab(minute=0, hour="*/4"),  # Every 4 hours
        "options": {"queue": "default"},
    },

    # ── Fulfillment ─────────────────────────────────────────────────────────
    "check-overdue-fulfillments": {
        "task": "fulfillment.tasks.check_overdue_fulfillments",
        "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours
        "options": {"queue": "default"},
    },
    "check-delivery-exceptions": {
        "task": "fulfillment.tasks.check_delivery_exceptions",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        "options": {"queue": "default"},
    },

    # ── Maintenance ─────────────────────────────────────────────────────────
    "cleanup-expired-sessions": {
        "task": "core.tasks.cleanup_expired_sessions",
        "schedule": crontab(hour=4, minute=0),  # Daily at 4:00 AM
        "options": {"queue": "low_priority"},
    },
    "cleanup-temp-files": {
        "task": "core.tasks.cleanup_temp_files",
        "schedule": crontab(hour=5, minute=0),  # Daily at 5:00 AM
        "options": {"queue": "low_priority"},
    },

    # ── Payments ────────────────────────────────────────────────────────────
    "cleanup-old-webhook-logs": {
        "task": "payments.tasks.cleanup_old_webhook_logs",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),  # Weekly, Sunday 2 AM
        "options": {"queue": "low_priority"},
    },
}

# ─── Structured Logging ────────────────────────────────────────────────────────
# Comprehensive logging configuration with separate handlers for different
# concerns (django core, payments, security, celery, errors).
# All file handlers use RotatingFileHandler (10 MB max, 5 backups).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} — {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file_django": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "django.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "file_requests": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "requests.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "file_payments": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "payments.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "file_security": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "security.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "file_celery": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "celery.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
        "file_errors": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "errors.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file_requests", "file_errors"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "file_security", "file_errors"],
            "level": "WARNING",
            "propagate": False,
        },
        "payments": {
            "handlers": ["console", "file_payments", "file_errors"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console", "file_celery"],
            "level": "INFO",
            "propagate": False,
        },
        "orders": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        "inventory": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        "security": {
            "handlers": ["console", "file_security", "file_errors"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "file_errors"],
        "level": "WARNING",
    },
}
