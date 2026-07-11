# crm/tasks.py
"""
crm/tasks.py
──────────────────────────────────────────────────────────────────────────────
Background tasks and asynchronous workers for CRM maintenance, dynamic segment
refreshing, and data export bundling.
──────────────────────────────────────────────────────────────────────────────
"""

import logging

logger = logging.getLogger("crm")


def refresh_customer_segments_task() -> dict:
    """
    Background job to precompute and cache expensive customer segmentation cohorts
    for instant administrative lookup.
    """
    from .selectors import customer_segments
    segments = customer_segments(use_cache=False)
    logger.info("Successfully refreshed %d customer segmentation cohorts.", len(segments))
    return {k: v.count() if hasattr(v, "count") else len(v) for k, v in segments.items()}
