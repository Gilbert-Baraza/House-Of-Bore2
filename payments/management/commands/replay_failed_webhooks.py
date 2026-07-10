# payments/management/commands/replay_failed_webhooks.py
"""
payments/management/commands/replay_failed_webhooks.py
──────────────────────────────────────────────────────────────────────────────
Management command allowing operations teams to safely replay and re-verify
previous `PaymentWebhookLog` deliveries that encountered temporary failures
(e.g., database lock timeouts, external SMTP service outages, or transient bugs).
Usage: `python manage.py replay_failed_webhooks --status failed --gateway stripe`
──────────────────────────────────────────────────────────────────────────────
"""

import json
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone
from payments.models import GatewayChoices, PaymentWebhookLog
from payments.services import process_webhook_payload


class Command(BaseCommand):
    help = "Replay and re-process failed or ignored webhook logs through the payment service layer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gateway",
            type=str,
            default="",
            choices=[g.value for g in GatewayChoices] + [""],
            help="Filter logs by specific gateway provider code (e.g., paypal, mpesa, stripe).",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="failed",
            choices=["failed", "ignored", "duplicate", "all"],
            help="Filter logs by current status (default: failed).",
        )
        parser.add_argument(
            "--event-id",
            type=str,
            default="",
            help="Replay a specific webhook delivery by its event_id.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate webhook replay without modifying database state.",
        )

    def handle(self, *args, **options):
        gateway = options["gateway"]
        status_filter = options["status"]
        event_id = options["event_id"]
        dry_run = options["dry_run"]

        queryset = PaymentWebhookLog.objects.all()
        if gateway:
            queryset = queryset.filter(gateway=gateway)
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        elif status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        count = queryset.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No matching webhook log entries found for replay."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY RUN] Would attempt to replay {count} webhook log(s):"))
            for log in queryset[:10]:
                self.stdout.write(f" - #{log.pk} [{log.gateway} - {log.event_type} - {log.event_id}] ({log.status})")
            if count > 10:
                self.stdout.write(f" ... and {count - 10} more.")
            return

        factory = RequestFactory()
        replayed_count = 0
        failed_count = 0

        self.stdout.write(f"Starting replay of {count} webhook entry/entries...")

        for log in queryset:
            try:
                # Construct HTTP request from stored audit payload and headers
                req = factory.post(
                    f"/payments/webhooks/{log.gateway}/",
                    data=json.dumps(log.payload),
                    content_type="application/json",
                )
                if isinstance(log.headers, dict):
                    for k, v in log.headers.items():
                        # Set header in META dictionary format
                        meta_key = f"HTTP_{k.upper().replace('-', '_')}" if not k.lower().startswith("content-") else k.upper().replace('-', '_')
                        req.META[meta_key] = v

                # Temporarily rename event_id or mark replay flag in payload so deduplication allows reprocessing if explicitly requested
                if log.payload and isinstance(log.payload, dict):
                    req._replay_from_log_id = log.pk

                with transaction.atomic():
                    _, result = process_webhook_payload(log.gateway, req)

                if result.get("success") and result.get("processed"):
                    log.status = "processed"
                    log.error_message = f"Replayed successfully on {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    log.save(update_fields=["status", "error_message"])
                    replayed_count += 1
                    self.stdout.write(self.style.SUCCESS(f" [OK] Log #{log.pk} replayed successfully."))
                else:
                    failed_count += 1
                    err = result.get("error") or result.get("message", "Unknown error")
                    self.stdout.write(self.style.ERROR(f" [FAIL] Log #{log.pk} failed during replay: {err}"))

            except Exception as str_e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f" [ERROR] Exception while replaying Log #{log.pk}: {str(str_e)}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Replay complete: {replayed_count} replayed successfully, {failed_count} still failed/unprocessed."
            )
        )
