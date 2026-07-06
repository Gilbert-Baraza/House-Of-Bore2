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
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from accounts.backends import EmailAuthenticationBackend
from accounts.forms import UserLoginForm, UserRegistrationForm
from accounts.selectors import email_exists, get_user_by_email, username_exists
from accounts.services import _get_absolute_url, register_user, send_verification_email, send_welcome_email

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

    def test_verify_email_placeholder_redirects(self) -> None:
        verify_url = reverse("accounts:verify_email", kwargs={"uidb64": "testuid", "token": "testtoken"})
        response = self.client.get(verify_url)
        self.assertRedirects(response, self.success_url)

    def test_resend_verification_placeholder_redirects(self) -> None:
        resend_url = reverse("accounts:resend_verification")
        response = self.client.get(resend_url)
        self.assertRedirects(response, self.success_url)


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
