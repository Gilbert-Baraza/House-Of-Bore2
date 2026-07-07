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
    For existing users without a profile, ensures one is created on save.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Ensure profile exists if user was created before signal was added
        UserProfile.objects.get_or_create(user=instance)
