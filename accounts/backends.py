# accounts/backends.py
"""
accounts/backends.py
──────────────────────────────────────────────────────────────────────────────
Custom authentication backend for House of Bore.

DESIGN DECISIONS
────────────────
1.  Case-Insensitive Email Lookup
    While our custom User model uses `email` as USERNAME_FIELD, Django's default
    ModelBackend performs exact case string matching when querying by natural key.
    This backend ensures that customers who registered with 'Patron@HouseOfBore.com'
    can log in seamlessly with 'patron@houseofbore.com' without authentication errors.

2.  Timing Attack Mitigation
    When an email address is not found in the database, we run the password hasher
    once against an empty/dummy User object. This ensures the authentication time
    is relatively constant whether an account exists or not, preventing bad actors
    from enumerating registered email addresses via timing discrepancies.

3.  Framework Compliance
    Inherits from `ModelBackend` and respects `user_can_authenticate(user)` to
    ensure deactivated (`is_active = False`) users are properly rejected.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Optional
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

User = get_user_model()


class EmailAuthenticationBackend(ModelBackend):
    """
    Custom authentication backend allowing case-insensitive email login.
    """

    def authenticate(
        self,
        request: Optional[HttpRequest],
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any
    ) -> Optional[Any]:
        """
        Authenticate a user by case-insensitive email and password.
        
        Supports both 'email' and 'username' keyword arguments for compatibility
        with Django's built-in auth forms and custom login workflows.
        """
        email = kwargs.get("email") or username
        if not email or not password:
            return None

        # Clean/normalize email to match lowercase indexed field
        normalized_email = email.strip().lower()

        try:
            # Exact lookup utilizing standard B-Tree unique index on email
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            # Run password hasher once to mitigate timing attacks enumerating existing emails
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # In the rare/impossible case of duplicates due to legacy data, get the first
            user = User.objects.filter(email=normalized_email).order_by("id").first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
