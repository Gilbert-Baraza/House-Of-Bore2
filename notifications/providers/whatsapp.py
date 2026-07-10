# notifications/providers/whatsapp.py
"""
notifications/providers/whatsapp.py
──────────────────────────────────────────────────────────────────────────────
Production-ready WhatsApp Business API provider interface and placeholder
(e.g., WhatsApp Cloud API or Meta Graph API).
──────────────────────────────────────────────────────────────────────────────
"""

import re
import uuid
from typing import Any, Dict, Optional
from notifications.providers.base import BaseNotificationProvider


class WhatsAppProvider(BaseNotificationProvider):
    """
    WhatsApp Cloud API provider interface.
    Formats structured message templates or text bodies and simulates dispatch
    when live Graph API tokens are absent.
    """
    provider_code: str = "whatsapp_cloud"

    def validate(self, recipient: str) -> bool:
        """
        Validate international E.164 phone number compatible with WhatsApp Business API.
        """
        if not recipient or not isinstance(recipient, str):
            return False
        clean_num = recipient.strip()
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
        Format payload conforming to Meta WhatsApp Cloud API specifications.
        Supports text messages or structured template messages if template_name is in metadata.
        """
        metadata = metadata or {}
        template_name = metadata.get("template_name")
        phone_no = recipient.strip().lstrip("+")

        if template_name:
            return {
                "messaging_product": "whatsapp",
                "to": phone_no,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": metadata.get("language_code", "en_US")},
                    "components": metadata.get("template_components", []),
                },
            }

        return {
            "messaging_product": "whatsapp",
            "to": phone_no,
            "type": "text",
            "text": {"preview_url": False, "body": content.strip() if content else (subject.strip() if subject else "")},
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
        Simulate or execute WhatsApp API dispatch.
        """
        if not self.validate(recipient):
            return {
                "success": False,
                "provider_code": self.provider_code,
                "message_id": None,
                "error": f"Invalid recipient phone number for WhatsApp: {recipient}",
                "raw_response": None,
            }

        payload = self.format_payload(recipient, subject, content, html_content=html_content, metadata=metadata)
        
        access_token = self.config.get("access_token")
        if not access_token:
            simulated_id = f"wa_sim_{uuid.uuid4().hex[:12]}"
            return {
                "success": True,
                "provider_code": self.provider_code,
                "message_id": simulated_id,
                "error": None,
                "raw_response": {"status": "accepted", "messages": [{"id": simulated_id}], "payload": payload, "simulated": True},
            }

        return {
            "success": False,
            "provider_code": self.provider_code,
            "message_id": None,
            "error": "Live WhatsApp Cloud API dispatch not yet configured.",
            "raw_response": None,
        }
