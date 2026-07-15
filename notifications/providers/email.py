# notifications/providers/email.py
"""
notifications/providers/email.py
──────────────────────────────────────────────────────────────────────────────
Fully implemented, production-ready email channel provider utilizing Django's
`EmailMultiAlternatives` to deliver both rich HTML and plain-text alternatives.
──────────────────────────────────────────────────────────────────────────────
"""

import uuid
from typing import Any, Dict, Optional
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from notifications.providers.base import BaseNotificationProvider


class EmailProvider(BaseNotificationProvider):
    """
    SMTP / Backend email communication provider.
    Constructs multi-part MIME messages with plain-text fallback and responsive HTML.
    """
    provider_code: str = "email_smtp"

    def validate(self, recipient: str) -> bool:
        """
        Validate RFC 5322 email address string.
        """
        if not recipient or not isinstance(recipient, str):
            return False
        try:
            validate_email(recipient.strip())
            return True
        except ValidationError:
            return False

    def format_payload(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EmailMultiAlternatives:
        """
        Construct and return `EmailMultiAlternatives` ready for dispatch.
        """
        from_email = self.config.get("from_email") or getattr(
            settings, "DEFAULT_FROM_EMAIL", "House of Bore <noreply@houseofbore.com>"
        )
        msg = EmailMultiAlternatives(
            subject=subject.strip() if subject else "House of Bore Notification",
            body=content or "",
            from_email=from_email,
            to=[recipient.strip()],
        )
        if html_content:
            msg.attach_alternative(html_content, "text/html")
        return msg

    def send(
        self,
        recipient: str,
        subject: str,
        content: str,
        html_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send multipart transactional email.
        """
        if not self.validate(recipient):
            return {
                "success": False,
                "provider_code": self.provider_code,
                "message_id": None,
                "error": f"Invalid email address recipient: {recipient}",
                "raw_response": None,
            }

        try:
            msg = self.format_payload(recipient, subject, content, html_content=html_content, metadata=metadata)
            sent_count = msg.send(fail_silently=True)
            message_id = f"email_{uuid.uuid4().hex}" if sent_count > 0 else None
            return {
                "success": sent_count > 0,
                "provider_code": self.provider_code,
                "message_id": message_id,
                "error": None if sent_count > 0 else "SMTP email dispatch failed: backend returned 0 messages sent (check SMTP settings/port availability).",
                "raw_response": {"sent_count": sent_count, "message_id": message_id},
            }
        except (Exception, BaseException) as str_e:
            return {
                "success": False,
                "provider_code": self.provider_code,
                "message_id": None,
                "error": str(str_e),
                "raw_response": None,
            }
