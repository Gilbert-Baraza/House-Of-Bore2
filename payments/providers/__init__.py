# payments/providers/__init__.py
"""
payments/providers/__init__.py
──────────────────────────────────────────────────────────────────────────────
Factory layer for payment gateway adapters.
Exports `BasePaymentProvider` and `get_provider()`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.core.exceptions import ValidationError
from payments.models import GatewayChoices
from payments.providers.base import BasePaymentProvider
from payments.providers.paypal import PayPalProvider
from payments.providers.mpesa import MpesaProvider
from payments.providers.stripe import StripeProvider


def get_provider(gateway: str, **config: Any) -> BasePaymentProvider:
    """
    Factory function instantiating the appropriate gateway adapter.
    Encapsulates provider instantiation so services and views never hardcode gateway classes.

    Args:
        gateway: Gateway code string (e.g., 'paypal', 'mpesa', 'stripe').
        **config: Optional keyword configuration parameters passed to the adapter.

    Returns:
        Instance of `BasePaymentProvider`.

    Raises:
        ValidationError if an unsupported gateway is specified.
    """
    gateway_lower = str(gateway or "").lower().strip()

    if gateway_lower == GatewayChoices.PAYPAL:
        return PayPalProvider(**config)
    elif gateway_lower == GatewayChoices.MPESA:
        return MpesaProvider(**config)
    elif gateway_lower == GatewayChoices.STRIPE:
        return StripeProvider(**config)
    elif gateway_lower == GatewayChoices.MANUAL:
        # For manual/test payments, use a lightweight simulation adapter or PayPal sandbox mock
        config_copy = dict(config)
        config_copy["mock"] = True
        return PayPalProvider(**config_copy)
    else:
        raise ValidationError(f"Unsupported payment gateway provider code: '{gateway}'")
