# core/tasks.py
"""
core/tasks.py
──────────────────────────────────────────────────────────────────────────────
Background Celery tasks for system maintenance and housekeeping:
1. cleanup_expired_sessions — purge expired Django sessions
2. cleanup_temp_files — remove orphaned temporary upload files
3. database_maintenance — run PostgreSQL ANALYZE for query optimizer
──────────────────────────────────────────────────────────────────────────────
"""

import logging
import os
import time

from celery import shared_task

logger = logging.getLogger("django")


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def cleanup_expired_sessions(self):
    """
    Periodic task that calls Django's built-in clearsessions management command.
    Removes expired sessions from the session store.

    For cache-backed sessions (our production setup), this is a no-op since
    Redis handles TTL expiry automatically. However, this task ensures cleanup
    if the session backend is ever switched to database-backed sessions.

    Runs daily at 4:00 AM via Celery Beat.
    """
    from django.core.management import call_command

    call_command("clearsessions")
    logger.info("Expired sessions cleanup completed.")

    return {"status": "completed"}


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def cleanup_temp_files(self):
    """
    Periodic task that removes orphaned temporary files from Django's
    FILE_UPLOAD_TEMP_DIR (or the system temp directory). Files older than
    24 hours are considered orphaned and safe to delete.

    Runs daily at 5:00 AM via Celery Beat.
    """
    import tempfile
    from datetime import timedelta
    from django.conf import settings
    from django.utils import timezone

    temp_dir = getattr(settings, "FILE_UPLOAD_TEMP_DIR", None) or tempfile.gettempdir()
    cutoff = time.time() - timedelta(hours=24).total_seconds()
    cleaned = 0

    try:
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            if os.path.isfile(filepath) and filename.startswith("tmp"):
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    cleaned += 1
    except OSError as e:
        logger.warning("Temp file cleanup encountered an error: %s", str(e))

    logger.info("Cleaned up %d orphaned temporary files.", cleaned)
    return {"cleaned_count": cleaned}


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def database_maintenance(self):
    """
    Run PostgreSQL ANALYZE to update query planner statistics.
    This helps the query optimizer make better decisions about index usage
    and join strategies after bulk data changes.

    Only runs when using PostgreSQL (skips for SQLite in development).
    Should be scheduled weekly or after large data imports.
    """
    from django.conf import settings
    from django.db import connection

    db_engine = settings.DATABASES["default"]["ENGINE"]

    if "postgresql" not in db_engine:
        logger.info("Skipping database maintenance (not PostgreSQL).")
        return {"status": "skipped", "reason": "not_postgresql"}

    try:
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE;")
        logger.info("PostgreSQL ANALYZE completed successfully.")
        return {"status": "completed"}
    except Exception as e:
        logger.error("Database maintenance failed: %s", str(e))
        raise
