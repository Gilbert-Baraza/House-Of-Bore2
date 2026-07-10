# notifications/providers/base.py
"""
notifications/providers/base.py
──────────────────────────────────────────────────────────────────────────────
Abstract base class defining the standardized interface (`send`, `validate`,
and `format_payload`) for all communication channel adapters.
──────────────────────────────────────────────────────────────────────────────
"""

import abc
from typing import Any, Dict, Optional


class BaseNotificationProvider(abc.ABC):
    """
    Abstract communication channel provider.
    Every channel adapter must implement `send`, `validate`, and `format_payload`.
    """
    provider_code: str = "base"

    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs

    @abc.abstractmethod
    def validate(self, recipient: str) -> bool:
        """
        Validate whether the `recipient` string is correctly formatted for this channel
        (e.g., RFC 5322 email validation, E.164 phone number check).
        """
        pass

    @abc.abstractmethod
    def format_payload(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Format raw input arguments into provider-specific payload structure or HTTP body.
        """
        pass

    @abc.abstractmethod
    def send(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute dispatch of the notification to the target recipient.
        Returns a standardized result dictionary:
        {
            "success": bool,
            "provider_code": str,
            "message_id": Optional[str],
            "error": Optional[str],
            "raw_response": Optional[Dict[str, Any]],
        }
        """
        pass
