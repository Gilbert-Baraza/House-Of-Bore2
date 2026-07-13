# config/celery.py
"""
config/celery.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Celery application initialization and configuration for House of Bore.
    Discovers asynchronous background tasks across all registered Django apps.

    This module is imported by config/__init__.py to ensure the Celery app is
    always available when Django starts, enabling @shared_task decorators to
    register tasks correctly.

IMPORTANT:
    DJANGO_SETTINGS_MODULE points to 'config.settings' (the package), which
    routes to the correct environment via config/settings/__init__.py.
──────────────────────────────────────────────────────────────────────────────
"""

import os
import logging
from celery import Celery
from celery.signals import task_failure, task_retry

logger = logging.getLogger("celery")

# Set default Django settings module for 'celery' command-line program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("house_of_bore")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# Namespace 'CELERY' means all celery-related configuration keys
# should have a `CELERY_` prefix in Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Automatically discover tasks.py files in all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Diagnostic task for verifying Celery worker connectivity."""
    print(f"Request: {self.request!r}")


# ─── Error Handling Signals ────────────────────────────────────────────────────
# These signal handlers provide centralized logging for task failures and retries
# across all workers. In production, Sentry will capture these automatically.

@task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, traceback=None, **kwargs):
    """Log task failures to the celery logger for monitoring and alerting."""
    logger.error(
        "Task %s[%s] FAILED: %s",
        sender.name if sender else "unknown",
        task_id,
        str(exception),
        exc_info=(type(exception), exception, traceback) if exception else None,
    )


@task_retry.connect
def log_task_retry(sender=None, request=None, reason=None, **kwargs):
    """Log task retries for visibility into transient failures."""
    logger.warning(
        "Task %s[%s] RETRYING: %s",
        sender.name if sender else "unknown",
        request.id if request else "unknown",
        str(reason),
    )
