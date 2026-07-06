# accounts/services.py
"""
accounts/services.py
──────────────────────────────────────────────────────────────────────────────
Business services and transactional operations for customer accounts.

Encapsulates user registration and email sending infrastructure (welcome and
verification emails), keeping controllers/views thin and maintainable.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from typing import Any, Optional
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()
logger = logging.getLogger(__name__)


@transaction.atomic
def register_user(
    email: str,
    password: str,
    request: Optional[HttpRequest] = None,
    **extra_fields: Any
) -> Any:
    """
    Register a new customer account atomically.
    
    1. Validates and creates the User instance via Django's auth manager.
    2. Hashes the password securely using Django's PBKDF2/Argon2 hasher.
    3. Sets the account as active.
    4. Triggers welcome and verification email notifications.
    
    Args:
        email: The customer's email address (used as unique login identifier).
        password: The customer's raw password.
        request: The HTTP request object (used to build absolute verification URLs).
        **extra_fields: Optional additional attributes (e.g., first_name, last_name, phone).
        
    Returns:
        User: The newly registered and active User instance.
    """
    cleaned_email = email.strip().lower()
    
    # Filter out any fields that are not supported on the User model schema
    valid_fields = {}
    for key, value in extra_fields.items():
        if hasattr(User, key):
            valid_fields[key] = value

    user = User.objects.create_user(
        email=cleaned_email,
        password=password,
        is_active=True,
        **valid_fields
    )

    # Decouple network email I/O from the database transaction so slow SMTP servers
    # do not hold database connection locks.
    def _dispatch_emails() -> None:
        try:
            send_welcome_email(user, request=request)
        except Exception as e:
            logger.error(f"Failed to send welcome email to {cleaned_email}: {e}")

        try:
            send_verification_email(user, request=request)
        except Exception as e:
            logger.error(f"Failed to send verification email to {cleaned_email}: {e}")

    transaction.on_commit(_dispatch_emails)
    return user


def send_welcome_email(user: Any, request: Optional[HttpRequest] = None) -> bool:
    """
    Send a luxury-branded welcome email to a newly registered customer.
    
    Returns True if the email was dispatched successfully.
    """
    if not user or not getattr(user, "email", None):
        return False

    context = {
        "user": user,
        "site_name": "House of Bore",
        "login_url": _get_absolute_url(request, reverse("accounts:register_success")),
    }

    subject = "Welcome to House of Bore — Exceptional Luxury Awaits"
    text_body = render_to_string("accounts/emails/welcome_email.txt", context)
    html_body = render_to_string("accounts/emails/welcome_email.html", context)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "concierge@houseofbore.com")
    
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[user.email]
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
    return True


def send_verification_email(user: Any, request: Optional[HttpRequest] = None) -> bool:
    """
    Generate secure verification token and dispatch verification email.
    
    Prepares the infrastructure for email verification activation in Phase 3.3.
    """
    if not user or not getattr(user, "email", None):
        return False

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    
    verify_path = reverse("accounts:verify_email", kwargs={"uidb64": uidb64, "token": token})
    verification_url = _get_absolute_url(request, verify_path)

    context = {
        "user": user,
        "site_name": "House of Bore",
        "verification_url": verification_url,
        "token": token,
        "uidb64": uidb64,
    }

    subject = "Please Verify Your Email Address — House of Bore"
    text_body = render_to_string("accounts/emails/verification_email.txt", context)
    html_body = render_to_string("accounts/emails/verification_email.html", context)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "concierge@houseofbore.com")

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[user.email]
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
    return True


def _get_absolute_url(request: Optional[HttpRequest], path: str) -> str:
    """
    Helper to construct an absolute URL using the HTTP request host or local fallback.
    """
    if request is not None:
        return request.build_absolute_uri(path)
    return f"http://127.0.0.1:8000{path}"
