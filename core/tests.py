# core/tests.py
"""
Tests for core application views, URL resolution, and forms.
"""

from django.test import Client, TestCase
from django.urls import resolve, reverse
from core.forms import ContactForm
from core.views import AboutView, ContactView, HomeView


class CoreURLResolutionTests(TestCase):
    """
    Tests that core URL names resolve to the correct class-based views.
    """

    def test_home_url_resolves_to_home_view(self):
        url = reverse("core:home")
        self.assertEqual(resolve(url).func.view_class, HomeView)

    def test_about_url_resolves_to_about_view(self):
        url = reverse("core:about")
        self.assertEqual(resolve(url).func.view_class, AboutView)

    def test_contact_url_resolves_to_contact_view(self):
        url = reverse("core:contact")
        self.assertEqual(resolve(url).func.view_class, ContactView)


class CoreViewResponseTests(TestCase):
    """
    Tests view HTTP status codes and template usage.
    """

    def setUp(self):
        self.client = Client()

    def test_home_view_status_code_and_templates(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "components/category_card.html")
        self.assertTemplateUsed(response, "components/feature_card.html")
        self.assertTemplateUsed(response, "components/product_card_preview.html")
        self.assertTemplateUsed(response, "components/promo_banner.html")
        self.assertTemplateUsed(response, "components/testimonial_card.html")
        self.assertTemplateUsed(response, "components/newsletter_section.html")

    def test_about_view_status_code_and_templates(self):
        response = self.client.get(reverse("core:about"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/about.html")
        self.assertTemplateUsed(response, "base.html")

    def test_contact_view_status_code_and_templates(self):
        response = self.client.get(reverse("core:contact"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/contact.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertIsInstance(response.context["form"], ContactForm)


class ContactFormTests(TestCase):
    """
    Tests contact form validation and submission handling.
    """

    def setUp(self):
        self.client = Client()
        self.url = reverse("core:contact")

    def test_contact_form_valid_submission(self):
        valid_data = {
            "name": "Eleanor Vance",
            "email": "eleanor@houseofbore.com",
            "subject": "order",
            "message": "I would like to inquire about shipping times to Paris.",
        }
        response = self.client.post(self.url, data=valid_data, follow=True)
        # Check redirect on success
        self.assertEqual(response.status_code, 200)
        # Check success message
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Thank you, Eleanor Vance", str(messages[0]))

    def test_contact_form_invalid_submission(self):
        # Missing required email and message
        invalid_data = {
            "name": "",
            "email": "not-an-email",
            "subject": "",
            "message": "",
        }
        response = self.client.post(self.url, data=invalid_data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.errors)
        self.assertIn("name", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("subject", form.errors)
        self.assertIn("message", form.errors)
