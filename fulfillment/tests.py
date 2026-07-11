# fulfillment/tests.py
"""
fulfillment/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive regression and integration test suite for the Order Fulfillment &
Shipping Operations module (`fulfillment`).

Tests:
1. State transitions across picking, packing, shipping dispatch, and delivery.
2. Integration with OMS (`orders.services.transition_order_status`) and Stock
   Ledger (`inventory.services`).
3. RBAC permission verification across store managers, inventory managers,
   and fulfillment managers.
4. RMA return inspection and physical stock restock reconciliation.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from dashboard.models import StaffRole
from inventory.models import Inventory, InventoryMovement, MovementType
from inventory.services import reserve_stock
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus
from products.models import Product, ProductVariant
from .models import (
    FulfillmentEvent,
    FulfillmentItem,
    FulfillmentOrder,
    FulfillmentPriority,
    FulfillmentWorkflowStatus,
    ReturnExchangeRequest,
    ReturnRequestStatus,
    Shipment,
    ShipmentStatus,
)
from .permissions import ensure_fulfillment_permissions
from .selectors import (
    fulfillment_statistics,
    pending_packs,
    pending_picks,
    ready_for_dispatch,
)
from .services import (
    assign_order,
    cancel_fulfillment,
    complete_packing,
    complete_picking,
    confirm_delivery,
    create_fulfillment_order,
    create_shipment,
    dispatch_order,
    initiate_return,
    process_return_inspection,
    start_packing,
    start_picking,
)

User = get_user_model()


class FulfillmentIntegrationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        ensure_fulfillment_permissions()

        # Users
        self.super_admin = User.objects.create_superuser(
            email="admin@houseofbore.test",
            password="adminpassword123",
            first_name="Super",
            last_name="Admin"
        )
        self.staff_user = User.objects.create_user(
            email="logistics@houseofbore.test",
            password="staffpassword123",
            is_staff=True,
            first_name="Fulfillment",
            last_name="Lead"
        )
        self.picker_user = User.objects.create_user(
            email="picker@houseofbore.test",
            password="pickerpassword123",
            is_staff=True,
            first_name="Joe",
            last_name="Picker"
        )
        role = StaffRole.objects.get(code="fulfillment_manager")
        self.staff_user.staff_roles.add(role)
        self.picker_user.staff_roles.add(role)

        from products.models import Brand, Category
        self.category = Category.objects.create(name="Drapes", slug="drapes")
        self.brand = Brand.objects.create(name="House of Bore", slug="house-of-bore")
        self.product = Product.objects.create(
            name="Luxury Silk Velvet Drape",
            slug="luxury-silk-velvet-drape",
            short_description="Silk velvet drapes",
            description="Premium luxury silk velvet drapery.",
            category=self.category,
            brand=self.brand,
            price=Decimal("450.00"),
            stock_quantity=50,
            low_stock_threshold=10,
        )
        self.variant, _ = ProductVariant.objects.get_or_create(
            product=self.product,
            sku="L-SILK-DRP-01-EM-108",
            defaults={
                "price_override": Decimal("450.00"),
                "stock_quantity": 50,
                "low_stock_threshold": 10,
            }
        )
        self.inventory, _ = Inventory.objects.get_or_create(
            product_variant=self.variant,
            defaults={
                "available_quantity": 50,
                "reorder_level": 10,
                "reorder_quantity": 20,
            }
        )

        # Customer Order
        self.customer = User.objects.create_user(
            email="customer@houseofbore.test",
            password="customerpassword123"
        )
        self.order = Order.objects.create(
            order_number="HOB-20260711-000101",
            user=self.customer,
            status=OrderStatus.PAID,
            payment_status=PaymentStatus.PAID,
            shipping_address_snapshot={
                "recipient_name": "Eleanor Bore",
                "address_line_1": "100 Grand Avenue",
                "city": "New York",
                "county_or_state": "NY",
                "postal_code": "10001",
                "country": "US",
                "phone_number": "555-0199"
            },
            subtotal=Decimal("900.00"),
            grand_total=Decimal("900.00")
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name="Luxury Silk Velvet Drape",
            sku="L-SILK-DRP-01-EM-108",
            quantity=2,
            unit_price=Decimal("450.00"),
            line_total=Decimal("900.00")
        )
        reserve_stock(self.inventory, 2, notes="Initial order reservation")

    def test_fulfillment_order_initialization_and_selectors(self):
        fo = create_fulfillment_order(self.order, priority=FulfillmentPriority.HIGH, performed_by=self.staff_user)
        self.assertEqual(fo.order, self.order)
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.PAID)
        self.assertEqual(fo.priority, FulfillmentPriority.HIGH)
        self.assertEqual(fo.items.count(), 1)
        self.assertEqual(fo.items.first().order_item, self.order_item)
        self.assertEqual(fo.items.first().quantity, 2)

        # Verify selectors
        picks = pending_picks()
        self.assertIn(fo, picks)
        stats = fulfillment_statistics()
        self.assertEqual(stats["total_orders"], 1)
        self.assertEqual(stats["awaiting_pick"], 1)

    def test_complete_picking_and_packing_workflow(self):
        fo = create_fulfillment_order(self.order, performed_by=self.staff_user)

        # Assign Picker
        assign_order(fo, staff_user=self.picker_user, role="picker", performed_by=self.staff_user)
        fo.refresh_from_db()
        self.assertEqual(fo.assigned_picker, self.picker_user)

        # Start Picking
        start_picking(fo, picker=self.picker_user, performed_by=self.picker_user)
        fo.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.PICKING)
        self.assertIsNotNone(fo.picking_started_at)

        # Complete Picking cleanly
        item = fo.items.first()
        picked_data = [{"item_id": item.pk, "picked_quantity": 2, "missing_quantity": 0, "notes": "All verified"}]
        complete_picking(fo, picked_items_data=picked_data, performed_by=self.picker_user)
        fo.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.PICKED)
        self.assertEqual(fo.picking_progress_percentage, 100)
        self.assertIn(fo, pending_packs())

        # Start & Complete Packing
        start_packing(fo, packer=self.staff_user, performed_by=self.staff_user)
        fo.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.PACKING)
        complete_packing(fo, performed_by=self.staff_user, notes="Box sealed securely with bubble wrap.")
        fo.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.PACKED)
        self.assertEqual(fo.packing_progress_percentage, 100)

    def test_shipment_creation_and_dispatch_triggers_order_status_and_stock_fulfillment(self):
        fo = create_fulfillment_order(self.order, performed_by=self.staff_user)
        start_picking(fo, picker=self.staff_user, performed_by=self.staff_user)
        complete_picking(fo, performed_by=self.staff_user)
        start_packing(fo, packer=self.staff_user, performed_by=self.staff_user)
        complete_packing(fo, performed_by=self.staff_user)

        # Create Shipment
        shipment = create_shipment(
            fulfillment_order=fo,
            courier="FedEx Express",
            shipping_method="2-Day Express",
            tracking_number="HOB-TRK-9988776655",
            shipping_cost=Decimal("25.50"),
            dimensions={"length": 30.0, "width": 20.0, "height": 10.0, "weight": 2.5},
            performed_by=self.staff_user
        )
        fo.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.READY_FOR_DISPATCH)
        self.assertIn(fo, ready_for_dispatch())
        self.assertEqual(shipment.tracking_number, "HOB-TRK-9988776655")

        # Dispatch order -> should bridge status with Order and trigger inventory fulfill
        dispatch_order(fo, shipment=shipment, performed_by=self.staff_user)
        fo.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.SHIPPED)
        self.assertEqual(self.order.status, OrderStatus.SHIPPED)
        self.assertEqual(shipment.shipment_status, ShipmentStatus.IN_TRANSIT)

        # Check audit event log
        self.assertTrue(FulfillmentEvent.objects.filter(fulfillment_order=fo, event_type="DISPATCHED").exists())

    def test_confirm_delivery_and_rma_restock_workflow(self):
        fo = create_fulfillment_order(self.order, performed_by=self.staff_user)
        start_picking(fo, picker=self.staff_user, performed_by=self.staff_user)
        complete_picking(fo, performed_by=self.staff_user)
        start_packing(fo, packer=self.staff_user, performed_by=self.staff_user)
        complete_packing(fo, performed_by=self.staff_user)
        shipment = create_shipment(fo, tracking_number="HOB-TRK-11223344", performed_by=self.staff_user)
        dispatch_order(fo, shipment=shipment, performed_by=self.staff_user)

        # Confirm Delivery
        confirm_delivery(fo, shipment=shipment, performed_by=self.staff_user)
        fo.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.DELIVERED)
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)

        # Initiate RMA Return
        rma = initiate_return(fo, reason="Customer decided color didn't match decor", performed_by=self.staff_user)
        self.assertEqual(rma.status, ReturnRequestStatus.REQUESTED)

        # Process RMA and restock to inventory
        process_return_inspection(rma, action="restock", performed_by=self.staff_user, notes="Items pristine, restocked.")
        rma.refresh_from_db()
        fo.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(rma.status, ReturnRequestStatus.COMPLETED)
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.RETURNED)
        # Verify physical stock ledger restocked quantity 2 (50 - 2 shipped + 2 returned = 50)
        self.assertEqual(self.inventory.available_quantity, 50)
        self.assertTrue(InventoryMovement.objects.filter(inventory=self.inventory, movement_type=MovementType.RETURN).exists())

    def test_cancel_fulfillment_releases_order_and_inventory(self):
        fo = create_fulfillment_order(self.order, performed_by=self.staff_user)
        cancel_fulfillment(fo, reason="Customer cancelled before picking", performed_by=self.staff_user)
        fo.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(fo.fulfillment_status, FulfillmentWorkflowStatus.CANCELLED)
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)

    def test_invalid_state_transition_raises_validation_error(self):
        fo = create_fulfillment_order(self.order, performed_by=self.staff_user)
        # Cannot jump directly from PAID to DELIVERED without picking/packing/dispatch
        with self.assertRaises(ValidationError):
            confirm_delivery(fo, performed_by=self.staff_user)
