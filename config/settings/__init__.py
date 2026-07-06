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
