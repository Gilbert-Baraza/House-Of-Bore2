"""
accounts/signals.py
──────────────────────────────────────────────────────────────────────────────
Signal receivers for automatic UserProfile management.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender: Any, instance: User, created: bool, **kwargs: Any) -> None:
    """
    Automatically create a UserProfile whenever a new User is registered.
    For existing users without a profile, ensures one is created on save without firing
    redundant SELECT queries on every subsequent save.
    """
    if created:
        UserProfile.objects.create(user=instance)
        instance._profile_checked = True  # type: ignore[attr-defined]
    elif not getattr(instance, "_profile_checked", False):
        try:
            # If profile is already cached in memory or accessible via reverse relation, skip DB query
            if hasattr(instance, "profile") and instance.profile is not None:
                instance._profile_checked = True  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        UserProfile.objects.get_or_create(user=instance)
        instance._profile_checked = True  # type: ignore[attr-defined]
