# accounts/selectors.py
"""
accounts/selectors.py
──────────────────────────────────────────────────────────────────────────────
Read-only queries and data lookup helpers for the accounts app.

Keeps database query logic out of forms, views, and services, promoting DRY
principles and clean separation of concerns.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Optional
from django.contrib.auth import get_user_model
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from .models import UserProfile, Address

User = get_user_model()


def get_user_by_email(email: str) -> Optional[Any]:
    """
    Retrieve a user instance by case-insensitive email lookup.
    
    Returns None if no user exists with the given email address.
    """
    if not email or not isinstance(email, str):
        return None
    return User.objects.filter(email__iexact=email.strip()).first()


def email_exists(email: str) -> bool:
    """
    Check whether an account already exists with the given email address.
    
    Performs a case-insensitive check using database-level indexes.
    """
    if not email or not isinstance(email, str):
        return False
    return User.objects.filter(email__iexact=email.strip()).exists()


def username_exists(username: str) -> bool:
    """
    Check whether a username already exists in the system.
    
    Adaptive implementation:
    If the project's User model explicitly supports a 'username' field, performs
    a case-insensitive lookup against that field. Since House of Bore uses email
    as the unique identifier and sets `username = None`, this method checks if
    the identifier matches an existing email address or returns False.
    """
    if not username or not isinstance(username, str):
        return False

    cleaned_name = username.strip()
    if hasattr(User, "username") and getattr(User, "username", None) is not None:
        return User.objects.filter(username__iexact=cleaned_name).exists()

    # Fallback/alias check against email if username field is not on the model schema
    return email_exists(cleaned_name)


def get_user_by_pk(pk: Any) -> Optional[Any]:
    """
    Retrieve a user instance by primary key.
    
    Returns None if no user exists with the given primary key or if pk is invalid.
    """
    if pk is None or pk == "":
        return None
    try:
        return User.objects.filter(pk=pk).first()
    except (ValueError, TypeError):
        return None


def get_user_by_uidb64(uidb64: str) -> Optional[Any]:
    """
    Safely decode a URL-safe base64 encoded user primary key and retrieve the user instance.
    
    Returns None if decoding fails or no corresponding user exists.
    """
    if not uidb64 or not isinstance(uidb64, str):
        return None
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return get_user_by_pk(uid)
    except (TypeError, ValueError, OverflowError, Exception):
        return None


def is_email_verified(user: Any) -> bool:
    """
    Check whether a user account has verified its email address.
    
    Returns False if user is None, anonymous, or unverified.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return getattr(user, "email_verified", False)


def get_users_for_password_reset(email: str) -> Any:
    """
    Retrieve a queryset of active users matching the given email address (case-insensitive)
    for password reset email dispatch.
    
    Returns an empty queryset if email is invalid or empty.
    """
    if not email or not isinstance(email, str):
        return User.objects.none()
    return User.objects.filter(email__iexact=email.strip(), is_active=True)


def get_profile(user: Any) -> Optional[UserProfile]:
    """
    Retrieve the UserProfile for a given user.
    Leverages Django's internal reverse relation cache (hasattr/user.profile)
    before falling back to get_or_create to eliminate redundant database queries.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    try:
        if hasattr(user, "profile") and user.profile is not None:
            return user.profile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        return profile
    except Exception:
        return None


def profile_completion_percentage(user: Any) -> int:
    """
    Calculate the profile completion percentage (0-100) for a given user.
    
    Designed modularly so criteria can be expanded in future phases
    (e.g., adding address count, loyalty preferences, etc.).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return 0

    profile = get_profile(user)
    if not profile:
        return 0

    criteria = [
        ("email_verified", bool(getattr(user, "email_verified", False))),
        ("phone_number", bool(profile.phone_number and profile.phone_number.strip())),
        ("avatar", bool(profile.avatar and profile.avatar.name)),
        ("date_of_birth", bool(profile.date_of_birth)),
        ("preferred_language", bool(profile.preferred_language)),
        ("preferred_currency", bool(profile.preferred_currency)),
    ]

    completed_count = sum(1 for _, is_complete in criteria if is_complete)
    total_count = len(criteria)
    return int((completed_count / total_count) * 100) if total_count > 0 else 0


def get_user_addresses(user: Any) -> Any:
    """
    Retrieve all saved addresses for a given user, ordered by default status
    and recent updates. Uses select_related to optimize query performance.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Address.objects.none()
    return Address.objects.filter(user=user).select_related("user").order_by(
        "-is_default_shipping", "-is_default_billing", "-updated_at"
    )


def get_user_address_by_pk(user: Any, pk: Any) -> Optional[Address]:
    """
    Retrieve a specific address by primary key, enforcing that it belongs to the given user.
    """
    if not user or not getattr(user, "is_authenticated", False) or pk is None or pk == "":
        return None
    try:
        return Address.objects.filter(user=user, pk=pk).select_related("user").first()
    except (ValueError, TypeError):
        return None


def get_default_shipping(user: Any) -> Optional[Address]:
    """
    Retrieve the user's default shipping address.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return Address.objects.filter(user=user, is_default_shipping=True).select_related("user").first()


def get_default_billing(user: Any) -> Optional[Address]:
    """
    Retrieve the user's default billing address.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return Address.objects.filter(user=user, is_default_billing=True).select_related("user").first()

