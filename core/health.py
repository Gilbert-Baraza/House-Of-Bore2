# core/health.py
"""
core/health.py
──────────────────────────────────────────────────────────────────────────────
WHY THIS FILE EXISTS:
    Health check endpoints for load balancers, container orchestrators (Kubernetes/ECS),
    and uptime monitoring tools (Prometheus, BetterStack, AWS Route 53).

ENDPOINTS:
    • /health/        — Liveness probe (200 OK if Django WSGI/ASGI process is alive)
    • /health/ready/  — Readiness probe (200 OK if DB & Redis dependencies are operational)
    • /health/live/   — Lightweight heartbeat check

SECURITY NOTE:
    These endpoints do not require authentication or rate limiting so that internal
    orchestrators and reverse proxies can poll them frequently without overhead or blockage.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
import time
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("django.request")


def health_check(request):
    """
    Basic liveness probe.
    Returns 200 OK if Django is running and able to handle HTTP requests.
    """
    return JsonResponse(
        {
            "status": "ok",
            "service": "house-of-bore",
            "timestamp": int(time.time()),
        },
        status=200,
    )


def readiness_check(request):
    """
    Readiness probe for zero-downtime deployments.
    Verifies connectivity to critical external dependencies:
      1. PostgreSQL / SQLite database
      2. Redis cache engine
    Returns 200 OK if all checks pass, 503 Service Unavailable if any check fails.
    """
    status_data = {
        "status": "ready",
        "service": "house-of-bore",
        "timestamp": int(time.time()),
        "checks": {
            "database": "unknown",
            "cache": "unknown",
        },
    }
    http_status = 200

    # 1. Database Check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                status_data["checks"]["database"] = "ok"
            else:
                raise ValueError("Database returned unexpected result for SELECT 1;")
    except Exception as exc:
        logger.error(f"Readiness check failed — Database error: {exc}")
        status_data["checks"]["database"] = f"error: {str(exc)}"
        status_data["status"] = "unready"
        http_status = 503

    # 2. Redis / Cache Check
    try:
        test_key = "health_probe_readiness"
        test_val = str(time.time())
        cache.set(test_key, test_val, timeout=10)
        retrieved_val = cache.get(test_key)
        if retrieved_val == test_val:
            status_data["checks"]["cache"] = "ok"
        else:
            raise ValueError("Cache read value did not match written value.")
    except Exception as exc:
        logger.error(f"Readiness check failed — Cache error: {exc}")
        status_data["checks"]["cache"] = f"error: {str(exc)}"
        status_data["status"] = "unready"
        http_status = 503

    return JsonResponse(status_data, status=http_status)


def liveness_check(request):
    """
    Lightweight heartbeat check for container orchestration monitoring.
    Never checks external resources to avoid cascade failures when DB or Redis lag.
    """
    return JsonResponse({"status": "live"}, status=200)
