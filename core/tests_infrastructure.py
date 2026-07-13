# core/tests_infrastructure.py
"""
core/tests_infrastructure.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Automated verification of production infrastructure configuration:
    1. Celery task discovery and task routing tables
    2. Cache backend connectivity and key expiration
    3. Security setting assertions
    4. Structured logging handler definitions
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase


class InfrastructureConfigurationTests(TestCase):
    """Test suite asserting configuration integrity across core infrastructure layers."""

    def test_celery_task_registration_and_routing(self):
        """Verify Celery task autodiscovery and queue routing settings."""
        from config.celery import app as celery_app

        # Check that task routing is defined
        routes = getattr(settings, "CELERY_TASK_ROUTES", {})
        self.assertIn("payments.tasks.*", routes)
        self.assertEqual(routes["payments.tasks.*"]["queue"], "high_priority")
        self.assertIn("orders.tasks.*", routes)
        self.assertEqual(routes["orders.tasks.*"]["queue"], "default")

        # Check Beat periodic schedule definition
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
        self.assertIn("expire-pending-payments", schedule)
        self.assertIn("clear-abandoned-carts", schedule)
        self.assertIn("generate-inventory-alerts", schedule)

    def test_cache_backend_functionality(self):
        """Verify Django cache read/write/delete behavior using the configured backend."""
        test_key = "infra_test_key_abc123"
        test_value = {"service": "house-of-bore", "status": "active"}

        cache.set(test_key, test_value, timeout=60)
        retrieved = cache.get(test_key)
        self.assertEqual(retrieved, test_value)

        cache.delete(test_key)
        self.assertIsNone(cache.get(test_key))

    def test_security_middleware_and_header_settings(self):
        """Assert core security headers and limits are present in Django settings."""
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin")
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 10 * 1024 * 1024)
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)

    def test_structured_logging_handlers_defined(self):
        """Verify structured logging configuration has separate handlers for core concerns."""
        logging_config = getattr(settings, "LOGGING", {})
        handlers = logging_config.get("handlers", {})
        self.assertIn("console", handlers)
        self.assertIn("file_django", handlers)
        self.assertIn("file_payments", handlers)
        self.assertIn("file_security", handlers)
        self.assertIn("file_celery", handlers)
        self.assertIn("file_errors", handlers)
