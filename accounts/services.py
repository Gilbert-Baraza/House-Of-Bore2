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
from typing import Any, Optional, Tuple
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.selectors import get_user_by_uidb64, is_email_verified

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

    phone = extra_fields.get("phone") or extra_fields.get("phone_number")
    if phone:
        from .selectors import get_profile
        profile = get_profile(user)
        if profile:
            profile.phone_number = str(phone).strip()
            profile.save(update_fields=["phone_number", "updated_at"])

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
    try:
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}", exc_info=True)
        return False


def send_verification_email(user: Any, request: Optional[HttpRequest] = None) -> bool:
    """
    Generate secure verification token and dispatch luxury-branded verification email.
    
    Includes secure token generation, absolute URL construction, fallback text link,
    security notice, and concierge support placeholder.
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
        "support_email": "concierge@houseofbore.com",
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
    try:
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {e}", exc_info=True)
        return False


def send_password_reset_email(user: Any, request: Optional[HttpRequest] = None) -> bool:
    """
    Generate secure password reset token and dispatch password reset email.
    
    Uses Django's built-in token generator and builds absolute reset confirmation URLs.
    Never reveals whether an email address exists during password reset requests.
    """
    if not user or not getattr(user, "email", None) or not getattr(user, "is_active", False):
        return False

    cache_key = f"password_reset_{user.pk}"
    if cache.get(cache_key):
        logger.warning(f"Password reset email throttled for {user.email}")
        return False

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    reset_path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
    reset_url = _get_absolute_url(request, reset_path)

    context = {
        "user": user,
        "site_name": "House of Bore",
        "reset_url": reset_url,
        "token": token,
        "uidb64": uidb64,
        "support_email": "concierge@houseofbore.com",
    }

    subject = "Password Reset Request — House of Bore"
    text_body = render_to_string("accounts/emails/password_reset.txt", context)
    html_body = render_to_string("accounts/emails/password_reset.html", context)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "concierge@houseofbore.com")

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[user.email]
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send(fail_silently=False)
        cache.set(cache_key, True, 60)  # 60 seconds cooldown
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {e}", exc_info=True)
        return False


def verify_email_token(uidb64: str, token: str) -> Tuple[bool, str, Optional[Any]]:
    """
    Validate an email verification token and mark the account as verified if valid.
    
    Returns:
        tuple[bool, str, Optional[User]]:
        - (True, "already_verified", user) if the user was already verified.
        - (True, "success", user) if verification succeeded.
        - (False, "user_not_found", None) if uidb64 decoding failed or user does not exist.
        - (False, "invalid_token", user) if token check failed.
    """
    user = get_user_by_uidb64(uidb64)
    if not user:
        return False, "user_not_found", None

    if is_email_verified(user):
        return True, "already_verified", user

    if default_token_generator.check_token(user, token):
        user.verify_email()
        return True, "success", user

    return False, "invalid_token", user


def resend_verification_email(user: Any, request: Optional[HttpRequest] = None) -> Tuple[bool, str]:
    """
    Resend verification email to an authenticated user if not already verified.
    
    Returns:
        tuple[bool, str]:
        - (False, "already_verified") if user has already verified their email.
        - (False, "throttled") if verification email was requested within the last 60 seconds.
        - (False, "failed") if email dispatch failed.
        - (True, "sent") if verification email was dispatched.
    """
    if is_email_verified(user):
        return False, "already_verified"

    cache_key = f"resend_verification_{user.pk}"
    if cache.get(cache_key):
        logger.warning(f"Resend verification email throttled for user {user.pk}")
        return False, "throttled"

    sent = send_verification_email(user, request=request)
    if sent:
        cache.set(cache_key, True, 60)  # 60 seconds cooldown
        return True, "sent"
    return False, "failed"


def _get_absolute_url(request: Optional[HttpRequest], path: str) -> str:
    """
    Helper to construct an absolute URL using the HTTP request host or local fallback.
    """
    if request is not None:
        return request.build_absolute_uri(path)
    return f"http://127.0.0.1:8000{path}"


def update_profile(user: Any, **data: Any) -> Optional[Any]:
    """
    Update a user's UserProfile attributes and save to the database.
    
    Allowed attributes: phone_number, date_of_birth, preferred_language,
    preferred_currency, marketing_emails.
    """
    from .selectors import get_profile
    profile = get_profile(user)
    if not profile:
        return None

    allowed_fields = [
        "phone_number",
        "date_of_birth",
        "preferred_language",
        "preferred_currency",
        "marketing_emails",
    ]
    updated_fields = []
    for field in allowed_fields:
        if field in data:
            setattr(profile, field, data[field])
            updated_fields.append(field)

    if updated_fields:
        updated_fields.append("updated_at")
        profile.save(update_fields=updated_fields)
    return profile


def update_avatar(user: Any, avatar_file: Any) -> tuple[bool, str]:
    """
    Validate and upload a new avatar image for the user's profile.
    
    Replaces any existing avatar file.
    Validates max file size (2MB) and valid image extension/MIME.
    
    Returns:
        tuple[bool, str]: (Success boolean, Status/Error message)
    """
    from .selectors import get_profile
    profile = get_profile(user)
    if not profile:
        return False, "Profile not found."

    if not avatar_file:
        return False, "No file provided."

    # Max size check: 2MB
    max_size = 2 * 1024 * 1024
    if getattr(avatar_file, "size", 0) > max_size:
        return False, "Image file too large. Maximum allowed size is 2MB."

    # Extension / MIME check
    valid_extensions = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
    file_name = getattr(avatar_file, "name", "").lower()
    if not any(file_name.endswith(ext) for ext in valid_extensions):
        return False, "Invalid image format. Supported formats: JPEG, PNG, WEBP, GIF."

    # Pillow content verification (defense-in-depth against polyglot/disguised files)
    try:
        import io
        from PIL import Image
        from django.core.files.base import ContentFile
        if hasattr(avatar_file, "seek") and not getattr(avatar_file, "closed", False):
            avatar_file.seek(0)
        content = avatar_file.read()
        img = Image.open(io.BytesIO(content))
        img.verify()
    except Exception as e:
        logger.warning(f"Avatar file verification failed for user {user.pk}: {e}")
        return False, "Invalid or corrupted image file."

    try:
        # Delete old avatar file from storage if present
        if profile.avatar and profile.avatar.name:
            try:
                profile.avatar.delete(save=False)
            except Exception as e:
                logger.warning(f"Could not delete old avatar for user {user.pk}: {e}")

        file_name = getattr(avatar_file, "name", "avatar.jpg")
        profile.avatar = ContentFile(content, name=file_name)
        profile.save(update_fields=["avatar", "updated_at"])
        return True, "Avatar updated successfully."
    except Exception as e:
        logger.error(f"Failed to update avatar for user {user.pk}: {e}", exc_info=True)
        return False, "An error occurred while saving the image."


def remove_avatar(user: Any) -> bool:
    """
    Remove and delete the avatar image from the user's profile.
    """
    from .selectors import get_profile
    profile = get_profile(user)
    if not profile or not profile.avatar:
        return False

    try:
        profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save(update_fields=["avatar", "updated_at"])
        return True
    except Exception as e:
        logger.error(f"Failed to remove avatar for user {user.pk}: {e}", exc_info=True)
        return False


@transaction.atomic
def create_address(user: Any, **data: Any) -> Any:
    """
    Create a new address for the customer.
    If this is the user's first address (or first shipping/billing capable address),
    automatically assign it as the default for that type.
    """
    from accounts.models import Address

    address_type = data.get("address_type", "both")

    has_shipping = Address.objects.filter(user=user, is_default_shipping=True).exists()
    has_billing = Address.objects.filter(user=user, is_default_billing=True).exists()

    if not has_shipping and address_type in ("shipping", "both"):
        data["is_default_shipping"] = True
    if not has_billing and address_type in ("billing", "both"):
        data["is_default_billing"] = True

    address = Address.objects.create(user=user, **data)
    return address


@transaction.atomic
def update_address(address: Any, **data: Any) -> Any:
    """
    Update an existing address with new data.
    """
    for key, value in data.items():
        if hasattr(address, key) and key != "user":
            setattr(address, key, value)
    address.save()
    return address


@transaction.atomic
def delete_address(address: Any) -> bool:
    """
    Delete an address. If a default shipping or billing address is deleted,
    automatically promote the most recently updated remaining address of that
    type to default to prevent database inconsistency.
    """
    if not address or not address.pk:
        return False

    user = address.user
    was_default_shipping = address.is_default_shipping
    was_default_billing = address.is_default_billing

    try:
        from accounts.models import Address
        address.delete()

        if was_default_shipping:
            fallback_shipping = Address.objects.filter(
                user=user, address_type__in=["shipping", "both"]
            ).order_by("-updated_at").first()
            if fallback_shipping:
                fallback_shipping.is_default_shipping = True
                fallback_shipping.save(update_fields=["is_default_shipping", "updated_at"])

        if was_default_billing:
            fallback_billing = Address.objects.filter(
                user=user, address_type__in=["billing", "both"]
            ).order_by("-updated_at").first()
            if fallback_billing:
                fallback_billing.is_default_billing = True
                fallback_billing.save(update_fields=["is_default_billing", "updated_at"])

        return True
    except Exception as e:
        logger.error(f"Failed to delete address {address.pk}: {e}", exc_info=True)
        return False


@transaction.atomic
def set_default_shipping(address: Any) -> Any:
    """
    Set the specified address as the user's default shipping address
    and unset any previous default.
    """
    if not address or not address.pk:
        return None
    if address.address_type == "billing":
        address.address_type = "both"
    address.is_default_shipping = True
    address.save()
    return address


@transaction.atomic
def set_default_billing(address: Any) -> Any:
    """
    Set the specified address as the user's default billing address
    and unset any previous default.
    """
    if not address or not address.pk:
        return None
    if address.address_type == "shipping":
        address.address_type = "both"
    address.is_default_billing = True
    address.save()
    return address


def format_address(address: Any, html: bool = False) -> str:
    """
    Reusable address formatter.
    Returns formatted address string consistently across the application.
    If html=True, returns HTML line breaks (<br>) with escaped text.
    """
    if not address:
        return ""
    if html:
        from django.utils.html import escape
        lines = [escape(address.recipient_name)]
        if address.company_name:
            lines.append(escape(address.company_name))
        lines.append(escape(address.address_line_1))
        if address.address_line_2:
            lines.append(escape(address.address_line_2))

        city_line = f"{escape(address.city)}, {escape(address.county_or_state)}"
        if address.postal_code:
            city_line += f" {escape(address.postal_code)}"
        lines.append(city_line)

        country_display = address.get_country_display() if hasattr(address, "get_country_display") else address.country
        lines.append(escape(str(country_display)))
        return "<br>".join(lines)

    return getattr(address, "formatted_address", "") or str(address)

