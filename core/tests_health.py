# core/tests_health.py
"""
core/tests_health.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Automated unit tests for health check endpoints (/health/, /health/ready/,
    /health/live/). Verifies liveness, readiness (DB and cache verification),
    and failure handling when dependencies are unready.
──────────────────────────────────────────────────────────────────────────────
"""

import json
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    """Test suite verifying container orchestration health probes."""

    def setUp(self):
        self.client = Client()

    def test_health_check_endpoint(self):
        """Verify /health/ liveness probe returns 200 OK and valid JSON payload."""
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "house-of-bore")
        self.assertIn("timestamp", data)

    def test_liveness_check_endpoint(self):
        """Verify /health/live/ returns lightweight 200 OK heartbeat."""
        response = self.client.get(reverse("liveness_check"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "live")

    def test_readiness_check_endpoint_success(self):
        """Verify /health/ready/ returns 200 OK when database and cache pass."""
        response = self.client.get(reverse("readiness_check"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["checks"]["database"], "ok")
        self.assertEqual(data["checks"]["cache"], "ok")

    @patch("core.health.connection.cursor")
    def test_readiness_check_endpoint_db_failure(self, mock_cursor):
        """Verify /health/ready/ returns 503 Service Unavailable when database query fails."""
        mock_cursor.side_effect = Exception("Database connection pool exhausted")
        response = self.client.get(reverse("readiness_check"))
        self.assertEqual(response.status_code, 503)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "unready")
        self.assertIn("error", data["checks"]["database"])

    @patch("core.health.cache.set")
    def test_readiness_check_endpoint_cache_failure(self, mock_set):
        """Verify /health/ready/ returns 503 Service Unavailable when cache write fails."""
        mock_set.side_effect = Exception("Redis connection refused")
        response = self.client.get(reverse("readiness_check"))
        self.assertEqual(response.status_code, 503)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "unready")
        self.assertIn("error", data["checks"]["cache"])
