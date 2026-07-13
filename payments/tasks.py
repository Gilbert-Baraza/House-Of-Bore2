# payments/tasks.py
"""
payments/tasks.py
──────────────────────────────────────────────────────────────────────────────
Background Celery tasks for payment infrastructure maintenance:
1. cleanup_old_webhook_logs — purge webhook log entries older than 90 days
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("payments")


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_old_webhook_logs(self):
    """
    Periodic task that deletes PaymentWebhookLog entries older than 90 days.
    Webhook logs are retained for debugging and reconciliation, but entries
    beyond 90 days add no operational value and increase database size.

    Runs weekly (Sunday 2:00 AM) via Celery Beat.
    """
    from payments.models import PaymentWebhookLog

    cutoff = timezone.now() - timedelta(days=90)

    old_logs = PaymentWebhookLog.objects.filter(created_at__lt=cutoff)
    count = old_logs.count()

    if count > 0:
        old_logs.delete()
        logger.info(
            "Purged %d webhook log entries older than %s.",
            count,
            cutoff.isoformat(),
        )

    return {"purged_count": count, "cutoff": cutoff.isoformat()}
