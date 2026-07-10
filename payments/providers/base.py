# payments/providers/base.py
"""
payments/providers/base.py
──────────────────────────────────────────────────────────────────────────────
Common abstract base interface (`BasePaymentProvider`) that all gateway adapters
must implement to ensure a consistent, gateway-agnostic payment architecture.
──────────────────────────────────────────────────────────────────────────────
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Optional
from django.http import HttpRequest
from payments.models import Payment


class BasePaymentProvider(ABC):
    """
    Abstract base class defining the required interface for all payment gateway adapters.
    Ensures that views, services, and checkout flows never depend directly on specific
    gateway APIs.
    """

    def __init__(self, **config: Any) -> None:
        """
        Initialize provider with configuration parameters (API keys, secrets, environment).
        """
        self.config = config

    @abstractmethod
    def initiate_payment(
        self,
        payment: Payment,
        request: Optional[HttpRequest] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Initiate the payment process with the external gateway API.

        Args:
            payment: The `Payment` model instance to initiate.
            request: Optional Django HTTP request object (for URLs, callbacks, session info).
            **kwargs: Extra gateway-specific parameters (e.g., phone_number for M-Pesa).

        Returns:
            Dictionary containing result info:
            {
                "success": bool,
                "redirect_url": Optional[str],
                "provider_data": Dict[str, Any],
                "error": Optional[str],
            }
        """
        pass

    @abstractmethod
    def verify_payment(
        self,
        payment: Payment,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Perform server-side verification of a payment against the gateway API.
        Never trust client-submitted transaction statuses.

        Args:
            payment: The `Payment` model instance to verify.
            **kwargs: Extra parameters (e.g., token, PayerID, receipt query parameters).

        Returns:
            Dictionary containing verification status:
            {
                "success": bool,
                "status": str,  # e.g., "completed", "failed", "pending"
                "transaction_id": Optional[str],
                "amount": Optional[Decimal],
                "currency": Optional[str],
                "provider_response": Dict[str, Any],
                "error": Optional[str],
            }
        """
        pass

    @abstractmethod
    def handle_webhook(
        self,
        request: HttpRequest
    ) -> Dict[str, Any]:
        """
        Process and verify an incoming gateway webhook payload and cryptographic signature.

        Args:
            request: Django HTTP request object containing headers and raw payload.

        Returns:
            Dictionary containing parsed webhook event data:
            {
                "success": bool,
                "event_id": Optional[str],
                "event_type": Optional[str],
                "payment_reference": Optional[str],
                "transaction_id": Optional[str],
                "status": Optional[str],  # e.g., "completed", "failed"
                "amount": Optional[Decimal],
                "raw_payload": Dict[str, Any],
                "error": Optional[str],
            }
        """
        pass

    def refund(
        self,
        payment: Payment,
        amount: Optional[Decimal] = None,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Placeholder method for refund processing.
        As specified in Phase 4.5 requirements, refunds belong to future milestones.

        Returns standard placeholder structure indicating refund capability is not yet active.
        """
        return {
            "success": False,
            "status": "not_implemented",
            "error": "Refund processing is reserved for future milestones.",
        }
