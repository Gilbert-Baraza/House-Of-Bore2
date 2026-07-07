# accounts/decorators.py
"""
accounts/decorators.py
──────────────────────────────────────────────────────────────────────────────
Route protection infrastructure for email verification enforcement.

Provides reusable decorators, class-based view mixins, and middleware to restrict
access to sensitive customer features (e.g., checkout, reviews, dashboard) to
users with a verified email address.

Per Phase 3.3 requirements, these components are prepared and tested but not yet
enforced globally across the application.
──────────────────────────────────────────────────────────────────────────────
"""

from functools import wraps
from typing import Any, Callable, Optional
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from accounts.selectors import is_email_verified
from accounts.services import _get_client_ip


def verified_email_required(
    function: Optional[Callable[..., Any]] = None,
    redirect_url: Optional[str] = None,
    message: str = "Please verify your email address to access this feature.",
) -> Callable[..., Any]:
    """
    Decorator for views that checks that the user is logged in and has verified their email.

    If unauthenticated, redirects to the login page.
    If authenticated but unverified, flashes a warning message and redirects to the
    resend verification page (or custom redirect_url).
    """
    def decorator(view_func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                login_url = reverse("accounts:login")
                return redirect(f"{login_url}?next={request.path}")

            if not is_email_verified(request.user):
                if message:
                    messages.warning(request, message)
                target_url = redirect_url or reverse("accounts:resend_verification")
                return redirect(target_url)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    if function:
        return decorator(function)
    return decorator


class VerifiedEmailRequiredMixin(AccessMixin):
    """
    Class-based view mixin ensuring the current user is authenticated and has verified their email.

    If unauthenticated, delegates to AccessMixin.handle_no_permission() (redirecting to login).
    If authenticated but unverified, redirects to the resend verification page with a flash message.
    """
    unverified_redirect_url: Optional[str] = None
    verification_required_message: str = "Please verify your email address to access this feature."

    def get_unverified_redirect_url(self) -> str:
        if self.unverified_redirect_url:
            return self.unverified_redirect_url
        return reverse("accounts:resend_verification")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not is_email_verified(request.user):
            if self.verification_required_message:
                messages.warning(request, self.verification_required_message)
            return redirect(self.get_unverified_redirect_url())

        return super().dispatch(request, *args, **kwargs)


class EmailVerificationMiddleware:
    """
    Middleware for path-based email verification enforcement.

    Allows configuring a list of URL prefixes (`protected_prefixes`) that require an
    authenticated and verified email address. Can be activated in settings.MIDDLEWARE
    when global or path-level enforcement is desired.
    """
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Default protected URL prefixes for future phases (Reviews, Checkout, Dashboard)
        self.protected_prefixes = getattr(
            settings,
            "EMAIL_VERIFICATION_PROTECTED_PREFIXES",
            [
                "/reviews/create/",
                "/checkout/",
                "/dashboard/",
            ],
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Check if current path matches any protected prefix
        if any(request.path.startswith(prefix) for prefix in self.protected_prefixes):
            if not request.user.is_authenticated:
                login_url = reverse("accounts:login")
                return redirect(f"{login_url}?next={request.path}")

            if not is_email_verified(request.user):
                messages.warning(
                    request,
                    "A verified email address is required to access this section."
                )
                return redirect(reverse("accounts:resend_verification"))

        return self.get_response(request)


class ThrottleAuthMixin:
    """
    Class-based view mixin to throttle POST requests on sensitive authentication endpoints
    (such as login and registration) to prevent brute-force and credential stuffing attacks.
    
    Tracks failed attempts by client IP address and email address using Django's cache backend.
    """
    throttle_limit: int = 10  # max attempts per time window
    throttle_timeout: int = 300  # time window in seconds (5 minutes)

    def get_throttle_keys(self, request: HttpRequest) -> tuple[str, Optional[str]]:
        ip = _get_client_ip(request) or "unknown_ip"
        email = request.POST.get("email", "").strip().lower()
        ip_key = f"throttle_ip_{request.path}_{ip}"
        email_key = f"throttle_email_{request.path}_{email}" if email else None
        return ip_key, email_key

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.method == "POST":
            ip_key, email_key = self.get_throttle_keys(request)
            ip_count = cache.get(ip_key, 0)
            email_count = cache.get(email_key, 0) if email_key else 0

            if ip_count >= self.throttle_limit or email_count >= self.throttle_limit:
                messages.error(
                    request,
                    "Too many unsuccessful attempts. For your security, please wait a few minutes before trying again."
                )
                if hasattr(self, "get_form") and hasattr(self, "render_to_response"):
                    form = self.get_form()  # type: ignore[attr-defined]
                    return self.render_to_response(self.get_context_data(form=form))  # type: ignore[attr-defined]
                return redirect(request.path)

            # Increment throttle counters
            cache.set(ip_key, ip_count + 1, self.throttle_timeout)
            if email_key:
                cache.set(email_key, email_count + 1, self.throttle_timeout)

        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    def clear_throttle_counters(self, request: HttpRequest) -> None:
        """
        Clear throttle counters upon successful authentication or registration.
        """
        ip_key, email_key = self.get_throttle_keys(request)
        cache.delete(ip_key)
        if email_key:
            cache.delete(email_key)

