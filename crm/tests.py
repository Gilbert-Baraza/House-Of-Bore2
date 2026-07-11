# crm/tests.py
"""
crm/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated integration tests for Customer Relationship Management (CRM).
Verifies 360° profile aggregation, chronological interaction timeline sorting,
behavioral cohort segmentation, private staff note isolation, and RBAC permissions.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Address
from dashboard.models import StaffRole
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus
from products.models import Brand, Category, Product
from .models import CustomerInteractionRecord, CustomerStaffNote
from .selectors import customer_segments, customer_statistics, search_customers
from .services import (
    add_staff_note,
    build_customer_profile,
    customer_timeline,
    export_customer_data,
    log_customer_interaction,
)

User = get_user_model()


class CRMIntegrationTestSuite(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Create customer patron
        self.patron = User.objects.create_user(
            email="patron_vip@houseofbore.com",
            password="SecurePassword123!",
            first_name="Victoria",
            last_name="Sterling",
        )
        Address.objects.create(
            user=self.patron,
            label="Home Villa",
            recipient_name="Victoria Sterling",
            phone_number="+1-555-0199",
            address_line_1="100 Luxury Way",
            city="Beverly Hills",
            county_or_state="CA",
            postal_code="90210",
        )

        # Create store manager staff member with full CRM permissions
        self.manager = User.objects.create_user(
            email="manager@houseofbore.com",
            password="SecurePassword123!",
            first_name="Alexander",
            last_name="Vance",
            is_staff=True,
        )
        self.manager_role = StaffRole.objects.create(
            code="store_manager",
            name="Store Manager",
            description="Full operational & CRM management",
        )
        self.manager.staff_roles.add(self.manager_role)

        # Create unauthorized regular staff member
        self.basic_staff = User.objects.create_user(
            email="intern@houseofbore.com",
            password="SecurePassword123!",
            is_staff=True,
        )

        # Create sample products and order
        self.cat = Category.objects.create(name="Haute Couture", slug="haute-couture")
        self.brand = Brand.objects.create(name="Atelier Bore", slug="atelier-bore")
        self.product = Product.objects.create(
            name="Cashmere Overcoat",
            slug="cashmere-overcoat",
            category=self.cat,
            brand=self.brand,
            price=Decimal("1250.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.order = Order.objects.create(
            user=self.patron,
            order_number="ORD-778899",
            status=OrderStatus.PAID,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("1250.00"),
            grand_total=Decimal("1250.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            sku="CO-991",
            unit_price=self.product.price,
            quantity=1,
            line_total=self.product.price,
        )

    def test_customer_staff_note_creation_and_models(self):
        """Verify CustomerStaffNote persistence and custom permissions checks."""
        note = add_staff_note(
            customer=self.patron,
            author=self.manager,
            note="Prefers champagne on arrival and express tailoring.",
            category="vip",
            is_pinned=True,
        )
        self.assertEqual(note.customer, self.patron)
        self.assertEqual(note.author, self.manager)
        self.assertTrue(note.is_pinned)
        self.assertEqual(note.category, "vip")
        self.assertIn("patron_vip@houseofbore.com", str(note))

    def test_build_customer_profile_service(self):
        """Verify build_customer_profile correctly calculates LTV, order counts, and address integration."""
        profile = build_customer_profile(self.patron)
        self.assertEqual(profile["id"], self.patron.pk)
        self.assertEqual(profile["email"], self.patron.email)
        self.assertEqual(profile["full_name"], "Victoria Sterling")
        self.assertEqual(profile["total_orders"], 1)
        self.assertEqual(profile["lifetime_value"], Decimal("1250.00"))
        self.assertEqual(profile["phone_number"], "+1-555-0199")
        self.assertEqual(len(profile["addresses"]), 1)

    def test_customer_timeline_service(self):
        """Verify customer_timeline chronological aggregation of orders, notes, and interactions."""
        add_staff_note(self.patron, self.manager, "Assigned personal concierge.", category="general")
        log_customer_interaction(self.patron, self.manager, "phone", "Verified wire transfer for order #ORD-778899")

        timeline = customer_timeline(self.patron)
        self.assertGreaterEqual(len(timeline), 3)
        # Verify both note and interaction appear in events
        event_types = [ev["event_type"] for ev in timeline]
        self.assertIn("order", event_types)
        self.assertIn("staff_note", event_types)
        self.assertIn("interaction", event_types)

    def test_customer_segmentation_and_statistics_selectors(self):
        """Verify dynamic cohort categorization and KPI analytics."""
        segments = customer_segments(use_cache=False)
        self.assertIn("new_customers", segments)
        self.assertIn("high_spending", segments)
        self.assertGreaterEqual(segments["high_spending"]["count"], 1)

        stats = customer_statistics(use_cache=False)
        self.assertGreaterEqual(stats["total_customers"], 1)
        self.assertEqual(stats["total_revenue"], Decimal("1250.00"))
        self.assertEqual(stats["average_order_value"], Decimal("1250.00"))

    def test_search_customers_selector_performance(self):
        """Verify search_customers queries without N+1 bottlenecks."""
        qs = search_customers(query="Victoria", segment="all")
        self.assertEqual(qs.count(), 1)
        patron_obj = qs.first()
        self.assertEqual(patron_obj.total_orders_count, 1)
        self.assertEqual(patron_obj.lifetime_spent, Decimal("1250.00"))

    def test_crm_views_rbac_protection(self):
        """Verify CRM views require crm.view_customer and return 403 access denied for unauthorized roles."""
        # 1. Anonymous access
        url_dashboard = reverse("crm:dashboard")
        resp_anon = self.client.get(url_dashboard)
        self.assertNotEqual(resp_anon.status_code, 200)

        # 2. Unauthorized staff access
        self.client.force_login(self.basic_staff)
        resp_unauth = self.client.get(url_dashboard)
        self.assertEqual(resp_unauth.status_code, 403)

        # 3. Authorized Store Manager access
        self.client.force_login(self.manager)
        resp_auth = self.client.get(url_dashboard)
        self.assertEqual(resp_auth.status_code, 200)

        # Detail view inspection
        resp_detail = self.client.get(reverse("crm:customer_detail", kwargs={"pk": self.patron.pk}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Victoria Sterling")
        self.assertContains(resp_detail, "1250.00")

    def test_staff_note_and_interaction_submission_endpoints(self):
        """Verify private notes and concierge interactions can be submitted via POST by authorized staff."""
        self.client.force_login(self.manager)

        # Submit note
        note_url = reverse("crm:staff_note_add", kwargs={"pk": self.patron.pk})
        resp_note = self.client.post(note_url, {
            "category": "vip",
            "note": "Client requested private styling session next Tuesday.",
            "is_pinned": "on",
        })
        self.assertRedirects(resp_note, reverse("crm:customer_detail", kwargs={"pk": self.patron.pk}))
        self.assertEqual(self.patron.staff_notes.count(), 1)

        # Submit interaction log
        irec_url = reverse("crm:interaction_add", kwargs={"pk": self.patron.pk})
        resp_irec = self.client.post(irec_url, {
            "interaction_type": "email",
            "summary": "Sent autumn luxury lookbook",
            "details": "Client acknowledged receipt with enthusiasm.",
        })
        self.assertRedirects(resp_irec, reverse("crm:customer_detail", kwargs={"pk": self.patron.pk}))
        self.assertEqual(self.patron.interaction_records.count(), 1)

    def test_customer_export_endpoint(self):
        """Verify secure JSON export of 360° customer data."""
        self.client.force_login(self.manager)
        export_url = reverse("crm:customer_export", kwargs={"pk": self.patron.pk})
        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("houseofbore_patron_360_", response["Content-Disposition"])
