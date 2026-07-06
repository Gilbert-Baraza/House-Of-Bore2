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
