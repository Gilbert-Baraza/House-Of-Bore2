# accounts/views.py
"""
accounts/views.py
──────────────────────────────────────────────────────────────────────────────
Class-based views for authentication and customer account management.

In Phase 3.1, implements:
- RegistrationView: Customer registration form and account creation (no auto-login).
- RegistrationSuccessView: Confirmation page after successful account registration.
- VerifyEmailView: Placeholder for verification activation (to be enabled in Phase 3.3).
- ResendVerificationView: Placeholder for resending verification tokens (Phase 3.3).
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, views as auth_views
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import FormView, TemplateView, View

from accounts.forms import UserLoginForm, UserRegistrationForm
from accounts.services import register_user


class RegistrationView(FormView):
    """
    Renders the registration form and handles new customer account creation.
    
    Upon successful validation and creation, redirects the user to the registration
    success page without logging them in automatically.
    """
    template_name = "accounts/register.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("accounts:register_success")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # Redirect already authenticated users to the homepage
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: UserRegistrationForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        
        extra_fields = {}
        if form.cleaned_data.get("phone"):
            extra_fields["phone"] = form.cleaned_data["phone"]
        if form.cleaned_data.get("username"):
            extra_fields["username"] = form.cleaned_data["username"]

        register_user(
            email=email,
            password=password,
            request=self.request,
            **extra_fields
        )

        messages.success(
            self.request,
            "Your account has been created successfully. Please check your inbox for verification instructions."
        )
        return super().form_valid(form)


class RegistrationSuccessView(TemplateView):
    """
    Displays confirmation message and next steps after registration.
    """
    template_name = "accounts/register_success.html"


class VerifyEmailView(View):
    """
    Placeholder view for email verification activation (to be enabled in Phase 3.3).
    
    In Phase 3.1, confirms receipt of the token and redirects to the success page.
    """
    def get(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        messages.info(
            request,
            "Email verification activation is scheduled for Phase 3.3. Your verification token was received successfully."
        )
        return redirect(reverse("accounts:register_success"))


class ResendVerificationView(View):
    """
    Placeholder view for resending verification emails (to be enabled in Phase 3.3).
    """
    def get(self, request: HttpRequest) -> HttpResponse:
        messages.info(
            request,
            "Resending verification emails is scheduled for Phase 3.3."
        )
        return redirect(reverse("accounts:register_success"))


class LoginView(auth_views.LoginView):
    """
    Class-based login view handling customer authentication, session persistence
    ('Remember Me'), safe redirection, and flash messaging.
    """
    template_name = "accounts/login.html"
    form_class = UserLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form: Any) -> HttpResponse:
        """
        Handle successful authentication: manage session expiry and flash messages.
        """
        response = super().form_valid(form)

        remember_me = form.cleaned_data.get("remember_me", False)
        if remember_me:
            # Persistent session: 30 days (in seconds: 30 * 24 * 60 * 60 = 2592000)
            self.request.session.set_expiry(2592000)
        else:
            # Browser session: expires when browser closes (0)
            self.request.session.set_expiry(0)

        user = form.get_user()
        messages.success(
            self.request,
            f"Welcome back to House of Bore, {user.full_name}."
        )
        return response

    def get_success_url(self) -> str:
        """
        Return safe redirect URL ('next' parameter or fallback to home).
        """
        url = self.get_redirect_url()
        return url or reverse_lazy("core:home")


class LogoutView(View):
    """
    Strictly POST-only logout view destroying session and redirecting to home.
    """
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        auth_logout(request)
        messages.info(request, "You have been securely logged out of your account.")
        return redirect("core:home")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Reject GET requests to comply with safe method RFC semantics."""
        return HttpResponseNotAllowed(["POST"], content="Logout strictly requires a POST request.")
