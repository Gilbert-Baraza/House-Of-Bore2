from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from inventory.models import Inventory, InventoryMovement, MovementType
from inventory.permissions import ensure_inventory_permissions
from inventory.services import fulfill_reserved_stock, reserve_stock
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus
from orders.services import transition_order_status
from products.models import Brand, Category, Product, ProductVariant


class InventoryCoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="ops@example.com", password="strong-pass123", is_staff=True)
        self.category = Category.objects.create(name="Accessories", slug="accessories")
        self.brand = Brand.objects.create(name="Test Brand", slug="test-brand")
        self.product = Product.objects.create(
            name="Ledger Test",
            slug="ledger-test",
            short_description="Test",
            description="Test",
            category=self.category,
            brand=self.brand,
            price=Decimal("10.00"),
            stock_quantity=10,
            low_stock_threshold=3,
        )
        self.variant = ProductVariant.objects.create(product=self.product, sku="INV-001", stock_quantity=10, low_stock_threshold=3)

    def test_inventory_is_created_for_variant_and_tracks_available_stock(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        self.assertEqual(inventory.available_quantity, 10)
        self.assertEqual(inventory.reorder_level, 3)

    def test_add_stock_creates_ledger_entry_and_updates_available_stock(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory = inventory.add_stock(5, performed_by=self.user, notes="Restock", movement_type=MovementType.MANUAL_INCREASE)
        self.assertEqual(inventory.available_quantity, 15)
        self.assertEqual(inventory.movements.count(), 1)
        movement = inventory.movements.first()
        self.assertEqual(movement.movement_type, MovementType.MANUAL_INCREASE)
        self.assertEqual(movement.new_quantity, 15)

    def test_reserve_stock_prevents_over_reservation(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory.add_stock(0, performed_by=self.user, notes="Seed")
        inventory.reserve_stock(6, performed_by=self.user, notes="Order reserve")
        self.assertEqual(inventory.reserved_quantity, 6)
        with self.assertRaises(ValidationError):
            inventory.reserve_stock(6, performed_by=self.user, notes="Overflow")

    def test_release_stock_restores_available_stock(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory.reserve_stock(4, performed_by=self.user, notes="Hold")
        inventory.release_stock(2, performed_by=self.user, notes="Release")
        self.assertEqual(inventory.reserved_quantity, 2)
        self.assertEqual(inventory.available_quantity, 10)

    def test_mark_damaged_and_adjustment_require_reason(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        with self.assertRaises(ValidationError):
            inventory.adjust_stock(1, performed_by=self.user, notes="", reason="")
        inventory.mark_damaged(2, performed_by=self.user, notes="Damaged on arrival")
        self.assertEqual(inventory.damaged_quantity, 2)

    def test_ledger_entries_are_immutable(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory.add_stock(3, performed_by=self.user, notes="Restock")
        movement = inventory.movements.first()
        with self.assertRaises(ValidationError):
            movement.notes = "Changed"
            movement.save()

    def test_inventory_permissions_are_registered(self):
        permission_codes = ensure_inventory_permissions()
        self.assertTrue(Permission.objects.filter(codename__in=permission_codes).exists())

    def test_backfill_inventory_command_recreates_missing_inventory_records(self):
        Inventory.objects.filter(product_variant=self.variant).delete()

        call_command("backfill_inventory")

        self.assertTrue(Inventory.objects.filter(product_variant=self.variant).exists())

    def test_order_status_transition_reserves_and_fulfills_inventory(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory.available_quantity = 10
        inventory.save(update_fields=["available_quantity", "updated_at"])

        order = Order.objects.create(
            order_number="HOB-TEST-0001",
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.AWAITING_PAYMENT,
            fulfillment_status="unfulfilled",
            subtotal=Decimal("10.00"),
            grand_total=Decimal("10.00"),
        )
        OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name, sku=self.variant.sku, quantity=3, unit_price=Decimal("10.00"), line_total=Decimal("30.00"))

        transition_order_status(order, OrderStatus.PAID)
        self.assertEqual(Inventory.objects.get(product_variant=self.variant).reserved_quantity, 3)

        transition_order_status(order, OrderStatus.DELIVERED)
        self.assertEqual(Inventory.objects.get(product_variant=self.variant).available_quantity, 7)

    def test_order_cancellation_releases_reserved_stock(self):
        inventory = Inventory.objects.get(product_variant=self.variant)
        inventory.available_quantity = 10
        inventory.save(update_fields=["available_quantity", "updated_at"])

        order = Order.objects.create(
            order_number="HOB-TEST-0002",
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.AWAITING_PAYMENT,
            fulfillment_status="unfulfilled",
            subtotal=Decimal("20.00"),
            grand_total=Decimal("20.00"),
        )
        OrderItem.objects.create(order=order, product=self.product, product_name=self.product.name, sku=self.variant.sku, quantity=4, unit_price=Decimal("10.00"), line_total=Decimal("40.00"))

        transition_order_status(order, OrderStatus.PAID)
        self.assertEqual(Inventory.objects.get(product_variant=self.variant).reserved_quantity, 4)

        transition_order_status(order, OrderStatus.CANCELLED)
        inv_after = Inventory.objects.get(product_variant=self.variant)
        self.assertEqual(inv_after.reserved_quantity, 0)
        self.assertEqual(inv_after.available_quantity, 10)


class InventoryDashboardRBACTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="mgr@example.com", password="pass-password123", is_staff=True)
        self.unauthorized_user = get_user_model().objects.create_user(email="cs@example.com", password="pass-password123", is_staff=True)
        self.category = Category.objects.create(name="Tools", slug="tools")
        self.brand = Brand.objects.create(name="Tool Brand", slug="tool-brand")
        self.product = Product.objects.create(
            name="RBAC Variant",
            slug="rbac-variant",
            short_description="RBAC",
            description="RBAC",
            category=self.category,
            brand=self.brand,
            price=Decimal("25.00"),
            stock_quantity=5,
        )
        self.variant = ProductVariant.objects.create(product=self.product, sku="RBAC-001", stock_quantity=5)
        self.inventory = Inventory.objects.get(product_variant=self.variant)

        from dashboard.models import StaffRole
        from dashboard.permissions import DEFAULT_ROLES_CONFIG
        self.role = StaffRole.objects.create(
            code="inventory_manager",
            name="Inventory Manager",
            description="Inventory Manager",
            permissions=DEFAULT_ROLES_CONFIG["inventory_manager"]["permissions"],
        )
        self.role.users.add(self.user)

    def test_inventory_dashboard_views_accessible_by_inventory_manager(self):
        self.client.force_login(self.user)
        from django.urls import reverse
        urls = [
            reverse("inventory:dashboard"),
            reverse("inventory:movement_list"),
            reverse("inventory:valuation"),
            reverse("inventory:alerts"),
            reverse("inventory:stock_history"),
            reverse("inventory:product_inventory", args=[self.inventory.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed accessing {url}")

    def test_inventory_dashboard_views_forbidden_for_unauthorized_staff(self):
        self.client.force_login(self.unauthorized_user)
        from django.urls import reverse
        urls = [
            reverse("inventory:dashboard"),
            reverse("inventory:movement_list"),
            reverse("inventory:valuation"),
            reverse("inventory:alerts"),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, f"Expected 403 for {url}")


class InventoryAuditAndAlertsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="auditor@example.com", password="pass-password123", is_staff=True)
        from dashboard.models import StaffRole
        from dashboard.permissions import DEFAULT_ROLES_CONFIG
        self.role = StaffRole.objects.create(
            code="store_manager",
            name="Store Manager",
            description="Store Manager",
            permissions=DEFAULT_ROLES_CONFIG["store_manager"]["permissions"],
        )
        self.role.users.add(self.user)

        self.category = Category.objects.create(name="Audited", slug="audited")
        self.brand = Brand.objects.create(name="Audited Brand", slug="audited-brand")
        self.product = Product.objects.create(
            name="Audit Variant",
            slug="audit-variant",
            short_description="Audit",
            description="Audit",
            category=self.category,
            brand=self.brand,
            price=Decimal("50.00"),
            stock_quantity=20,
        )
        self.variant = ProductVariant.objects.create(product=self.product, sku="AUD-001", stock_quantity=20)
        self.inventory = Inventory.objects.get(product_variant=self.variant)

    def test_adjustment_form_submission_creates_ledger_and_audit_log(self):
        self.client.force_login(self.user)
        from django.urls import reverse
        from dashboard.models import AuditLog

        url = reverse("inventory:adjustment_form", args=[self.inventory.pk])
        response = self.client.post(url, {
            "action": "increase",
            "quantity": 10,
            "reason": "Physical cycle count discrepancy adjustment",
            "notes": "Verified by floor lead",
        })
        self.assertEqual(response.status_code, 302)

        inv_after = Inventory.objects.get(pk=self.inventory.pk)
        self.assertEqual(inv_after.available_quantity, 30)

        # Check immutable ledger
        self.assertTrue(inv_after.movements.filter(notes__contains="Physical cycle count discrepancy adjustment").exists())

        # Check system audit log
        audit_log = AuditLog.objects.filter(model_name="Inventory", action="UPDATE").first()
        self.assertIsNotNone(audit_log)
        self.assertIn("Adjusted stock (increase: 10)", audit_log.description)
        self.assertEqual(audit_log.user, self.user)

    def test_generate_inventory_alerts_task_runs_successfully(self):
        from inventory.tasks import generate_inventory_alerts
        # Trigger Celery alert task synchronously
        result = generate_inventory_alerts()
        self.assertIn("low_stock_count", result)
        self.assertIn("out_of_stock_count", result)


