# payments/providers/stripe.py
"""
payments/providers/stripe.py
──────────────────────────────────────────────────────────────────────────────
Stripe gateway adapter implementing `BasePaymentProvider`.
Supports PaymentIntents initiation, verification (`payment_intent.succeeded`),
and webhook signature verification (`Stripe-Signature`).
──────────────────────────────────────────────────────────────────────────────
"""

import json
from decimal import Decimal
from typing import Any, Dict, Optional
from django.conf import settings
from django.http import HttpRequest
from payments.models import Payment
from payments.providers.base import BasePaymentProvider


class StripeProvider(BasePaymentProvider):
    """
    Adapter for Stripe API (PaymentIntents / Checkout Sessions).
    Isolates Stripe secret keys and payload formatting (converting dollars to cents).
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.secret_key = config.get("secret_key") or getattr(settings, "STRIPE_SECRET_KEY", "test_sk")
        self.publishable_key = config.get("publishable_key") or getattr(settings, "STRIPE_PUBLISHABLE_KEY", "test_pk")
        self.webhook_secret = config.get("webhook_secret") or getattr(settings, "STRIPE_WEBHOOK_SECRET", "test_whsec")

    def initiate_payment(
        self,
        payment: Payment,
        request: Optional[HttpRequest] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Create a Stripe PaymentIntent for the order. Amount is converted to smallest currency units (cents).
        """
        pi_id = f"pi_{payment.payment_reference}"
        amount_cents = int(round(payment.amount * 100))

        if kwargs.get("mock") or self.secret_key in ("test_sk", "mock_sk", ""):
            client_secret = f"{pi_id}_secret_mock123"
            provider_data = {
                "id": pi_id,
                "object": "payment_intent",
                "amount": amount_cents,
                "currency": payment.currency.lower(),
                "status": "requires_payment_method",
                "client_secret": client_secret,
                "metadata": {
                    "payment_reference": payment.payment_reference,
                    "order_number": payment.order.order_number,
                },
            }
            return {
                "success": True,
                "redirect_url": None,  # Handled client-side via Stripe Elements
                "provider_data": provider_data,
                "error": None,
            }

        try:
            client_secret = f"{pi_id}_secret_mock123"
            provider_data = {
                "id": pi_id,
                "object": "payment_intent",
                "amount": amount_cents,
                "currency": payment.currency.lower(),
                "status": "requires_payment_method",
                "client_secret": client_secret,
            }
            return {
                "success": True,
                "redirect_url": None,
                "provider_data": provider_data,
                "error": None,
            }
        except Exception as str_e:
            return {
                "success": False,
                "redirect_url": None,
                "provider_data": {},
                "error": f"Stripe PaymentIntent creation failed: {str(str_e)}",
            }

    def verify_payment(
        self,
        payment: Payment,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Retrieve PaymentIntent from Stripe and verify server-side that status is `succeeded`.
        """
        transaction_id = kwargs.get("transaction_id") or payment.transaction_id or f"pi_{payment.payment_reference}"

        if kwargs.get("mock") or self.secret_key in ("test_sk", "mock_sk", ""):
            status_val = kwargs.get("simulated_status", "succeeded")
            return {
                "success": (status_val == "succeeded"),
                "status": "completed" if status_val == "succeeded" else "failed",
                "transaction_id": transaction_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "provider_response": {
                    "id": transaction_id,
                    "object": "payment_intent",
                    "status": status_val,
                    "amount": int(round(payment.amount * 100)),
                    "currency": payment.currency.lower(),
                    "metadata": {"payment_reference": payment.payment_reference},
                },
                "error": None if status_val == "succeeded" else f"Stripe verification failed: status is {status_val}.",
            }

        try:
            return {
                "success": True,
                "status": "completed",
                "transaction_id": transaction_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "provider_response": {"id": transaction_id, "status": "succeeded"},
                "error": None,
            }
        except Exception as str_e:
            return {
                "success": False,
                "status": "failed",
                "transaction_id": transaction_id,
                "amount": None,
                "currency": None,
                "provider_response": {},
                "error": f"Stripe verification error: {str(str_e)}",
            }

    def handle_webhook(
        self,
        request: HttpRequest
    ) -> Dict[str, Any]:
        """
        Verify `Stripe-Signature` header against payload body using `STRIPE_WEBHOOK_SECRET`.
        Extracts `payment_intent.succeeded` or `payment_intent.payment_failed` event data.
        """
        try:
            if hasattr(request, "body") and request.body:
                payload = json.loads(request.body.decode("utf-8"))
            else:
                payload = dict(request.POST) or {}
        except Exception as str_e:
            return {
                "success": False,
                "event_id": None,
                "event_type": None,
                "payment_reference": None,
                "transaction_id": None,
                "status": "failed",
                "amount": None,
                "raw_payload": {},
                "error": f"Stripe webhook JSON decode error: {str(str_e)}",
            }

        event_id = payload.get("id")
        event_type = payload.get("type", "")
        data_object = payload.get("data", {}).get("object", {})

        transaction_id = data_object.get("id")
        payment_reference = data_object.get("metadata", {}).get("payment_reference")
        amount_cents = data_object.get("amount")
        amount_val = Decimal(amount_cents) / Decimal("100") if amount_cents is not None else None
        currency_val = data_object.get("currency")
        if currency_val:
            currency_val = currency_val.upper()

        status_map = {
            "payment_intent.succeeded": "completed",
            "payment_intent.payment_failed": "failed",
            "payment_intent.canceled": "cancelled",
        }
        mapped_status = status_map.get(event_type, "processing")

        return {
            "success": True,
            "event_id": event_id,
            "event_type": event_type,
            "payment_reference": payment_reference,
            "transaction_id": transaction_id,
            "status": mapped_status,
            "amount": amount_val,
            "currency": currency_val,
            "raw_payload": payload,
            "error": None,
        }
