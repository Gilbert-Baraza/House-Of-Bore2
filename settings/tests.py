# settings/tests.py
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.http import HttpResponse

from settings.models import StoreSettings
from settings.selectors import (
    get_store_settings,
    is_feature_enabled,
    is_maintenance_mode_enabled,
    get_branding_context,
    get_seo_defaults,
    get_social_links,
)
from settings.services import update_store_settings, update_store_file_asset
from settings.middleware import MaintenanceModeMiddleware
from dashboard.models import StaffRole

User = get_user_model()


class StoreSettingsModelTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_singleton_load(self):
        """Verify load() returns or creates exactly one StoreSettings instance with pk=1."""
        settings_1 = StoreSettings.load()
        self.assertEqual(settings_1.pk, 1)
        self.assertEqual(StoreSettings.objects.count(), 1)

        settings_2 = StoreSettings.load()
        self.assertEqual(settings_1, settings_2)
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_cache_cleared_on_save(self):
        """Verify saving StoreSettings clears the singleton cache."""
        settings = StoreSettings.load()
        cached = cache.get(StoreSettings.CACHE_KEY)
        self.assertIsNotNone(cached)

        settings.store_name = "New House of Bore"
        settings.save()

        # Cache should be cleared on save, so cache.get returns None until next load()
        self.assertIsNone(cache.get(StoreSettings.CACHE_KEY))
        loaded = StoreSettings.load()
        self.assertEqual(loaded.store_name, "New House of Bore")

    def test_string_representation(self):
        settings = StoreSettings.load()
        settings.store_name = "House of Bore Luxury"
        settings.save()
        self.assertEqual(str(settings), "Store Settings (House of Bore Luxury)")


class StoreSettingsSelectorsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = StoreSettings.load()

    def test_get_store_settings(self):
        s = get_store_settings()
        self.assertEqual(s.pk, 1)

    def test_is_feature_enabled(self):
        self.settings.feature_wishlist = True
        self.settings.feature_reviews = False
        self.settings.save()

        self.assertTrue(is_feature_enabled("feature_wishlist"))
        self.assertFalse(is_feature_enabled("feature_reviews"))
        self.assertFalse(is_feature_enabled("non_existent_feature"))

    def test_is_maintenance_mode_enabled(self):
        self.settings.maintenance_mode_enabled = False
        self.settings.save()
        self.assertFalse(is_maintenance_mode_enabled())

        self.settings.maintenance_mode_enabled = True
        self.settings.save()
        self.assertTrue(is_maintenance_mode_enabled())

    def test_get_branding_context(self):
        self.settings.primary_color = "#111111"
        self.settings.accent_color = "#FFD700"
        self.settings.save()

        context = get_branding_context()
        self.assertEqual(context["primary_color"], "#111111")
        self.assertEqual(context["accent_color"], "#FFD700")

    def test_get_seo_defaults_and_social_links(self):
        self.settings.default_meta_title = "House of Bore Store"
        self.settings.instagram_url = "https://instagram.com/houseofbore"
        self.settings.save()

        seo = get_seo_defaults()
        self.assertEqual(seo["default_meta_title"], "House of Bore Store")

        social = get_social_links()
        self.assertEqual(social["instagram_url"], "https://instagram.com/houseofbore")

    def test_context_processor_single_lookup(self):
        from settings.context_processors import store_settings
        from django.test import RequestFactory
        from unittest.mock import patch
        rf = RequestFactory()
        req = rf.get("/")
        # Ensure cached
        StoreSettings.load()
        with patch.object(StoreSettings, "load", wraps=StoreSettings.load) as mock_load:
            ctx = store_settings(req)
            self.assertIn("store_settings", ctx)
            self.assertIn("branding", ctx)
            self.assertIn("feature_flags", ctx)
            self.assertIn("currency_settings", ctx)
            # Must only call load once per context processor invocation
            mock_load.assert_called_once()

    def test_maintenance_allowlist_paths(self):
        from django.test import RequestFactory
        rf = RequestFactory()
        self.settings.maintenance_mode_enabled = True
        self.settings.save()

        # Regular storefront path -> maintenance enabled
        req_store = rf.get("/products/trench-coat")
        self.assertTrue(is_maintenance_mode_enabled(req_store))

        # Allowlisted API / health paths -> maintenance NOT enabled
        req_api = rf.get("/api/v1/products/")
        self.assertFalse(is_maintenance_mode_enabled(req_api))
        req_health = rf.get("/health/")
        self.assertFalse(is_maintenance_mode_enabled(req_health))


class StoreSettingsServicesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="admin@houseofbore.com",
            password="securepassword123",
            is_staff=True,
            is_superuser=True,
        )

    def test_update_store_settings(self):
        updated = update_store_settings(
            user=self.user,
            section_name="profile",
            store_name="House of Bore Flagship",
            tax_percentage="16.00",
        )
        self.assertEqual(updated.store_name, "House of Bore Flagship")
        self.assertEqual(str(updated.tax_percentage), "16.00")

    def test_update_store_file_asset(self):
        test_file = SimpleUploadedFile("logo.png", b"file_content", content_type="image/png")
        updated = update_store_file_asset(
            user=self.user,
            field_name="logo",
            file_obj=test_file,
        )
        self.assertTrue(bool(updated.logo))


class StoreSettingsMiddlewareTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.get_response = lambda request: HttpResponse("Normal Storefront Response", status=200)
        self.middleware = MaintenanceModeMiddleware(self.get_response)
        self.settings = StoreSettings.load()
        self.user = User.objects.create_user(
            email="staff@houseofbore.com",
            password="securepassword123",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email="customer@houseofbore.com",
            password="securepassword123",
            is_staff=False,
        )

    def test_middleware_bypasses_when_disabled(self):
        self.settings.maintenance_mode_enabled = False
        self.settings.save()

        request = self.factory.get("/")
        request.user = self.customer
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_middleware_blocks_customer_when_enabled(self):
        self.settings.maintenance_mode_enabled = True
        self.settings.save()

        request = self.factory.get("/")
        request.user = self.customer
        response = self.middleware(request)
        self.assertEqual(response.status_code, 503)

    def test_middleware_bypasses_staff_and_admin_paths(self):
        self.settings.maintenance_mode_enabled = True
        self.settings.save()

        # Staff user accessing normal path
        request = self.factory.get("/")
        request.user = self.user
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

        # Admin URL accessed by anonymous or anyone
        request_admin = self.factory.get("/admin/login/")
        request_admin.user = self.customer
        response_admin = self.middleware(request_admin)
        self.assertEqual(response_admin.status_code, 200)

        # Dashboard URL accessed
        request_dash = self.factory.get("/dashboard/")
        request_dash.user = self.customer
        response_dash = self.middleware(request_dash)
        self.assertEqual(response_dash.status_code, 200)


class StoreSettingsViewsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.settings = StoreSettings.load()

        # Create staff user with store_manager role
        self.manager = User.objects.create_user(
            email="manager@houseofbore.com",
            password="securepassword123",
            is_staff=True,
        )
        self.role_manager, _ = StaffRole.objects.get_or_create(
            code="store_manager",
            defaults={"name": "Store Manager", "description": "Store Manager Role"},
        )
        self.role_manager.permissions = ["settings.view_storesettings", "settings.change_storesettings"]
        self.role_manager.save()
        self.role_manager.users.add(self.manager)

        # Create staff user without settings permissions
        self.staff_no_perm = User.objects.create_user(
            email="staffnoperm@houseofbore.com",
            password="securepassword123",
            is_staff=True,
        )
        self.role_basic, _ = StaffRole.objects.get_or_create(
            code="customer_service",
            defaults={"name": "Customer Service", "description": "CS Role"},
        )
        self.role_basic.permissions = ["orders.view_orders"]
        self.role_basic.save()
        self.role_basic.users.add(self.staff_no_perm)

    def test_overview_view_access(self):
        # Unauthenticated redirect
        response = self.client.get(reverse("dashboard:settings:overview"))
        self.assertEqual(response.status_code, 302)

        # Authenticated manager can view
        self.client.force_login(self.manager)
        response = self.client.get(reverse("dashboard:settings:overview"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/settings/dashboard.html")

    def test_section_view_post_updates_settings(self):
        self.client.force_login(self.manager)
        url = reverse("dashboard:settings:profile")
        response = self.client.post(url, {
            "store_name": "Updated House of Bore",
            "business_name": "House of Bore Inc.",
            "store_description": "Updated description",
            "email": "contact@houseofbore.com",
            "phone": "+254700000000",
            "whatsapp": "+254700000000",
            "physical_address": "Nairobi, Kenya",
            "business_hours": "Mon-Fri 9AM-5PM",
        })
        self.assertRedirects(response, url)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.store_name, "Updated House of Bore")

    def test_permission_denied_without_manage_permission(self):
        self.client.force_login(self.staff_no_perm)
        response = self.client.get(reverse("dashboard:settings:profile"))
        # Should deny access based on permission check
        self.assertEqual(response.status_code, 403)
