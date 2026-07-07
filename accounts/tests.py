# accounts/tests.py
"""
accounts/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated tests for Phase 3.1 — User Registration.

Covers:
1. Form validation (required fields, password mismatch, password strength, duplicates).
2. Selectors read queries (email_exists, username_exists, get_user_by_email).
3. Services transactional creation and email notifications (welcome & verification).
4. Class-based views and routing (no auto-login enforcement, redirects, placeholders).
──────────────────────────────────────────────────────────────────────────────
"""

import unittest.mock
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.backends import EmailAuthenticationBackend
from accounts.decorators import verified_email_required, VerifiedEmailRequiredMixin, EmailVerificationMiddleware
from accounts.forms import (
    UserLoginForm,
    UserPasswordChangeForm,
    UserPasswordResetForm,
    UserRegistrationForm,
    UserSetPasswordForm,
    ProfileUpdateForm,
    AvatarUploadForm,
    AddressForm,
    EmailChangeForm,
    AccountDeactivateForm,
    AccountDeleteForm,
)
from accounts.models import UserProfile, Address, PendingEmailChange, AccountActivity, UserSession
from django.contrib.sessions.models import Session
from accounts.selectors import (
    email_exists,
    get_user_by_email,
    get_user_by_pk,
    get_user_by_uidb64,
    get_users_for_password_reset,
    is_email_verified,
    username_exists,
    get_profile,
    profile_completion_percentage,
    get_user_addresses,
    get_user_address_by_pk,
    get_default_shipping,
    get_default_billing,
    get_active_sessions,
    get_recent_activity,
    pending_email_change,
)
from accounts.services import (
    _get_absolute_url,
    register_user,
    resend_verification_email,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
    verify_email_token,
    update_profile,
    update_avatar,
    remove_avatar,
    create_address,
    update_address,
    delete_address,
    set_default_shipping,
    format_address,
    log_account_activity,
    track_user_session,
    request_email_change,
    verify_email_change,
    revoke_session,
    revoke_other_sessions,
    deactivate_account,
    delete_account,
)

User = get_user_model()


class TestSelectors(TestCase):
    """Test read-only queries in accounts/selectors.py."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_get_user_by_email_case_insensitive(self) -> None:
        user = get_user_by_email("PATRON@houseofbore.com")
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "patron@houseofbore.com")

    def test_get_user_by_email_non_existent(self) -> None:
        user = get_user_by_email("unknown@houseofbore.com")
        self.assertIsNone(user)

    def test_get_user_by_email_invalid_input(self) -> None:
        self.assertIsNone(get_user_by_email(""))  # type: ignore[arg-type]
        self.assertIsNone(get_user_by_email(None))  # type: ignore[arg-type]

    def test_email_exists_case_insensitive(self) -> None:
        self.assertTrue(email_exists("patron@houseofbore.com"))
        self.assertTrue(email_exists("PATRON@HOUSEOFBORE.COM"))
        self.assertFalse(email_exists("nobody@houseofbore.com"))

    def test_username_exists_adaptive(self) -> None:
        # Since username = None on our User model, username_exists falls back to checking email
        self.assertTrue(username_exists("patron@houseofbore.com"))
        self.assertFalse(username_exists("nonexistent"))


class TestServices(TestCase):
    """Test transactional business services and email infrastructure in accounts/services.py."""

    def test_register_user_creates_active_account(self) -> None:
        user = register_user(
            email="newpatron@houseofbore.com",
            password="SecurePassword456!",
            phone="+15550001111"
        )
        self.assertIsNotNone(user.pk)
        self.assertEqual(user.email, "newpatron@houseofbore.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("SecurePassword456!"))
        if hasattr(user, "phone"):
            self.assertEqual(user.phone, "+15550001111")

    def test_register_user_triggers_emails(self) -> None:
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            register_user(
                email="conciergetest@houseofbore.com",
                password="SecurePassword789!"
            )
        # Expect 2 emails: Welcome email and Verification email
        self.assertEqual(len(mail.outbox), 2)
        
        subjects = [m.subject for m in mail.outbox]
        self.assertTrue(any("Welcome to House of Bore" in s for s in subjects))
        self.assertTrue(any("Verify Your Email Address" in s for s in subjects))
        
        # Verify HTML alternative is attached
        for m in mail.outbox:
            self.assertEqual(m.to, ["conciergetest@houseofbore.com"])
            self.assertTrue(len(m.alternatives) > 0)
            self.assertEqual(m.alternatives[0][1], "text/html")

    def test_register_user_smtp_failure_resilience(self) -> None:
        """Verify user creation succeeds and commits even if email dispatch fails."""
        with self.captureOnCommitCallbacks(execute=True):
            with unittest.mock.patch("accounts.services.send_welcome_email", side_effect=Exception("SMTP Down")):
                user = register_user(email="smtpfail@houseofbore.com", password="SecurePassword123!")
        self.assertIsNotNone(user.pk)
        self.assertEqual(user.email, "smtpfail@houseofbore.com")
        self.assertTrue(user.is_active)

    def test_send_welcome_email_explicit(self) -> None:
        mail.outbox.clear()
        user = User.objects.create_user(email="testwelcome@houseofbore.com", password="pwd")
        result = send_welcome_email(user)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Welcome", mail.outbox[0].subject)

    def test_send_verification_email_explicit(self) -> None:
        mail.outbox.clear()
        user = User.objects.create_user(email="testverify@houseofbore.com", password="pwd")
        result = send_verification_email(user)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify Your Email Address", mail.outbox[0].subject)


class TestRegistrationForm(TestCase):
    """Test UserRegistrationForm validation rules."""

    def setUp(self) -> None:
        self.existing_user = User.objects.create_user(
            email="existing@houseofbore.com",
            password="ExistingPassword123!"
        )

    def test_valid_form(self) -> None:
        form_data = {
            "email": "validuser@houseofbore.com",
            "phone": "+15559998888",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        if hasattr(User, "username") and getattr(User, "username", None) is not None:
            form_data["username"] = "validusername"
            
        form = UserRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_email_rejected(self) -> None:
        form_data = {
            "email": "EXISTING@houseofbore.com",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertIn("already exists", form.errors["email"][0])

    def test_password_mismatch_rejected(self) -> None:
        form_data = {
            "email": "mismatch@houseofbore.com",
            "password": "ValidSecurePassword123!",
            "confirm_password": "DifferentPassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("confirm_password", form.errors)
        self.assertIn("didn't match", form.errors["confirm_password"][0])

    def test_weak_password_rejected(self) -> None:
        form_data = {
            "email": "weak@houseofbore.com",
            "password": "123",  # Too short, entirely numeric, weak
            "confirm_password": "123",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_missing_legal_checkboxes_rejected(self) -> None:
        form_data = {
            "email": "nolegal@houseofbore.com",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": False,
            "privacy_accepted": False,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("terms_accepted", form.errors)
        self.assertIn("privacy_accepted", form.errors)

    def test_invalid_email_format_rejected(self) -> None:
        form_data = {
            "email": "not-an-email",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_aria_attributes_bound_on_error(self) -> None:
        """Verify aria-invalid and aria-describedby are automatically attached on validation failure."""
        form_data = {
            "email": "not-an-email",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.fields["email"].widget.attrs.get("aria-invalid"), "true")
        self.assertIn("_error", form.fields["email"].widget.attrs.get("aria-describedby", ""))


class TestRegistrationViews(TestCase):
    """Test Class-Based Views and URL routing for Phase 3.1."""

    def setUp(self) -> None:
        self.client = Client()
        self.register_url = reverse("accounts:register")
        self.success_url = reverse("accounts:register_success")

    def test_register_get_renders_template(self) -> None:
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")
        self.assertContains(response, "Create Your Account")

    def test_register_post_creates_user_without_auto_login(self) -> None:
        form_data = {
            "email": "newmember@houseofbore.com",
            "password": "ValidSecurePassword123!",
            "confirm_password": "ValidSecurePassword123!",
            "terms_accepted": True,
            "privacy_accepted": True,
        }
        if hasattr(User, "username") and getattr(User, "username", None) is not None:
            form_data["username"] = "newmember"

        response = self.client.post(self.register_url, data=form_data)
        self.assertRedirects(response, self.success_url)
        
        # Verify user was created in DB
        user = User.objects.filter(email="newmember@houseofbore.com").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)

        # Verify NO AUTO-LOGIN occurred (user should NOT be logged in session)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_user_redirected_from_register(self) -> None:
        user = User.objects.create_user(email="auth@houseofbore.com", password="pwd")
        self.client.force_login(user)
        response = self.client.get(self.register_url)
        self.assertRedirects(response, reverse("core:home"))

    def test_register_success_page_renders(self) -> None:
        response = self.client.get(self.success_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register_success.html")
        self.assertContains(response, "Welcome to the Circle")

    def test_verify_email_active_view_renders_invalid_for_dummy_token(self) -> None:
        verify_url = reverse("accounts:verify_email", kwargs={"uidb64": "testuid", "token": "testtoken"})
        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/email_verification_invalid.html")

    def test_resend_verification_requires_login(self) -> None:
        resend_url = reverse("accounts:resend_verification")
        response = self.client.get(resend_url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={resend_url}")


class TestURLRouting(TestCase):
    """Test URL names resolution and paths."""

    def test_url_paths(self) -> None:
        self.assertEqual(reverse("accounts:login"), "/login/")
        self.assertEqual(reverse("accounts:logout"), "/logout/")
        self.assertEqual(reverse("accounts:register"), "/register/")
        self.assertEqual(reverse("accounts:register_success"), "/register/success/")
        self.assertEqual(reverse("accounts:resend_verification"), "/resend-verification/")
        self.assertEqual(reverse("accounts:verify_email", kwargs={"uidb64": "u", "token": "t"}), "/verify-email/u/t/")

    def test_get_absolute_url_fallback(self) -> None:
        """Verify _get_absolute_url returns local fallback when request is None."""
        url = _get_absolute_url(None, "/verify-email/test/token/")
        self.assertEqual(url, "http://127.0.0.1:8000/verify-email/test/token/")


class TestEmailAuthenticationBackend(TestCase):
    """Test custom EmailAuthenticationBackend."""

    def setUp(self) -> None:
        self.backend = EmailAuthenticationBackend()
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_case_insensitive_email_login(self) -> None:
        user = self.backend.authenticate(None, email="PATRON@HouseOfBore.com", password="SecurePassword123!")
        self.assertIsNotNone(user)
        self.assertEqual(user, self.user)

    def test_invalid_password_returns_none(self) -> None:
        user = self.backend.authenticate(None, email="patron@houseofbore.com", password="WrongPassword!")
        self.assertIsNone(user)

    def test_inactive_user_returns_none(self) -> None:
        self.user.is_active = False
        self.user.save()
        user = self.backend.authenticate(None, email="patron@houseofbore.com", password="SecurePassword123!")
        self.assertIsNone(user)

    def test_nonexistent_user_returns_none(self) -> None:
        user = self.backend.authenticate(None, email="nobody@houseofbore.com", password="Password123!")
        self.assertIsNone(user)


class TestLoginForm(TestCase):
    """Test UserLoginForm validation and ARIA attribute injection."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_valid_credentials(self) -> None:
        form = UserLoginForm(data={"email": "patron@houseofbore.com", "password": "SecurePassword123!"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.get_user(), self.user)

    def test_invalid_credentials_error_and_aria(self) -> None:
        form = UserLoginForm(data={"email": "patron@houseofbore.com", "password": "WrongPassword!"})
        self.assertFalse(form.is_valid())
        self.assertIn("Invalid email address or password", str(form.errors["__all__"]))
        self.assertEqual(form.fields["email"].widget.attrs.get("aria-invalid"), "true")

    def test_inactive_user_error(self) -> None:
        self.user.is_active = False
        self.user.save()
        form = UserLoginForm(data={"email": "patron@houseofbore.com", "password": "SecurePassword123!"})
        self.assertFalse(form.is_valid())
        self.assertIn("Invalid email address or password", str(form.errors["__all__"]))


class TestLoginViews(TestCase):
    """Test LoginView behaviors, session expiry, and safe redirects."""

    def setUp(self) -> None:
        self.client = Client()
        self.login_url = reverse("accounts:login")
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_login_get_renders_template(self) -> None:
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_post_success_without_remember_me(self) -> None:
        response = self.client.post(self.login_url, {
            "email": "patron@houseofbore.com",
            "password": "SecurePassword123!",
            "remember_me": False
        })
        self.assertRedirects(response, reverse("core:home"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_login_post_success_with_remember_me(self) -> None:
        response = self.client.post(self.login_url, {
            "email": "patron@houseofbore.com",
            "password": "SecurePassword123!",
            "remember_me": True
        })
        self.assertRedirects(response, reverse("core:home"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 2592000)

    def test_safe_redirect_handling(self) -> None:
        response = self.client.post(f"{self.login_url}?next=/wishlist/", {
            "email": "patron@houseofbore.com",
            "password": "SecurePassword123!",
        })
        self.assertRedirects(response, "/wishlist/")

    def test_open_redirect_protection(self) -> None:
        response = self.client.post(f"{self.login_url}?next=https://evil.com/", {
            "email": "patron@houseofbore.com",
            "password": "SecurePassword123!",
        })
        self.assertRedirects(response, reverse("core:home"))

    def test_authenticated_user_redirected_away_from_login(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.login_url)
        self.assertRedirects(response, reverse("core:home"))


class TestLogoutViews(TestCase):
    """Test strictly POST-only logout enforcement."""

    def setUp(self) -> None:
        self.client = Client()
        self.logout_url = reverse("accounts:logout")
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!"
        )
        self.client.force_login(self.user)

    def test_logout_post_success(self) -> None:
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_get_rejected(self) -> None:
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)


class TestNavbarRendering(TestCase):
    """Test dynamic navbar rendering based on authentication state."""

    def setUp(self) -> None:
        self.client = Client()
        self.home_url = reverse("core:home")
        self.user = User.objects.create_user(
            email="patron@houseofbore.com",
            password="SecurePassword123!",
            first_name="Arthur",
            last_name="Pendleton"
        )

    def test_navbar_anonymous_state(self) -> None:
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:register"))
        self.assertNotContains(response, reverse("accounts:logout"))

    def test_navbar_authenticated_state(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("accounts:logout"))
        self.assertContains(response, reverse("wishlist:wishlist"))
        self.assertNotContains(response, "Sign In")


class TestEmailVerificationAndSelectors(TestCase):
    """Test email verification model methods, selectors, and services."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="verify_test@houseofbore.com",
            password="SecurePassword123!",
            is_active=True,
        )

    def test_verify_email_model_method(self) -> None:
        self.assertFalse(self.user.email_verified)
        self.assertIsNone(self.user.email_verified_at)
        self.user.verify_email()
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(self.user.email_verified_at)

    def test_selectors_helpers(self) -> None:
        self.assertEqual(get_user_by_pk(self.user.pk), self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.assertEqual(get_user_by_uidb64(uidb64), self.user)
        self.assertFalse(is_email_verified(self.user))
        self.user.verify_email()
        self.assertTrue(is_email_verified(self.user))

    def test_verify_email_token_service(self) -> None:
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        
        success, status, verified_user = verify_email_token(uidb64, token)
        self.assertTrue(success)
        self.assertEqual(status, "success")
        self.assertEqual(verified_user, self.user)
        self.user.refresh_from_db()
        self.assertTrue(is_email_verified(self.user))

        # Test already verified
        success_again, status_again, _ = verify_email_token(uidb64, token)
        self.assertTrue(success_again)
        self.assertEqual(status_again, "already_verified")

    def test_verify_email_token_invalid(self) -> None:
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        success, status, _ = verify_email_token(uidb64, "invalid-token")
        self.assertFalse(success)
        self.assertEqual(status, "invalid_token")


class TestEmailVerificationViews(TestCase):
    """Test email verification and resend verification views."""

    def setUp(self) -> None:
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email="patron_verify@houseofbore.com",
            password="SecurePassword123!",
            is_active=True,
        )
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)

    def test_verify_email_view_success(self) -> None:
        url = reverse("accounts:verify_email", kwargs={"uidb64": self.uidb64, "token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/email_verified.html")
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verify_email_view_already_verified(self) -> None:
        self.user.verify_email()
        url = reverse("accounts:verify_email", kwargs={"uidb64": self.uidb64, "token": self.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/email_verification_already.html")

    def test_verify_email_view_invalid_token(self) -> None:
        url = reverse("accounts:verify_email", kwargs={"uidb64": self.uidb64, "token": "bogus-token"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/email_verification_invalid.html")

    def test_resend_verification_view_unauthenticated(self) -> None:
        url = reverse("accounts:resend_verification")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_resend_verification_view_authenticated_post(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:resend_verification")
        response = self.client.post(url)
        self.assertRedirects(response, url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Please Verify Your Email Address", mail.outbox[0].subject)

    def test_resend_verification_view_authenticated_get_unverified(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:resend_verification")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/resend_verification.html")

    def test_resend_verification_view_authenticated_get_already_verified(self) -> None:
        self.user.verify_email()
        self.client.force_login(self.user)
        url = reverse("accounts:resend_verification")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/email_verification_already.html")

    def test_resend_verification_throttling(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:resend_verification")
        # First request sends email
        self.client.post(url)
        self.assertEqual(len(mail.outbox), 1)
        # Second immediate request is throttled
        response = self.client.post(url)
        self.assertRedirects(response, url)
        self.assertEqual(len(mail.outbox), 1)


class TestPasswordResetWorkflows(TestCase):
    """Test password reset form, email dispatch, and confirmation views."""

    def setUp(self) -> None:
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email="reset_patron@houseofbore.com",
            password="OldPassword123!",
            is_active=True,
        )

    def test_password_reset_form_valid_email(self) -> None:
        form = UserPasswordResetForm(data={"email": "reset_patron@houseofbore.com"})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Password Reset Request", mail.outbox[0].subject)

    def test_password_reset_form_unregistered_email(self) -> None:
        """Ensure no email is sent and no error is thrown for unknown emails (anti-enumeration)."""
        form = UserPasswordResetForm(data={"email": "unknown_patron@houseofbore.com"})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_view(self) -> None:
        url = reverse("accounts:password_reset")
        response = self.client.post(url, data={"email": "reset_patron@houseofbore.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_confirm_view_post(self) -> None:
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
        
        # Django redirects /reset/<uidb64>/<token>/ to /reset/<uidb64>/set-password/ to hide token from Referer
        get_res = self.client.get(url, follow=True)
        self.assertEqual(get_res.status_code, 200)
        
        post_url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": "set-password"})
        response = self.client.post(post_url, data={
            "new_password1": "NewSecurePassword456!",
            "new_password2": "NewSecurePassword456!",
        })
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecurePassword456!"))

    def test_password_reset_confirm_view_get_invalid_token(self) -> None:
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": "invalid-token"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/password_reset_confirm.html")
        self.assertFalse(response.context["validlink"])


class TestPasswordChangeWorkflows(TestCase):
    """Test authenticated password change workflows."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(
            email="change_patron@houseofbore.com",
            password="CurrentPassword123!",
        )

    def test_password_change_unauthenticated(self) -> None:
        url = reverse("accounts:password_change")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_password_change_success(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:password_change")
        response = self.client.post(url, data={
            "old_password": "CurrentPassword123!",
            "new_password1": "UpdatedPassword789!",
            "new_password2": "UpdatedPassword789!",
        })
        self.assertRedirects(response, reverse("core:home"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("UpdatedPassword789!"))
        # Ensure user remains logged in
        self.assertIn("_auth_user_id", self.client.session)


class TestRouteProtectionInfrastructure(TestCase):
    """Test decorators, mixins, and middleware for email verification enforcement."""

    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(
            email="unverified_patron@houseofbore.com",
            password="SecurePassword123!",
        )

    def test_verified_email_required_decorator(self) -> None:
        @verified_email_required
        def dummy_view(request):
            return HttpResponse("Access Granted")

        # Unauthenticated
        from django.test import RequestFactory
        factory = RequestFactory()
        req = factory.get("/protected/")
        req.user = unittest.mock.Mock(is_authenticated=False)
        res = dummy_view(req)
        self.assertEqual(res.status_code, 302)

        # Authenticated but unverified
        req.user = self.user
        req._messages = unittest.mock.Mock()
        res = dummy_view(req)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse("accounts:resend_verification"))

        # Authenticated and verified
        self.user.verify_email()
        res = dummy_view(req)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content.decode(), "Access Granted")


class TestUserProfileManagement(TestCase):
    """
    Comprehensive automated tests for Phase 3.4 — Customer Profile Management.
    """
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(
            email="patron_profile@houseofbore.com",
            password="SecurePassword123!",
        )
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(buf, format="GIF")
        self.valid_gif_data = buf.getvalue()

    def test_signal_creates_profile_on_user_registration(self) -> None:
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())
        profile = get_profile(self.user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.preferred_currency, "USD")
        self.assertEqual(profile.preferred_language, "en")

    def test_register_user_populates_phone(self) -> None:
        new_user = register_user(
            email="concierge_patron@houseofbore.com",
            password="SecurePassword123!",
            phone="+1 555 999 8888"
        )
        profile = get_profile(new_user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.phone_number, "+1 555 999 8888")

    def test_profile_completion_percentage_calculation(self) -> None:
        # Initially 0 out of 6 criteria (email unverified, no phone, no avatar, no dob)
        # But wait: preferred_language and preferred_currency have defaults!
        # So 2 out of 6 (33%) should be complete by default.
        initial_pct = profile_completion_percentage(self.user)
        self.assertEqual(initial_pct, 33)

        # Verify email -> 3/6 = 50%
        self.user.verify_email()
        self.assertEqual(profile_completion_percentage(self.user), 50)

        # Set phone & dob -> 5/6 = 83%
        update_profile(self.user, phone_number="+1 555 000 1111", date_of_birth="1985-06-15")
        self.assertEqual(profile_completion_percentage(self.user), 83)

        # Set avatar -> 6/6 = 100%
        avatar_file = SimpleUploadedFile("avatar.gif", self.valid_gif_data, content_type="image/gif")
        update_avatar(self.user, avatar_file)
        self.assertEqual(profile_completion_percentage(self.user), 100)

    def test_update_profile_service(self) -> None:
        profile = update_profile(
            self.user,
            phone_number="+33 1 23 45 67 89",
            preferred_language="fr",
            preferred_currency="EUR",
            marketing_emails=False
        )
        self.assertIsNotNone(profile)
        self.assertEqual(profile.phone_number, "+33 1 23 45 67 89")
        self.assertEqual(profile.preferred_language, "fr")
        self.assertEqual(profile.preferred_currency, "EUR")
        self.assertFalse(profile.marketing_emails)

    def test_avatar_upload_and_removal_service(self) -> None:
        avatar_file = SimpleUploadedFile("patron.gif", self.valid_gif_data, content_type="image/gif")
        success, msg = update_avatar(self.user, avatar_file)
        self.assertTrue(success)
        self.assertEqual(msg, "Avatar updated successfully.")

        profile = get_profile(self.user)
        self.assertTrue(bool(profile.avatar))

        # Remove avatar
        removed = remove_avatar(self.user)
        self.assertTrue(removed)
        profile.refresh_from_db()
        self.assertFalse(bool(profile.avatar))

    def test_avatar_upload_validation_errors(self) -> None:
        # Too large (> 2MB)
        huge_file = SimpleUploadedFile("huge.png", b"a" * (2 * 1024 * 1024 + 100), content_type="image/png")
        success, msg = update_avatar(self.user, huge_file)
        self.assertFalse(success)
        self.assertIn("too large", msg)

        # Invalid extension
        txt_file = SimpleUploadedFile("document.txt", b"not an image", content_type="text/plain")
        success, msg = update_avatar(self.user, txt_file)
        self.assertFalse(success)
        self.assertIn("Invalid image format", msg)

    def test_profile_views_unauthenticated_redirect(self) -> None:
        url_profile = reverse("accounts:profile")
        url_edit = reverse("accounts:profile_edit")
        
        res1 = self.client.get(url_profile)
        self.assertRedirects(res1, f"{reverse('accounts:login')}?next={url_profile}")

        res2 = self.client.get(url_edit)
        self.assertRedirects(res2, f"{reverse('accounts:login')}?next={url_edit}")

    def test_profile_overview_view_authenticated(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:profile")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "accounts/profile.html")
        self.assertIn("profile", res.context)
        self.assertIn("completion_percentage", res.context)

    def test_profile_edit_view_post_update_info(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:profile_edit")
        res = self.client.post(url, data={
            "action": "update_profile",
            "phone_number": "+44 20 7946 0999",
            "date_of_birth": "1990-01-01",
            "preferred_language": "it",
            "preferred_currency": "GBP",
            "marketing_emails": "on",
        })
        self.assertRedirects(res, reverse("accounts:profile"))
        
        profile = get_profile(self.user)
        profile.refresh_from_db()
        self.assertEqual(profile.phone_number, "+44 20 7946 0999")
        self.assertEqual(profile.preferred_language, "it")
        self.assertEqual(profile.preferred_currency, "GBP")
        self.assertTrue(profile.marketing_emails)

    def test_profile_edit_view_post_upload_and_remove_avatar(self) -> None:
        self.client.force_login(self.user)
        url = reverse("accounts:profile_edit")
        
        avatar_file = SimpleUploadedFile("test_avatar.gif", self.valid_gif_data, content_type="image/gif")
        res_upload = self.client.post(url, data={
            "action": "upload_avatar",
            "avatar": avatar_file,
        })
        self.assertRedirects(res_upload, reverse("accounts:profile_edit"))
        
        profile = get_profile(self.user)
        profile.refresh_from_db()
        self.assertTrue(bool(profile.avatar))

        res_remove = self.client.post(url, data={
            "action": "remove_avatar",
        })
        self.assertRedirects(res_remove, reverse("accounts:profile_edit"))
        
        profile.refresh_from_db()
        self.assertFalse(bool(profile.avatar))

    def test_admin_registration(self) -> None:
        from django.contrib import admin
        from accounts.admin import UserProfileInline
        self.assertIn(UserProfile, admin.site._registry)
        user_admin = admin.site._registry[User]
        self.assertIn(UserProfileInline, user_admin.inlines)

    def test_date_of_birth_future_validation(self) -> None:
        import datetime
        from django.utils import timezone
        future_date = timezone.now().date() + datetime.timedelta(days=10)
        
        form = ProfileUpdateForm(data={"date_of_birth": future_date.strftime("%Y-%m-%d")})
        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)
        self.assertIn("future", form.errors["date_of_birth"][0])

    def test_avatar_upload_corrupted_content_verification(self) -> None:
        fake_png = SimpleUploadedFile("fake.png", b"not a real png bitmap", content_type="image/png")
        success, msg = update_avatar(self.user, fake_png)
        self.assertFalse(success)
        self.assertIn("corrupted", msg)

    def test_get_profile_caching_efficiency(self) -> None:
        profile = get_profile(self.user)
        self.assertIsNotNone(profile)
        with self.assertNumQueries(0):
            cached_profile = get_profile(self.user)
            self.assertEqual(cached_profile, profile)


class TestAddressBookModels(TestCase):
    """Test Address model methods and default unsetting logic."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="address_model@houseofbore.com",
            password="SecurePassword123!",
            is_active=True,
        )

    def test_address_creation_and_str(self) -> None:
        address = Address.objects.create(
            user=self.user,
            label="Home",
            recipient_name="Lord Bore",
            phone_number="+1 555-0100",
            address_line_1="100 Luxury Way",
            city="Beverly Hills",
            county_or_state="CA",
            postal_code="90210",
            country="US",
        )
        self.assertIn("Home", str(address))
        self.assertIn("Beverly Hills", str(address))

    def test_formatted_address_property(self) -> None:
        address = Address.objects.create(
            user=self.user,
            label="Office",
            recipient_name="Executive Suite",
            company_name="Bore Industries",
            phone_number="+1 555-0101",
            address_line_1="500 Wall Street",
            address_line_2="Floor 40",
            city="New York",
            county_or_state="NY",
            postal_code="10005",
            country="US",
        )
        formatted = address.formatted_address
        self.assertIn("Executive Suite", formatted)
        self.assertIn("Bore Industries", formatted)
        self.assertIn("500 Wall Street", formatted)
        self.assertIn("Floor 40", formatted)
        self.assertIn("New York, NY 10005", formatted)
        self.assertIn("United States", formatted)

    def test_auto_unsetting_defaults_on_save(self) -> None:
        addr1 = Address.objects.create(
            user=self.user,
            label="Home",
            recipient_name="User",
            phone_number="+1 555-0100",
            address_line_1="1 Street",
            city="City",
            county_or_state="State",
            postal_code="10000",
            country="US",
            is_default_shipping=True,
            is_default_billing=True,
        )
        self.assertTrue(addr1.is_default_shipping)
        self.assertTrue(addr1.is_default_billing)

        addr2 = Address.objects.create(
            user=self.user,
            label="Work",
            recipient_name="User Work",
            phone_number="+1 555-0102",
            address_line_1="2 Street",
            city="City",
            county_or_state="State",
            postal_code="10000",
            country="US",
            is_default_shipping=True,
            is_default_billing=True,
        )
        addr1.refresh_from_db()
        self.assertFalse(addr1.is_default_shipping)
        self.assertFalse(addr1.is_default_billing)
        self.assertTrue(addr2.is_default_shipping)
        self.assertTrue(addr2.is_default_billing)


class TestAddressBookSelectors(TestCase):
    """Test read-only address queries and ownership isolation."""

    def setUp(self) -> None:
        self.user1 = User.objects.create_user(email="user1@houseofbore.com", password="pwd")
        self.user2 = User.objects.create_user(email="user2@houseofbore.com", password="pwd")
        self.addr1 = Address.objects.create(
            user=self.user1, label="Home", recipient_name="U1", phone_number="+1 555-0100",
            address_line_1="1 St", city="City", county_or_state="ST", country="US",
            is_default_shipping=True
        )
        self.addr2 = Address.objects.create(
            user=self.user2, label="Work", recipient_name="U2", phone_number="+1 555-0101",
            address_line_1="2 St", city="City", county_or_state="ST", country="US",
            is_default_billing=True
        )

    def test_get_user_addresses(self) -> None:
        u1_addrs = get_user_addresses(self.user1)
        self.assertEqual(u1_addrs.count(), 1)
        self.assertEqual(u1_addrs.first(), self.addr1)

        u2_addrs = get_user_addresses(self.user2)
        self.assertEqual(u2_addrs.count(), 1)
        self.assertEqual(u2_addrs.first(), self.addr2)

    def test_get_user_address_by_pk_ownership_isolation(self) -> None:
        self.assertIsNone(get_user_address_by_pk(self.user1, self.addr2.pk))
        self.assertEqual(get_user_address_by_pk(self.user1, self.addr1.pk), self.addr1)

    def test_get_default_shipping_and_billing(self) -> None:
        self.assertEqual(get_default_shipping(self.user1), self.addr1)
        self.assertIsNone(get_default_billing(self.user1))
        self.assertIsNone(get_default_shipping(self.user2))
        self.assertEqual(get_default_billing(self.user2), self.addr2)


class TestAddressBookServices(TestCase):
    """Test transactional CRUD services and default promotion."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(email="service_test@houseofbore.com", password="pwd")

    def test_create_address_auto_default_assignment(self) -> None:
        addr = create_address(
            user=self.user, label="First", recipient_name="Me", phone_number="+1 555-0100",
            address_line_1="1 St", city="City", county_or_state="ST", country="US",
            address_type="both"
        )
        self.assertTrue(addr.is_default_shipping)
        self.assertTrue(addr.is_default_billing)

    def test_delete_address_fallback_promotion(self) -> None:
        addr1 = create_address(
            user=self.user, label="First", recipient_name="Me", phone_number="+1 555-0100",
            address_line_1="1 St", city="City", county_or_state="ST", country="US",
            address_type="both"
        )
        addr2 = create_address(
            user=self.user, label="Second", recipient_name="Me", phone_number="+1 555-0100",
            address_line_1="2 St", city="City", county_or_state="ST", country="US",
            address_type="both", is_default_shipping=False, is_default_billing=False
        )
        self.assertTrue(addr1.is_default_shipping)
        self.assertFalse(addr2.is_default_shipping)

        delete_address(addr1)
        addr2.refresh_from_db()
        self.assertTrue(addr2.is_default_shipping)
        self.assertTrue(addr2.is_default_billing)

    def test_set_default_shipping_modifies_billing_only(self) -> None:
        addr = create_address(
            user=self.user, label="Billing", recipient_name="Me", phone_number="+1 555-0100",
            address_line_1="1 St", city="City", county_or_state="ST", country="US",
            address_type="billing"
        )
        self.assertEqual(addr.address_type, "billing")
        set_default_shipping(addr)
        addr.refresh_from_db()
        self.assertEqual(addr.address_type, "both")
        self.assertTrue(addr.is_default_shipping)

    def test_format_address_service(self) -> None:
        addr = create_address(
            user=self.user, label="Home", recipient_name="Lord Bore", phone_number="+1 555-0100",
            address_line_1="100 Luxury Way", city="Beverly Hills", county_or_state="CA", country="US"
        )
        html_formatted = format_address(addr, html=True)
        self.assertIn("<br>", html_formatted)
        self.assertIn("Lord Bore", html_formatted)
        plain_formatted = format_address(addr, html=False)
        self.assertNotIn("<br>", plain_formatted)


class TestAddressBookForm(TestCase):
    """Test AddressForm validation and international country choices."""

    def test_valid_address_form(self) -> None:
        form = AddressForm(data={
            "label": "Home",
            "recipient_name": "John Doe",
            "phone_number": "+1 (555) 019-9888",
            "address_line_1": "123 Main St",
            "city": "Austin",
            "county_or_state": "TX",
            "postal_code": "78701",
            "country": "US",
            "address_type": "both",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_phone_number_format(self) -> None:
        form = AddressForm(data={
            "label": "Home",
            "recipient_name": "John Doe",
            "phone_number": "invalid-phone-str",
            "address_line_1": "123 Main St",
            "city": "Austin",
            "county_or_state": "TX",
            "postal_code": "78701",
            "country": "US",
            "address_type": "both",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("phone_number", form.errors)

    def test_postal_code_required_for_certain_countries(self) -> None:
        form = AddressForm(data={
            "label": "Home",
            "recipient_name": "John Doe",
            "phone_number": "+1 555-0199",
            "address_line_1": "123 Main St",
            "city": "Austin",
            "county_or_state": "TX",
            "postal_code": "",
            "country": "US",
            "address_type": "both",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("postal_code", form.errors)


class TestAddressBookViews(TestCase):
    """Test Class-Based Views, routing, permissions, and flash messages."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(email="view_user@houseofbore.com", password="pwd")
        self.other_user = User.objects.create_user(email="other_user@houseofbore.com", password="pwd")
        self.address = create_address(
            user=self.user, label="Home", recipient_name="View User", phone_number="+1 555-0100",
            address_line_1="1 St", city="City", county_or_state="ST", country="US"
        )
        self.list_url = reverse("accounts:address_list")
        self.create_url = reverse("accounts:address_create")
        self.edit_url = reverse("accounts:address_edit", args=[self.address.pk])
        self.delete_url = reverse("accounts:address_delete", args=[self.address.pk])
        self.set_default_url = reverse("accounts:address_set_default", args=[self.address.pk, "shipping"])

    def test_anonymous_redirects(self) -> None:
        for url in [self.list_url, self.create_url, self.edit_url, self.delete_url]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response.url)

    def test_address_list_view_authenticated(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Address Book")
        self.assertContains(response, "Home")
        self.assertEqual(response.context["active_nav"], "addresses")

    def test_address_create_view_post(self) -> None:
        self.client.force_login(self.user)
        response = self.client.post(self.create_url, data={
            "label": "Vacation Home",
            "recipient_name": "View User",
            "phone_number": "+1 555-0199",
            "address_line_1": "777 Beach Blvd",
            "city": "Miami",
            "county_or_state": "FL",
            "postal_code": "33101",
            "country": "US",
            "address_type": "shipping",
        })
        self.assertRedirects(response, self.list_url)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 2)

    def test_address_edit_view_other_user_404(self) -> None:
        self.client.force_login(self.other_user)
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 404)

    def test_address_delete_view_post(self) -> None:
        self.client.force_login(self.user)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, self.list_url)
        self.assertEqual(Address.objects.filter(user=self.user).count(), 0)

    def test_address_set_default_view_post(self) -> None:
        self.client.force_login(self.user)
        self.address.is_default_shipping = False
        self.address.save()
        response = self.client.post(self.set_default_url)
        self.assertRedirects(response, self.list_url)
        self.address.refresh_from_db()
        self.assertTrue(self.address.is_default_shipping)


class TestSecuritySelectorsAndServices(TestCase):
    """Test security selectors and services in Phase 3.6."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="security@houseofbore.com",
            password="SecurePassword123!",
            first_name="Security",
            last_name="Patron"
        )
        self.other_user = User.objects.create_user(
            email="other@houseofbore.com",
            password="OtherPassword123!"
        )

    def test_log_account_activity(self) -> None:
        log_account_activity(self.user, "login", details={"browser": "Chrome"})
        activity = get_recent_activity(self.user)
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity[0].event_type, "login")
        self.assertEqual(activity[0].details["browser"], "Chrome")

    def test_track_and_get_active_sessions(self) -> None:
        from django.utils import timezone
        from datetime import timedelta
        expire_date = timezone.now() + timedelta(days=365)
        session = Session.objects.create(session_key="testkey123", expire_date=expire_date)
        request = unittest.mock.MagicMock()
        request.session = session
        request.META = {"HTTP_USER_AGENT": "Mozilla/5.0", "REMOTE_ADDR": "127.0.0.1"}

        user_session = track_user_session(request, self.user)
        self.assertIsNotNone(user_session)
        self.assertEqual(user_session.session_key, "testkey123")

        active = get_active_sessions(self.user)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].session_key, "testkey123")

    def test_request_and_verify_email_change(self) -> None:
        pending = request_email_change(self.user, "newemail@houseofbore.com", "SecurePassword123!")
        self.assertEqual(pending.new_email, "newemail@houseofbore.com")
        self.assertEqual(pending_email_change(self.user), pending)

        success, user, msg = verify_email_change(pending.token)
        self.assertTrue(success)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newemail@houseofbore.com")
        self.assertIsNone(pending_email_change(self.user))

    def test_request_email_change_wrong_password(self) -> None:
        with self.assertRaises(Exception):
            request_email_change(self.user, "newemail@houseofbore.com", "WrongPassword!")

    def test_verify_email_change_expired(self) -> None:
        from django.utils import timezone
        from datetime import timedelta
        pending = request_email_change(self.user, "expire@houseofbore.com", "SecurePassword123!")
        self.assertIsNotNone(pending.expires_at)
        # Simulate expiration by setting created_at to 25 hours ago
        PendingEmailChange.objects.filter(pk=pending.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        pending.refresh_from_db()
        self.assertTrue(pending.is_expired)
        success, user, msg = verify_email_change(pending.token)
        self.assertFalse(success)
        self.assertIn("expired", msg.lower())

    def test_revoke_session(self) -> None:
        from django.utils import timezone
        from datetime import timedelta
        expire_date = timezone.now() + timedelta(days=365)
        session = Session.objects.create(session_key="tokill123", expire_date=expire_date)
        UserSession.objects.create(user=self.user, session=session, session_key="tokill123")
        res = revoke_session(self.user, "tokill123")
        self.assertTrue(res)
        self.assertFalse(Session.objects.filter(session_key="tokill123").exists())

    def test_deactivate_account(self) -> None:
        deactivate_account(self.user, "SecurePassword123!")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_delete_account(self) -> None:
        delete_account(self.user, "SecurePassword123!", "DELETE MY ACCOUNT")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        profile = get_profile(self.user)
        if profile:
            self.assertEqual(profile.phone_number, "")


class TestSecurityForms(TestCase):
    """Test security forms in Phase 3.6."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="formsec@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_email_change_form_valid(self) -> None:
        form = EmailChangeForm(data={
            "new_email": "updated@houseofbore.com",
            "password": "SecurePassword123!"
        }, user=self.user)
        self.assertTrue(form.is_valid())

    def test_email_change_form_invalid_password(self) -> None:
        form = EmailChangeForm(data={
            "new_email": "updated@houseofbore.com",
            "password": "WrongPassword!"
        }, user=self.user)
        self.assertFalse(form.is_valid())

    def test_delete_form_invalid_phrase(self) -> None:
        form = AccountDeleteForm(data={
            "password": "SecurePassword123!",
            "confirmation_phrase": "WRONG PHRASE"
        }, user=self.user)
        self.assertFalse(form.is_valid())


class TestSecurityViews(TestCase):
    """Test security Class-Based Views in Phase 3.6."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="viewsec@houseofbore.com",
            password="SecurePassword123!"
        )
        self.settings_url = reverse("accounts:settings")
        self.sessions_url = reverse("accounts:sessions")
        self.email_change_url = reverse("accounts:email_change")
        self.deactivate_url = reverse("accounts:deactivate")
        self.delete_url = reverse("accounts:delete")

    def test_settings_view_requires_login(self) -> None:
        response = self.client.get(self.settings_url)
        self.assertNotEqual(response.status_code, 200)

    def test_settings_view_logged_in(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/settings.html")

    def test_sessions_view_logged_in(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(self.sessions_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/sessions.html")

    def test_email_change_view_post_success(self) -> None:
        self.client.force_login(self.user)
        response = self.client.post(self.email_change_url, {
            "new_email": "changed@houseofbore.com",
            "password": "SecurePassword123!"
        })
        self.assertRedirects(response, self.settings_url)
        self.assertIsNotNone(pending_email_change(self.user))

    def test_deactivate_view_post_success(self) -> None:
        self.client.force_login(self.user)
        response = self.client.post(self.deactivate_url, {
            "password": "SecurePassword123!"
        })
        self.assertRedirects(response, reverse("core:home"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_session_revoke_view_post(self) -> None:
        from django.utils import timezone
        from datetime import timedelta
        self.client.force_login(self.user)
        expire_date = timezone.now() + timedelta(days=365)
        session = Session.objects.create(session_key="viewkill123", expire_date=expire_date)
        UserSession.objects.create(user=self.user, session=session, session_key="viewkill123")
        revoke_url = reverse("accounts:session_revoke", kwargs={"session_key": "viewkill123"})
        response = self.client.post(revoke_url)
        self.assertRedirects(response, self.sessions_url)
        self.assertFalse(Session.objects.filter(session_key="viewkill123").exists())

    def test_session_revoke_others_view_post(self) -> None:
        from django.utils import timezone
        from datetime import timedelta
        self.client.force_login(self.user)
        expire_date = timezone.now() + timedelta(days=365)
        s1 = Session.objects.create(session_key="other1", expire_date=expire_date)
        s2 = Session.objects.create(session_key="other2", expire_date=expire_date)
        UserSession.objects.create(user=self.user, session=s1, session_key="other1")
        UserSession.objects.create(user=self.user, session=s2, session_key="other2")
        revoke_others_url = reverse("accounts:session_revoke_others")
        response = self.client.post(revoke_others_url)
        self.assertRedirects(response, self.sessions_url)
        # Other sessions should be deleted (except the client's current session if tracked)
        self.assertFalse(Session.objects.filter(session_key__in=["other1", "other2"]).exists())


class TestAuthenticationThrottling(TestCase):
    """
    Test rate limiting and throttling on authentication endpoints.
    """
    def setUp(self) -> None:
        from django.core.cache import cache
        cache.clear()
        self.login_url = reverse("accounts:login")

    def tearDown(self) -> None:
        from django.core.cache import cache
        cache.clear()

    def test_login_throttling_after_max_attempts(self) -> None:
        # Perform 10 failed login attempts
        for _ in range(10):
            response = self.client.post(self.login_url, {
                "email": "nonexistent@houseofbore.com",
                "password": "WrongPassword123!"
            })
            self.assertEqual(response.status_code, 200)

        # 11th attempt should trigger throttling warning
        response = self.client.post(self.login_url, {
            "email": "nonexistent@houseofbore.com",
            "password": "WrongPassword123!"
        })
        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context["messages"])
        self.assertTrue(any("Too many unsuccessful attempts" in str(m) for m in messages_list))


