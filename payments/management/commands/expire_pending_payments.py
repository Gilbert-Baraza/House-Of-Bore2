# payments/management/commands/expire_pending_payments.py
"""
payments/management/commands/expire_pending_payments.py
──────────────────────────────────────────────────────────────────────────────
Management command to expire old `Payment` attempts that remained in `PENDING`
or `PROCESSING` state past a configured threshold (`--hours`, default 24).
Can be run periodically via cron or Celery beat (`python manage.py expire_pending_payments`).
──────────────────────────────────────────────────────────────────────────────
"""

import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from payments.models import Payment, PaymentStatus


class Command(BaseCommand):
    help = "Expire stale payment records that have remained in PENDING or PROCESSING status beyond a threshold."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Number of hours before a pending/processing payment is considered expired (default: 24).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate expiration without actually modifying database records.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - datetime.timedelta(hours=hours)

        stale_payments = Payment.objects.filter(
            status__in=[PaymentStatus.PENDING, PaymentStatus.PROCESSING],
            created_at__lte=cutoff,
        )

        count = stale_payments.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No pending or processing payments older than {hours} hour(s) found."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Would expire {count} payment(s) older than {hours} hour(s):"))
            for p in stale_payments[:10]:
                self.stdout.write(f" - {p.payment_reference} (Order {p.order.order_number}, Status: {p.status}, Created: {p.created_at})")
            if count > 10:
                self.stdout.write(f" ... and {count - 10} more.")
            return

        expired_count = 0
        with transaction.atomic():
            for p in stale_payments.select_for_update():
                p.status = PaymentStatus.EXPIRED
                p.completed_at = timezone.now()
                p.save(update_fields=["status", "completed_at", "updated_at"])
                expired_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Successfully transitioned {expired_count} stale payment attempt(s) to EXPIRED status.")
        )
