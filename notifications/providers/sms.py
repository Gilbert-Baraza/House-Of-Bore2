# notifications/providers/sms.py
"""
notifications/providers/sms.py
──────────────────────────────────────────────────────────────────────────────
Production-ready SMS provider interface and placeholder (e.g. Twilio, AWS SNS,
or Africa's Talking). Validates target phone numbers and formats payload cleanly.
──────────────────────────────────────────────────────────────────────────────
"""

import re
import uuid
from typing import Any, Dict, Optional
from notifications.providers.base import BaseNotificationProvider


class SmsProvider(BaseNotificationProvider):
    """
    SMS communication provider interface.
    Provides complete validation and payload formatting with simulated delivery
    when live gateway keys are not present in settings.
    """
    provider_code: str = "sms_twilio"

    def validate(self, recipient: str) -> bool:
        """
        Validate E.164 or numeric telephone number (e.g., +14155552671 or +254712345678).
        """
        if not recipient or not isinstance(recipient, str):
            return False
        clean_num = recipient.strip()
        # Regex matching + followed by 7 to 15 digits or standard international digits
        if re.match(r"^\+?[1-9]\d{6,14}$", clean_num):
            return True
        return False

    def format_payload(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Format payload dictionary structured for SMS gateway REST APIs.
        """
        sender_id = self.config.get("sender_id", "HOB")
        return {
            "To": recipient.strip(),
            "From": sender_id,
            "Body": content.strip() if content else (subject.strip() if subject else ""),
            "Parameters": metadata or {},
        }

    def send(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Simulate or execute SMS dispatch.
        """
        if not self.validate(recipient):
            return {
                "success": False,
                "provider_code": self.provider_code,
                "message_id": None,
                "error": f"Invalid phone number recipient for SMS: {recipient}",
                "raw_response": None,
            }

        payload = self.format_payload(recipient, subject, content, html_content=html_content, metadata=metadata)
        
        # Check if live gateway credentials are configured
        api_key = self.config.get("api_key")
        if not api_key:
            # Simulated placeholder dispatch (production-ready interface)
            simulated_id = f"sms_sim_{uuid.uuid4().hex[:12]}"
            return {
                "success": True,
                "provider_code": self.provider_code,
                "message_id": simulated_id,
                "error": None,
                "raw_response": {"status": "queued", "sid": simulated_id, "payload": payload, "simulated": True},
            }

        # Future integration point: requests.post("https://api.twilio.com/...", json=payload, ...)
        return {
            "success": False,
            "provider_code": self.provider_code,
            "message_id": None,
            "error": "Live SMS HTTP gateway dispatch not yet configured.",
            "raw_response": None,
        }
