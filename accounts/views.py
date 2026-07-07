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
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import FormView, ListView, TemplateView, View

from accounts.forms import (
    UserLoginForm,
    UserPasswordChangeForm,
    UserPasswordResetForm,
    UserRegistrationForm,
    UserSetPasswordForm,
    ProfileUpdateForm,
    AvatarUploadForm,
    AddressForm,
)
from accounts.selectors import (
    is_email_verified,
    get_profile,
    profile_completion_percentage,
    get_user_addresses,
    get_user_address_by_pk,
    get_default_shipping,
    get_default_billing,
)
from accounts.services import (
    register_user,
    resend_verification_email,
    verify_email_token,
    update_profile,
    update_avatar,
    remove_avatar,
    create_address,
    update_address,
    delete_address,
    set_default_shipping,
    set_default_billing,
)


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
    Active view for email verification token validation.
    
    Validates token and renders appropriate success, already verified, or invalid token pages.
    """
    def get(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        success, status, user = verify_email_token(uidb64, token)
        if status == "success":
            return render(request, "accounts/email_verified.html", {"user": user})
        elif status == "already_verified":
            return render(request, "accounts/email_verification_already.html", {"user": user})
        else:
            return render(request, "accounts/email_verification_invalid.html", {"uidb64": uidb64, "token": token})


class ResendVerificationView(LoginRequiredMixin, View):
    """
    View for resending verification emails to authenticated users.
    
    Requires authentication per Phase 3.3 specification.
    """
    def get(self, request: HttpRequest) -> HttpResponse:
        if is_email_verified(request.user):
            return render(request, "accounts/email_verification_already.html", {"user": request.user})
        return render(request, "accounts/resend_verification.html", {"user": request.user})

    def post(self, request: HttpRequest) -> HttpResponse:
        if is_email_verified(request.user):
            messages.info(request, "Your email address is already verified.")
            return redirect("core:home")

        success, status = resend_verification_email(request.user, request=request)
        if status == "throttled":
            messages.warning(request, "Please wait at least 60 seconds before requesting another verification email.")
        elif status == "failed":
            messages.error(request, "We encountered an issue sending your verification email. Please try again later.")
        elif success:
            messages.success(
                request,
                "A new verification email has been dispatched to your email address. Please check your inbox."
            )
        else:
            messages.info(request, "Your account is already verified.")
        return redirect("accounts:resend_verification")


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


class PasswordResetView(FormView):
    """
    View for requesting a password reset email.
    """
    template_name = "accounts/password_reset_form.html"
    form_class = UserPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form: UserPasswordResetForm) -> HttpResponse:
        form.save(request=self.request)
        return super().form_valid(form)


class PasswordResetDoneView(TemplateView):
    """
    Confirmation view indicating password reset instructions have been dispatched.
    """
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    View for entering a new password using a valid reset token.
    """
    template_name = "accounts/password_reset_confirm.html"
    form_class = UserSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(TemplateView):
    """
    Success view confirming password has been reset.
    """
    template_name = "accounts/password_reset_complete.html"


class PasswordChangeView(LoginRequiredMixin, auth_views.PasswordChangeView):
    """
    View for authenticated users to change their current password.
    
    Automatically updates session auth hash to maintain login state.
    """
    template_name = "accounts/password_change.html"
    form_class = UserPasswordChangeForm
    success_url = reverse_lazy("core:home")

    def form_valid(self, form: Any) -> HttpResponse:
        messages.success(
            self.request,
            "Your password has been changed successfully. You remain securely signed in."
        )
        return super().form_valid(form)


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    Renders the customer profile overview dashboard.
    
    Displays avatar, member details, verification status, marketing preference,
    and profile completion percentage.
    """
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["profile"] = get_profile(user)
        context["completion_percentage"] = profile_completion_percentage(user)
        return context


class ProfileEditView(LoginRequiredMixin, View):
    """
    Renders and processes the customer profile and avatar update forms.
    
    Handles personal information updates, avatar image uploads, and avatar removals.
    Enforces that email and password cannot be modified here.
    """
    template_name = "accounts/profile_edit.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        profile = get_profile(request.user)
        profile_form = ProfileUpdateForm(instance=profile)
        avatar_form = AvatarUploadForm(instance=profile)
        return render(request, self.template_name, {
            "profile": profile,
            "profile_form": profile_form,
            "avatar_form": avatar_form,
        })

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        profile = get_profile(request.user)
        action = request.POST.get("action", "update_profile")

        if action == "remove_avatar":
            if remove_avatar(request.user):
                messages.success(request, "Your profile photo has been removed.")
            else:
                messages.error(request, "Could not remove profile photo.")
            return redirect("accounts:profile_edit")

        elif action == "upload_avatar":
            avatar_form = AvatarUploadForm(request.POST, request.FILES, instance=profile)
            if avatar_form.is_valid():
                success, msg = update_avatar(request.user, avatar_form.cleaned_data["avatar"])
                if success:
                    messages.success(request, msg)
                    return redirect("accounts:profile_edit")
                else:
                    messages.error(request, msg)
            profile_form = ProfileUpdateForm(instance=profile)
            return render(request, self.template_name, {
                "profile": profile,
                "profile_form": profile_form,
                "avatar_form": avatar_form,
            })

        else:
            # Default action: update personal info & preferences
            profile_form = ProfileUpdateForm(request.POST, instance=profile)
            if profile_form.is_valid():
                update_profile(request.user, **profile_form.cleaned_data)
                messages.success(request, "Your profile information has been updated successfully.")
                return redirect("accounts:profile")
            
            avatar_form = AvatarUploadForm(instance=profile)
            return render(request, self.template_name, {
                "profile": profile,
                "profile_form": profile_form,
                "avatar_form": avatar_form,
            })


class AddressListView(LoginRequiredMixin, ListView):
    """
    Renders the authenticated customer's address book.
    Displays all saved shipping and billing addresses with default indicators.
    """
    template_name = "accounts/address_list.html"
    context_object_name = "addresses"

    def get_queryset(self):
        return get_user_addresses(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["default_shipping"] = get_default_shipping(user)
        context["default_billing"] = get_default_billing(user)
        context["active_nav"] = "addresses"
        return context


class AddressCreateView(LoginRequiredMixin, View):
    """
    Renders address creation form and processes new address submission.
    """
    template_name = "accounts/address_form.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = AddressForm()
        return render(request, self.template_name, {
            "form": form,
            "title": "Add New Address",
            "active_nav": "addresses",
        })

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = AddressForm(request.POST)
        if form.is_valid():
            create_address(user=request.user, **form.cleaned_data)
            messages.success(request, "Your new address has been added to your Address Book.")
            return redirect("accounts:address_list")
        return render(request, self.template_name, {
            "form": form,
            "title": "Add New Address",
            "active_nav": "addresses",
        })


class AddressUpdateView(LoginRequiredMixin, View):
    """
    Renders address update form and processes address edits.
    Enforces that the address belongs to the authenticated user.
    """
    template_name = "accounts/address_form.html"

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        address = get_user_address_by_pk(request.user, pk)
        if not address:
            from django.http import Http404
            raise Http404("Address not found.")
        form = AddressForm(instance=address)
        return render(request, self.template_name, {
            "form": form,
            "address": address,
            "title": "Edit Address",
            "active_nav": "addresses",
        })

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        address = get_user_address_by_pk(request.user, pk)
        if not address:
            from django.http import Http404
            raise Http404("Address not found.")
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            update_address(address=address, **form.cleaned_data)
            messages.success(request, f"Address '{address.label}' has been updated successfully.")
            return redirect("accounts:address_list")
        return render(request, self.template_name, {
            "form": form,
            "address": address,
            "title": "Edit Address",
            "active_nav": "addresses",
        })


class AddressDeleteView(LoginRequiredMixin, View):
    """
    Handles address deletion.
    Displays confirmation page on GET and executes deletion on POST.
    Enforces that the address belongs to the authenticated user.
    """
    template_name = "accounts/address_confirm_delete.html"

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        address = get_user_address_by_pk(request.user, pk)
        if not address:
            from django.http import Http404
            raise Http404("Address not found.")
        return render(request, self.template_name, {
            "address": address,
            "active_nav": "addresses",
        })

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        address = get_user_address_by_pk(request.user, pk)
        if not address:
            from django.http import Http404
            raise Http404("Address not found.")
        label = address.label
        if delete_address(address):
            messages.success(request, f"Address '{label}' has been removed from your Address Book.")
        else:
            messages.error(request, f"Could not remove address '{label}'.")
        return redirect("accounts:address_list")


class AddressSetDefaultView(LoginRequiredMixin, View):
    """
    POST-only endpoint to set an address as default shipping or default billing.
    Enforces that the address belongs to the authenticated user.
    """
    def post(self, request: HttpRequest, pk: int, address_type: str, *args: Any, **kwargs: Any) -> HttpResponse:
        address = get_user_address_by_pk(request.user, pk)
        if not address:
            from django.http import Http404
            raise Http404("Address not found.")

        if address_type == "shipping":
            set_default_shipping(address)
            messages.success(request, f"'{address.label}' is now your default shipping address.")
        elif address_type == "billing":
            set_default_billing(address)
            messages.success(request, f"'{address.label}' is now your default billing address.")
        else:
            messages.error(request, "Invalid address type specified.")

        return redirect("accounts:address_list")

