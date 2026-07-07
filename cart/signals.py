# cart/signals.py
"""
cart/signals.py
──────────────────────────────────────────────────────────────────────────────
Signal receivers for the shopping cart system.
Automatically merges guest session carts into persistent user carts upon login.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest
from cart.services import merge_carts


@receiver(user_logged_in)
def on_user_logged_in(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    """
    Signal handler triggered immediately when a user authenticates.
    Delegates cart merging to the service layer.
    """
    if request:
        try:
            merge_carts(request, user)
        except Exception:
            # Prevent authentication failures if an unexpected cart merge error occurs
            pass
