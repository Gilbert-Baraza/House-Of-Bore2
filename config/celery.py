# config/celery.py
"""
config/celery.py
──────────────────────────────────────────────────────────────────────────────
Celery application initialization and configuration for House of Bore.
Discovers asynchronous background tasks across all registered Django apps (`LOCAL_APPS`).
──────────────────────────────────────────────────────────────────────────────
"""

import os
from celery import Celery

# Set default Django settings module for 'celery' command-line program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

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
    print(f"Request: {self.request!r}")
