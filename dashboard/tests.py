# dashboard/tests.py
"""
dashboard/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive unit and integration test suite for the Custom Administration
Dashboard and Role-Based Access Control (RBAC) subsystem.

Covers:
1. Staff and Role access checks (`@staff_required`, `@role_required`, mixins).
2. Individual Role verification (Super Admin, Store Manager, Inventory Manager, etc.).
3. Unauthorized and guest access denial (`/dashboard/access-denied/`, 403 status).
4. Dashboard KPI Selectors (`revenue_today`, `orders_today`, `pending_orders`, etc.).
5. Services (`dashboard_statistics`, `staff_notifications`, `assign_role`, profile updates).
6. Audit Log foundation (`log_action`, `log_login`, `log_create`, `log_update`, `log_delete`).
7. Views & Navigation responses (`DashboardHomeView`, `StaffProfileView`, etc.).
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View

from accounts.models import UserProfile
from orders.models import Order, OrderStatus, PaymentStatus
from products.models import Category, Product, ProductImage
from .models import AuditLog, StaffPreference, StaffRole
from .permissions import (
    DashboardPermissionRequiredMixin,
    RoleRequiredMixin,
    StaffRequiredMixin,
    dashboard_permission_required,
    has_dashboard_permission,
    has_role,
    role_required,
    staff_required,
)
from .selectors import (
    average_order_value,
    new_customers,
    orders_today,
    pending_orders,
    processing_orders,
    recent_activity,
    recent_orders,
    revenue_today,
    total_customers,
    total_products,
)
from .services import (
    assign_role,
    create_audit_log,
    dashboard_statistics,
    ensure_default_roles,
    get_dashboard_summary,
    log_action,
    log_create,
    log_delete,
    log_login,
    log_logout,
    log_update,
    staff_notifications,
    update_staff_contact,
    update_staff_preferences,
)

User = get_user_model()


class DashboardRBACTestCase(TestCase):
    """Test suite for Role-Based Access Control permissions and decorators."""

    def setUp(self):
        self.factory = RequestFactory()
        # Ensure default roles exist
        ensure_default_roles()

        # Create guest user
        self.guest = User.objects.create_user(email="guest@houseofbore.com", password="password123")
        self.guest.is_staff = False
        self.guest.save()

        # Create superuser
        self.superuser = User.objects.create_superuser(email="super@houseofbore.com", password="password123")

        # Create staff users with different roles
        self.store_mgr = User.objects.create_user(email="store.mgr@houseofbore.com", password="password123")
        assign_role(self.store_mgr, "store_manager")

        self.inv_mgr = User.objects.create_user(email="inv.mgr@houseofbore.com", password="password123")
        assign_role(self.inv_mgr, "inventory_manager")

        self.sales_mgr = User.objects.create_user(email="sales.mgr@houseofbore.com", password="password123")
        assign_role(self.sales_mgr, "sales_manager")

        self.support_mgr = User.objects.create_user(email="support.mgr@houseofbore.com", password="password123")
        assign_role(self.support_mgr, "customer_support")

        self.marketing_mgr = User.objects.create_user(email="marketing.mgr@houseofbore.com", password="password123")
        assign_role(self.marketing_mgr, "marketing_manager")

        self.content_mgr = User.objects.create_user(email="content.mgr@houseofbore.com", password="password123")
        assign_role(self.content_mgr, "content_manager")

    def test_ensure_default_roles_creation(self):
        """Verify all 8 default staff roles are initialized."""
        self.assertEqual(StaffRole.objects.count(), 8)
        self.assertTrue(StaffRole.objects.filter(code="store_manager").exists())
        self.assertTrue(StaffRole.objects.filter(code="inventory_manager").exists())
        self.assertTrue(StaffRole.objects.filter(code="fulfillment_manager").exists())

    def test_has_role_helper(self):
        """Test has_role function behavior with single and list arguments."""
        self.assertFalse(has_role(self.guest, "store_manager"))
        self.assertTrue(has_role(self.superuser, "store_manager"))  # Superuser bypasses
        self.assertTrue(has_role(self.store_mgr, "store_manager"))
        self.assertFalse(has_role(self.inv_mgr, "store_manager"))
        self.assertTrue(has_role(self.inv_mgr, ["store_manager", "inventory_manager"]))

    def test_has_dashboard_permission_helper(self):
        """Test application-level permission string checks across roles."""
        self.assertFalse(has_dashboard_permission(self.guest, "orders.view_order"))
        self.assertTrue(has_dashboard_permission(self.superuser, "orders.view_order"))
        self.assertTrue(has_dashboard_permission(self.store_mgr, "orders.view_order"))
        self.assertTrue(has_dashboard_permission(self.store_mgr, "products.change_product"))
        self.assertTrue(has_dashboard_permission(self.inv_mgr, "inventory.change_inventory"))
        self.assertFalse(has_dashboard_permission(self.inv_mgr, "orders.change_order"))
        self.assertTrue(has_dashboard_permission(self.sales_mgr, "pricing.change_pricing"))
        self.assertTrue(has_dashboard_permission(self.support_mgr, "reviews.change_review"))
        self.assertTrue(has_dashboard_permission(self.marketing_mgr, "dashboard.view_marketing"))
        self.assertTrue(has_dashboard_permission(self.content_mgr, "products.add_product"))

    def test_staff_required_decorator(self):
        """Verify @staff_required decorator redirection and access rejection."""
        @staff_required
        def dummy_view(request):
            return HttpResponse("OK")

        # Unauthenticated request redirects to login
        req_anon = self.factory.get("/dashboard/")
        req_anon.user = self.factory.user_class() if hasattr(self.factory, "user_class") else None
        from django.contrib.auth.models import AnonymousUser
        req_anon.user = AnonymousUser()
        resp_anon = dummy_view(req_anon)
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp_anon.url)

        # Non-staff guest request returns 403 access denied
        req_guest = self.factory.get("/dashboard/")
        req_guest.user = self.guest
        resp_guest = dummy_view(req_guest)
        self.assertEqual(resp_guest.status_code, 403)

        # Staff user request succeeds
        req_staff = self.factory.get("/dashboard/")
        req_staff.user = self.store_mgr
        resp_staff = dummy_view(req_staff)
        self.assertEqual(resp_staff.status_code, 200)
        self.assertEqual(resp_staff.content, b"OK")

    def test_role_required_decorator(self):
        """Verify @role_required decorator enforces specific role boundaries."""
        @role_required("store_manager", "inventory_manager")
        def restricted_view(request):
            return HttpResponse("Authorized")

        req = self.factory.get("/dashboard/inventory/")
        req.user = self.sales_mgr
        self.assertEqual(restricted_view(req).status_code, 403)

        req.user = self.inv_mgr
        self.assertEqual(restricted_view(req).status_code, 200)

    def test_dashboard_permission_required_decorator(self):
        """Verify @dashboard_permission_required decorator."""
        @dashboard_permission_required("pricing.change_pricing")
        def pricing_view(request):
            return HttpResponse("Pricing")

        req = self.factory.get("/dashboard/marketing/")
        req.user = self.inv_mgr
        self.assertEqual(pricing_view(req).status_code, 403)

        req.user = self.marketing_mgr
        self.assertEqual(pricing_view(req).status_code, 200)

    def test_role_mixins(self):
        """Verify class-based RoleRequiredMixin behavior."""
        class DummyRoleView(RoleRequiredMixin, View):
            required_roles = ["store_manager"]
            def get(self, request, *args, **kwargs):
                return HttpResponse("Mixin OK")

        view = DummyRoleView.as_view()
        req_anon = self.factory.get("/")
        from django.contrib.auth.models import AnonymousUser
        req_anon.user = AnonymousUser()
        self.assertEqual(view(req_anon).status_code, 302)

        req_guest = self.factory.get("/")
        req_guest.user = self.guest
        self.assertEqual(view(req_guest).status_code, 403)

        req_inv = self.factory.get("/")
        req_inv.user = self.inv_mgr
        self.assertEqual(view(req_inv).status_code, 403)

        req_store = self.factory.get("/")
        req_store.user = self.store_mgr
        self.assertEqual(view(req_store).status_code, 200)


class DashboardSelectorsAndServicesTestCase(TestCase):
    """Test suite for data selectors, KPI aggregations, and audit logging."""

    def setUp(self):
        self.staff_user = User.objects.create_user(email="staff@houseofbore.com", password="password123")
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.customer = User.objects.create_user(email="patron@houseofbore.com", password="password123")
        self.customer.is_staff = False
        self.customer.save()

        # Create category and products
        self.category = Category.objects.create(name="Coats", slug="coats")
        self.p1 = Product.objects.create(
            name="Trench Coat", slug="trench-coat", short_description="Trench",
            description="Luxury Trench Coat", category=self.category, price=Decimal("250.00")
        )
        self.p2 = Product.objects.create(
            name="Silk Scarf", slug="silk-scarf", short_description="Scarf",
            description="Luxury Silk Scarf", category=self.category, price=Decimal("120.00")
        )

        # Create Orders
        self.o1 = Order.objects.create(
            order_number="HOB-2026-001", user=self.customer,
            status=OrderStatus.PENDING, payment_status=PaymentStatus.AWAITING_PAYMENT,
            subtotal=Decimal("100.00"), grand_total=Decimal("100.00")
        )
        self.o2 = Order.objects.create(
            order_number="HOB-2026-002", user=self.customer,
            status=OrderStatus.PROCESSING, payment_status=PaymentStatus.PAID,
            subtotal=Decimal("500.00"), grand_total=Decimal("500.00")
        )
        self.o3 = Order.objects.create(
            order_number="HOB-2026-003", user=self.customer,
            status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID,
            subtotal=Decimal("300.00"), grand_total=Decimal("300.00")
        )

    def test_selectors_queries(self):
        """Verify accurate query results for all dashboard KPI selectors."""
        self.assertEqual(revenue_today(), Decimal("800.00"))  # o2 + o3 paid today
        self.assertEqual(orders_today(), 3)
        self.assertEqual(pending_orders().count(), 1)
        self.assertEqual(processing_orders().count(), 1)
        self.assertEqual(total_products(), 2)
        self.assertEqual(total_customers(), 1)
        self.assertEqual(average_order_value(), Decimal("400.00"))  # (500 + 300) / 2
        self.assertEqual(recent_orders().count(), 3)
        self.assertEqual(new_customers().count(), 1)

    def test_audit_logging_services(self):
        """Verify all audit logging helpers create proper immutable entries."""
        log_login(self.staff_user, ip_address="127.0.0.1", user_agent="Mozilla/5.0")
        log_create(self.staff_user, self.p1, description="Created Trench Coat")
        log_update(self.staff_user, self.o2, description="Marked Order Paid")
        log_delete(self.staff_user, self.p2, description="Deleted Silk Scarf")
        log_logout(self.staff_user)
        log_action(self.staff_user, "EXPORT", "Exported monthly orders report", model_name="Order")

        self.assertEqual(AuditLog.objects.count(), 6)
        recent = recent_activity(limit=10)
        self.assertEqual(len(recent), 6)
        self.assertEqual(recent[0].action, "EXPORT")
        self.assertEqual(recent[5].action, "LOGIN")
        self.assertEqual(recent[5].ip_address, "127.0.0.1")

    def test_dashboard_statistics_service(self):
        """Verify dashboard_statistics aggregates all KPI cards cleanly."""
        stats = dashboard_statistics()
        self.assertEqual(stats["revenue_today"], Decimal("800.00"))
        self.assertEqual(stats["orders_today"], 3)
        self.assertEqual(stats["pending_orders_count"], 1)
        self.assertEqual(stats["processing_orders_count"], 1)
        self.assertEqual(stats["total_products"], 2)
        self.assertEqual(stats["total_customers"], 1)
        self.assertEqual(stats["average_order_value"], Decimal("400.00"))

    def test_staff_notifications_service(self):
        """Verify staff_notifications generates actionable alerts."""
        notifs = staff_notifications(user=self.staff_user, limit=10)
        self.assertTrue(len(notifs) >= 2)
        types = [n["type"] for n in notifs]
        self.assertIn("new_order", types)
        self.assertIn("new_customer", types)

    def test_get_dashboard_summary_service(self):
        """Verify get_dashboard_summary returns full structure."""
        summary = get_dashboard_summary()
        self.assertIn("statistics", summary)
        self.assertIn("recent_orders", summary)
        self.assertIn("new_customers", summary)
        self.assertIn("activity_feed", summary)
        self.assertIn("notifications", summary)

    def test_staff_profile_updates(self):
        """Verify staff contact details and preference update services."""
        update_staff_contact(self.staff_user, "+1-800-555-0199")
        self.assertEqual(UserProfile.objects.get(user=self.staff_user).phone_number, "+1-800-555-0199")

        update_staff_preferences(
            self.staff_user,
            email_alerts=False,
            low_stock_alerts=True,
            new_order_alerts=True,
            system_notification_alerts=False,
            dark_mode=True,
        )
        prefs = StaffPreference.objects.get(user=self.staff_user)
        self.assertTrue(prefs.dark_mode)
        self.assertFalse(prefs.email_alerts)


class DashboardViewsTestCase(TestCase):
    """Test suite verifying URL routing, templates, and view HTTP responses."""

    def setUp(self):
        self.client.logout()
        self.guest = User.objects.create_user(email="guest.view@houseofbore.com", password="password123")
        self.guest.is_staff = False
        self.guest.save()

        self.staff = User.objects.create_user(email="staff.view@houseofbore.com", password="password123")
        self.staff.is_staff = True
        self.staff.save()
        assign_role(self.staff, "store_manager")

    def test_dashboard_home_view_access(self):
        """Verify authentication gating on dashboard home URL /dashboard/."""
        # Unauthenticated redirects to login
        resp_anon = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp_anon.status_code, 302)

        # Authenticated non-staff returns 403 access denied
        self.client.force_login(self.guest)
        resp_guest = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp_guest.status_code, 403)
        self.assertTemplateUsed(resp_guest, "dashboard/access_denied.html")

        # Staff user returns 200 with dashboard template
        self.client.force_login(self.staff)
        resp_staff = self.client.get(reverse("dashboard:home"))
        self.assertEqual(resp_staff.status_code, 200)
        self.assertTemplateUsed(resp_staff, "dashboard/dashboard.html")
        self.assertIn("statistics", resp_staff.context)

    def test_staff_profile_view_and_updates(self):
        """Verify staff profile page and POST contact updates."""
        self.client.force_login(self.staff)
        resp_profile = self.client.get(reverse("dashboard:profile"))
        self.assertEqual(resp_profile.status_code, 200)
        self.assertTemplateUsed(resp_profile, "dashboard/profile.html")

        # Post phone number update
        resp_contact = self.client.post(
            reverse("dashboard:profile_contact"),
            {"phone_number": "+1-555-888-9999"}
        )
        self.assertRedirects(resp_contact, reverse("dashboard:profile"))
        self.assertEqual(UserProfile.objects.get(user=self.staff).phone_number, "+1-555-888-9999")

        # Post preferences update
        resp_prefs = self.client.post(
            reverse("dashboard:profile_preferences"),
            {
                "email_alerts": "on",
                "low_stock_alerts": "on",
                "new_order_alerts": "on",
                "system_notification_alerts": "on",
                "dark_mode": "on",
            }
        )
        self.assertRedirects(resp_prefs, reverse("dashboard:profile"))
        self.assertTrue(StaffPreference.objects.get(user=self.staff).dark_mode)

    def test_notification_list_view(self):
        """Verify notification center page renders with alerts."""
        self.client.force_login(self.staff)
        resp_notifs = self.client.get(reverse("dashboard:notifications"))
        self.assertEqual(resp_notifs.status_code, 200)
        self.assertTemplateUsed(resp_notifs, "dashboard/notifications.html")
        self.assertIn("notifications", resp_notifs.context)

    def test_navigation_placeholder_views(self):
        """Verify all navigation section views render placeholder cleanly."""
        self.client.force_login(self.staff)
        sections = ["products", "customers", "marketing", "reports", "settings", "users"]
        for sec in sections:
            resp = self.client.get(reverse(f"dashboard:{sec}"))
            self.assertEqual(resp.status_code, 200)
            self.assertTemplateUsed(resp, "dashboard/placeholder_section.html")
            self.assertEqual(resp.context["active_nav"], sec)

    def test_orders_management_views(self):
        """Verify administrative orders management list and detail views."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("dashboard:orders"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard/orders/order_list.html")
        self.assertEqual(resp.context["active_nav"], "orders")

    def test_access_denied_view_direct(self):
        """Verify direct access to /dashboard/access-denied/ returns 403."""
        resp = self.client.get(reverse("dashboard:access_denied"))
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, "dashboard/access_denied.html")

    def test_product_add_with_image(self):
        """Verify adding a product with an initial image field creates the Product and ProductImage."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.staff)
        category = Category.objects.create(name="Outerwear Test", slug="outerwear-test")
        image_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        img_file = SimpleUploadedFile("test_garment.gif", image_content, content_type="image/gif")

        post_data = {
            "name": "New Luxury Trench",
            "slug": "new-luxury-trench",
            "short_description": "Short summary",
            "description": "Full detailed description",
            "category": category.pk,
            "price": "1200.00",
            "stock_quantity": "10",
            "low_stock_threshold": "2",
            "is_active": "on",
            "image": img_file,
        }
        resp = self.client.post(reverse("dashboard:product_add"), data=post_data)
        product = Product.objects.filter(slug="new-luxury-trench").first()
        self.assertIsNotNone(product)
        self.assertEqual(product.images.count(), 1)
        self.assertTrue(product.images.first().is_primary)

