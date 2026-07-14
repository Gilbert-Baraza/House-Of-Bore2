# core/utils.py
"""
core/utils.py
──────────────────────────────────────────────────────────────────────────────
Shared utilities and helper abstractions across House of Bore.
──────────────────────────────────────────────────────────────────────────────
"""
import logging
from typing import Any, Callable
from django.conf import settings

logger = logging.getLogger(__name__)


def dispatch_task(task_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Safely dispatch a Celery task either asynchronously or synchronously based
    on settings.CELERY_ENABLED.

    If CELERY_ENABLED is True, invokes `task_func.delay(*args, **kwargs)`.
    If CELERY_ENABLED is False, directly calls `task_func(*args, **kwargs)`
    for synchronous execution on the current thread without requiring Redis.
    """
    if getattr(settings, "CELERY_ENABLED", False):
        try:
            return task_func.delay(*args, **kwargs)
        except Exception as exc:
            logger.exception(
                "Failed to dispatch Celery task '%s' asynchronously (Redis/broker issue?). Falling back to synchronous execution: %s",
                getattr(task_func, "__name__", str(task_func)),
                exc,
            )
            return task_func(*args, **kwargs)
    else:
        return task_func(*args, **kwargs)
