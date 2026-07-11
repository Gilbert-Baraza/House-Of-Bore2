# crm/signals.py
"""
crm/signals.py
──────────────────────────────────────────────────────────────────────────────
Signal handlers for automatic CRM cache invalidation and timeline triggers.
──────────────────────────────────────────────────────────────────────────────
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CustomerInteractionRecord, CustomerStaffNote


@receiver([post_save, post_delete], sender=CustomerStaffNote)
@receiver([post_save, post_delete], sender=CustomerInteractionRecord)
def invalidate_crm_customer_cache(sender, instance, **kwargs):
    """
    Clear cached customer profile data when notes or interactions change.
    """
    if hasattr(instance, "customer_id") and instance.customer_id:
        cache.delete(f"crm_customer_profile_{instance.customer_id}")
        cache.delete(f"crm_customer_timeline_{instance.customer_id}")
