"""
config/settings/__init__.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Turns the settings/ directory into a Python package, allowing Django to
    resolve 'config.settings' as a valid import path.

    It reads the DJANGO_ENV environment variable and delegates to the correct
    settings module. This means manage.py, wsgi.py, and asgi.py all continue
    pointing to 'config.settings' without any modification — the package
    itself handles the routing.

    Additionally, it validates that critical environment variables are present
    at startup time and provides clear, actionable error messages when they
    are missing — preventing cryptic runtime failures later.

Environment switching:
    DJANGO_ENV=development  →  loads config.settings.development  (default)
    DJANGO_ENV=production   →  loads config.settings.production

Usage examples:
    # Run dev server (default)
    python manage.py runserver

    # Run with production settings
    set DJANGO_ENV=production && python manage.py check --deploy

    # Or inline (Linux/macOS)
    DJANGO_ENV=production python manage.py check --deploy
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys

# ─── Startup Environment Validation ────────────────────────────────────────────
# Validate critical environment variables BEFORE importing settings modules.
# This catches misconfiguration immediately with clear, actionable errors.


def _validate_environment():
    """
    Check that required environment variables are set.
    Raises ImproperlyConfigured with a helpful message if any are missing.
    """
    # SECRET_KEY is always required — without it Django cannot sign cookies,
    # CSRF tokens, or password reset links.
    if not os.environ.get("SECRET_KEY") and not os.path.exists(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    ):
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════════╗\n"
            "║  MISSING CONFIGURATION: SECRET_KEY                             ║\n"
            "╠══════════════════════════════════════════════════════════════════╣\n"
            "║                                                                ║\n"
            "║  Django requires SECRET_KEY to be set.                         ║\n"
            "║                                                                ║\n"
            "║  Quick fix:                                                    ║\n"
            "║  1. Copy .env.example to .env                                  ║\n"
            "║  2. Generate a key:                                            ║\n"
            "║     python -c \"from django.core.management.utils import        ║\n"
            "║       get_random_secret_key; print(get_random_secret_key())\"   ║\n"
            "║  3. Paste the key into SECRET_KEY= in your .env file           ║\n"
            "║                                                                ║\n"
            "╚══════════════════════════════════════════════════════════════════╝\n",
            file=sys.stderr,
        )

    environment = os.environ.get("DJANGO_ENV", "development").lower().strip()

    if environment == "production":
        # In production, these variables are mandatory — fail fast with clear messages.
        missing = []
        celery_enabled = os.environ.get("CELERY_ENABLED", "False").lower().strip() in ("true", "1", "yes")
        required_vars = [
            ("SECRET_KEY", "Django cryptographic signing key"),
            ("ALLOWED_HOSTS", "Comma-separated list of valid hostnames"),
            ("DB_NAME", "PostgreSQL database name"),
            ("DB_USER", "PostgreSQL username"),
            ("DB_PASSWORD", "PostgreSQL password"),
        ]
        if celery_enabled:
            required_vars.append(("REDIS_URL", "Redis connection URL (broker, cache, sessions)"))
        for var_name, description in required_vars:
            if not os.environ.get(var_name):
                missing.append(f"  • {var_name:24s} — {description}")

        if missing:
            print(
                "\n"
                "╔══════════════════════════════════════════════════════════════════╗\n"
                "║  PRODUCTION STARTUP FAILED: Missing Environment Variables       ║\n"
                "╠══════════════════════════════════════════════════════════════════╣\n"
                "║                                                                ║\n"
                + "\n".join(f"║  {line:62s}║" for line in missing)
                + "\n"
                "║                                                                ║\n"
                "║  Set these in your .env file or system environment before       ║\n"
                "║  starting with DJANGO_ENV=production.                           ║\n"
                "║                                                                ║\n"
                "║  See .env.example for a complete template.                      ║\n"
                "╚══════════════════════════════════════════════════════════════════╝\n",
                file=sys.stderr,
            )
            sys.exit(1)


# Only validate when not running in test discovery or migrations
_command = sys.argv[1] if len(sys.argv) > 1 else ""
if _command not in ("test", "makemigrations", "showmigrations"):
    _validate_environment()


# ─── Environment Routing ───────────────────────────────────────────────────────
# Read the target environment. Defaults to 'development' so that the project
# works out of the box without any environment variable configuration.
_environment = os.environ.get("DJANGO_ENV", "development").lower().strip()

if _environment == "production":
    from .production import *  # noqa: F401, F403
elif _environment == "development":
    from .development import *  # noqa: F401, F403
else:
    raise ValueError(
        f"Unknown DJANGO_ENV value: '{_environment}'. "
        f"Expected 'development' or 'production'."
    )
