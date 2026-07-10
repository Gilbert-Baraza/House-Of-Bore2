# notifications/providers/__init__.py
"""
notifications/providers/__init__.py
──────────────────────────────────────────────────────────────────────────────
Factory layer instantiating appropriate channel providers based on
configuration and target channel (Email, SMS, or WhatsApp).
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict
from notifications.models import ChannelChoices
from notifications.providers.base import BaseNotificationProvider
from notifications.providers.email import EmailProvider
from notifications.providers.sms import SmsProvider
from notifications.providers.whatsapp import WhatsAppProvider


def get_provider(channel: str, **kwargs: Any) -> BaseNotificationProvider:
    """
    Factory method returning an instance of `BaseNotificationProvider` matching the requested `channel`.
    Can be easily configured with specific API keys, gateway endpoints, or custom settings via `**kwargs`.
    """
    if channel == ChannelChoices.EMAIL:
        return EmailProvider(**kwargs)
    elif channel == ChannelChoices.SMS:
        return SmsProvider(**kwargs)
    elif channel == ChannelChoices.WHATSAPP:
        return WhatsAppProvider(**kwargs)
    else:
        raise ValueError(f"Unsupported notification channel: {channel}")
