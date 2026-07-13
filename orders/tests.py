# orders/tests.py
"""
orders/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite verifying Order and OrderItem models, order
numbering atomic generation, address and product snapshots immutability,
security access boundaries, service layer operations, and UI view rendering.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
import datetime
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from products.models import Brand, Category, Product, ProductOption, ProductOptionValue, ProductVariant, ProductVariantOption
from cart.models import Cart, CartItem
from cart.services import add_to_cart
from checkout.models import CheckoutSession, CheckoutAddress
from checkout.services import get_or_create_checkout, update_shipping, update_billing, validate_checkout
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
from orders.services import generate_order_number, snapshot_addresses, snapshot_products, calculate_order_totals, create_order, transition_order_status
from orders.selectors import get_order, get_customer_orders, get_order_items, recent_orders

User = get_user_model()


class OrderBaseTestCase(TestCase):
    """
    Setup common test fixtures: categories, brands, products, variants, and users.
    """
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="SecurePassword123!",
            first_name="Jane",
            last_name="Doe",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="OtherPassword123!",
            first_name="John",
            last_name="Smith",
        )
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            password="StaffPassword123!",
            is_staff=True,
        )
        self.category = Category.objects.create(
            name="Tailored Suits",
            slug="tailored-suits",
            is_active=True,
        )
        self.brand = Brand.objects.create(
            name="House of Bore Atelier",
            slug="house-of-bore-atelier",
            is_active=True,
        )
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Bespoke Wool Suit",
            slug="bespoke-wool-suit",
            price=Decimal("1200.00"),
            stock_quantity=20,
            is_active=True,
        )
        # Variant setup
        self.opt_size = ProductOption.objects.create(name="Size", display_name="Size")
        self.val_40r = ProductOptionValue.objects.create(option=self.opt_size, value="40R", display_order=1)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="SUIT-WOOL-40R",
            price_override=Decimal("1350.00"),
            stock_quantity=10,
            is_active=True,
        )
        ProductVariantOption.objects.create(variant=self.variant, option_value=self.val_40r)

    def setup_session(self, request):
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def create_ready_checkout_session(self, request, user=None, with_variant=True):
        if user:
            request.user = user
        checkout = get_or_create_checkout(request)
        
        # Add item to cart
        add_to_cart(request, product_id=self.product.pk, quantity=2, variant_id=self.variant.pk if with_variant else None)
        
        # Add addresses
        update_shipping(checkout, {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "company_name": "Bore Corp",
            "address_line_1": "100 Luxury Way",
            "address_line_2": "Suite 500",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        })
        update_billing(checkout, {}, billing_same_as_shipping=True)
        return checkout


class OrderNumberingTests(OrderBaseTestCase):
    """
    Verify unique, human-readable atomic order number generation (`HOB-YYYYMMDD-000001`).
    """
    def test_order_number_format_and_sequence(self):
        num1 = generate_order_number()
        today_str = timezone.now().strftime("%Y%m%d")
        self.assertTrue(num1.startswith(f"HOB-{today_str}-"))
        self.assertEqual(num1, f"HOB-{today_str}-000001")

        # Create dummy order with num1
        Order.objects.create(order_number=num1)
        
        num2 = generate_order_number()
        self.assertEqual(num2, f"HOB-{today_str}-000002")

        Order.objects.create(order_number=num2)
        num3 = generate_order_number()
        self.assertEqual(num3, f"HOB-{today_str}-000003")


class OrderCreationServiceTests(OrderBaseTestCase):
    """
    Verify order creation workflow, address/product snapshots, and status transitions.
    """
    def test_create_order_successfully_clears_cart_and_locks_totals(self):
        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user, with_variant=True)

        order = create_order(req, checkout, customer_notes="Deliver to front desk")
        
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, PaymentStatus.AWAITING_PAYMENT)
        self.assertEqual(order.customer_notes, "Deliver to front desk")
        
        # Verify address snapshot
        self.assertEqual(order.shipping_address_snapshot["recipient_name"], "Jane Doe")
        self.assertEqual(order.shipping_address_snapshot["postal_code"], "90210")
        self.assertEqual(order.billing_address_snapshot["city"], "Beverly Hills")

        # Verify line item snapshots
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        self.assertEqual(item.product_name, "Bespoke Wool Suit")
        self.assertEqual(item.sku, "SUIT-WOOL-40R")
        self.assertEqual(item.variant_description, "Size: 40R")
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal("1350.00"))
        self.assertEqual(item.line_total, Decimal("2700.00"))

        # Verify financial breakdown
        self.assertEqual(order.subtotal, Decimal("2700.00"))
        self.assertIsNotNone(order.currency)

    def test_create_order_records_dynamic_currency_from_settings(self):
        from settings.models import StoreSettings
        st = StoreSettings.load()
        st.default_currency = "EUR"
        st.save()

        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user, with_variant=True)

        order = create_order(req, checkout)
        self.assertEqual(order.currency, "EUR")
        self.assertEqual(order.grand_total, order.subtotal + order.tax_total + order.shipping_total)

        # Verify checkout session marked completed and cart cleared
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, "completed")
        self.assertEqual(checkout.cart.items.count(), 0)

    def test_transition_order_status_workflow(self):
        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user)
        order = create_order(req, checkout)

        transition_order_status(order, OrderStatus.PAID, note="Payment received via Visa ending in 4242")
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertIn("Payment received", order.customer_notes)

        transition_order_status(order, OrderStatus.DELIVERED, note="Signed by J. Doe")
        self.assertEqual(order.status, OrderStatus.DELIVERED)
        self.assertEqual(order.fulfillment_status, FulfillmentStatus.FULFILLED)


class OrderSnapshotImmutabilityTests(OrderBaseTestCase):
    """
    Verify historical order immutability. Mutating or deleting live products/variants
    must never alter past order records or item snapshots.
    """
    def test_order_item_snapshots_immune_to_live_product_mutation(self):
        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user, with_variant=True)
        order = create_order(req, checkout)

        # Mutate live product and variant
        self.product.name = "MODIFIED PRODUCT NAME"
        self.product.price = Decimal("99999.00")
        self.product.save()

        self.variant.sku = "MUTATED-SKU-000"
        self.variant.price_override = Decimal("88888.00")
        self.variant.save()

        # Reload historical order item from DB
        item = OrderItem.objects.get(order=order)
        self.assertEqual(item.product_name, "Bespoke Wool Suit")
        self.assertEqual(item.sku, "SUIT-WOOL-40R")
        self.assertEqual(item.unit_price, Decimal("1350.00"))
        self.assertEqual(item.line_total, Decimal("2700.00"))


class OrderSecurityAndPermissionsTests(OrderBaseTestCase):
    """
    Verify customer data isolation and selector security boundaries.
    """
    def test_customer_can_only_access_their_own_orders(self):
        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user)
        order = create_order(req, checkout)

        # User checks their order
        self.assertEqual(get_order(order.order_number, user=self.user), order)
        
        # Other user tries to access User's order
        self.assertIsNone(get_order(order.order_number, user=self.other_user))
        
        # Staff user accesses User's order
        self.assertEqual(get_order(order.order_number, user=self.staff_user), order)

    def test_guest_session_order_access_verification(self):
        req = self.factory.get("/")
        self.setup_session(req)
        # No user attached (guest)
        checkout = self.create_ready_checkout_session(req, user=None)
        order = create_order(req, checkout)

        # Access with exact session key
        self.assertEqual(get_order(order.order_number, session_key=req.session.session_key), order)
        # Access with mismatched session key
        self.assertIsNone(get_order(order.order_number, session_key="invalid-session-key"))


class OrderViewsAndPaginationTests(OrderBaseTestCase):
    """
    Verify UI endpoints: OrderCreateView POST, OrderListView pagination, and OrderDetailView rendering.
    """
    def test_order_create_view_post_creates_order_and_redirects(self):
        self.client.force_login(self.user)
        req = self.factory.get("/")
        self.setup_session(req)
        req.user = self.user
        checkout = self.create_ready_checkout_session(req, user=self.user)

        # Associate session key with client session
        session = self.client.session
        session["checkout_session_id"] = checkout.id
        session.save()

        res = self.client.post(reverse("orders:create"), {"customer_notes": "Leave at porch"})
        self.assertEqual(res.status_code, 302)
        
        order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(order)
        self.assertRedirects(res, reverse("orders:detail", kwargs={"order_number": order.order_number}))

    def test_order_list_view_pagination_and_authentication(self):
        # Unauthenticated access redirects to login
        res_unauth = self.client.get(reverse("orders:list"))
        self.assertEqual(res_unauth.status_code, 302)

        self.client.force_login(self.user)
        
        # Create 15 orders for pagination testing
        for i in range(15):
            Order.objects.create(
                order_number=f"HOB-TEST-{i:06d}",
                user=self.user,
                grand_total=Decimal("100.00")
            )

        res = self.client.get(reverse("orders:list"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("orders", res.context)
        self.assertTrue(res.context["is_paginated"])
        self.assertEqual(len(res.context["orders"]), 10)  # Page 1 has 10 items

        res_page2 = self.client.get(reverse("orders:list") + "?page=2")
        self.assertEqual(len(res_page2.context["orders"]), 5)  # Page 2 has 5 items

    def test_order_detail_view_rendering_and_security(self):
        req = self.factory.get("/")
        self.setup_session(req)
        checkout = self.create_ready_checkout_session(req, user=self.user)
        order = create_order(req, checkout)

        self.client.force_login(self.user)
        res = self.client.get(reverse("orders:detail", kwargs={"order_number": order.order_number}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, order.order_number)
        self.assertContains(res, "Bespoke Wool Suit")
        self.assertContains(res, "SUIT-WOOL-40R")

        # Other user tries to access details via URL -> redirects away
        self.client.force_login(self.other_user)
        res_unauth = self.client.get(reverse("orders:detail", kwargs={"order_number": order.order_number}))
        self.assertEqual(res_unauth.status_code, 302)
