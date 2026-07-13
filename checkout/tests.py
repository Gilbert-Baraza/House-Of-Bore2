# checkout/tests.py
"""
checkout/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for the Checkout Foundation application.
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
from checkout.services import (
    get_or_create_checkout,
    update_shipping,
    update_billing,
    validate_checkout,
    checkout_summary,
)
from checkout.selectors import get_checkout, get_shipping_address, get_billing_address
from accounts.models import Address

User = get_user_model()


class CheckoutBaseTestCase(TestCase):
    """
    Setup base data models: category, brand, active products, and customer user accounts.
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
        self.category = Category.objects.create(
            name="Accessories",
            slug="accessories",
            is_active=True,
        )
        self.brand = Brand.objects.create(
            name="Luxury Brand",
            slug="luxury-brand",
            is_active=True,
        )
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Gold Cufflinks",
            slug="gold-cufflinks",
            price=Decimal("450.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Inactive Cufflinks",
            slug="inactive-cufflinks",
            price=Decimal("450.00"),
            stock_quantity=10,
            is_active=False,
        )

    def add_session_to_request(self, request):
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request


class CheckoutModelAndServiceTests(CheckoutBaseTestCase):
    """
    Unit tests covering CheckoutAddress, CheckoutSession, services, and selectors.
    """
    def test_checkout_session_creation_and_expiry(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        req.user = self.user

        # Create checkout session
        checkout = get_or_create_checkout(req)
        self.assertEqual(checkout.user, self.user)
        self.assertEqual(checkout.status, "active")
        self.assertFalse(checkout.is_expired)

        # Force expiry
        checkout.expires_at = timezone.now() - datetime.timedelta(hours=1)
        checkout.save()
        self.assertTrue(checkout.is_expired)

    def test_guest_checkout_session_binding(self):
        from django.contrib.auth.models import AnonymousUser
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        req.user = AnonymousUser()

        checkout = get_or_create_checkout(req)
        self.assertIsNone(checkout.user)
        self.assertEqual(checkout.session_key, req.session.session_key)

    def test_update_shipping_address(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        checkout = get_or_create_checkout(req)

        address_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "company_name": "House of Bore",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        }

        update_shipping(checkout, address_data)
        self.assertIsNotNone(checkout.shipping_address)
        self.assertEqual(checkout.shipping_address.recipient_name, "Jane Doe")
        self.assertEqual(checkout.shipping_address.city, "Beverly Hills")

    def test_update_billing_same_as_shipping(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        checkout = get_or_create_checkout(req)

        address_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        }
        update_shipping(checkout, address_data)

        # Set billing same as shipping
        update_billing(checkout, {}, billing_same_as_shipping=True)
        self.assertTrue(checkout.billing_same_as_shipping)
        self.assertIsNone(checkout.billing_address)

        # Verify selectors resolve correctly
        billing_addr = get_billing_address(checkout)
        self.assertEqual(billing_addr, checkout.shipping_address)

    def test_update_billing_custom_address(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        checkout = get_or_create_checkout(req)

        billing_data = {
            "recipient_name": "John Smith",
            "phone_number": "+15559876543",
            "address_line_1": "456 Custom Lane",
            "city": "Seattle",
            "county_or_state": "WA",
            "postal_code": "98101",
            "country": "US",
        }
        update_billing(checkout, billing_data, billing_same_as_shipping=False)
        self.assertFalse(checkout.billing_same_as_shipping)
        self.assertIsNotNone(checkout.billing_address)
        self.assertEqual(checkout.billing_address.recipient_name, "John Smith")

    def test_validate_checkout_constraints(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        req.user = self.user
        checkout = get_or_create_checkout(req)

        # 1. Empty cart fails validation
        with self.assertRaises(ValidationError):
            validate_checkout(checkout)

        # 2. Add product to cart
        add_to_cart(req, product_id=self.product.pk, quantity=2)

        # Missing shipping fails validation
        with self.assertRaises(ValidationError):
            validate_checkout(checkout)

        # 3. Add shipping address
        shipping_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        }
        update_shipping(checkout, shipping_data)
        
        # Validation passes since billing_same_as_shipping is True
        validate_checkout(checkout)

        # 4. Quantity exceeds stock limit
        item = checkout.cart.items.first()
        item.quantity = 50
        item.save()
        with self.assertRaises(ValidationError):
            validate_checkout(checkout)

        # Restore quantity
        item.quantity = 2
        item.save()

        # 5. Inactive product fails validation
        self.inactive_product.is_active = True
        self.inactive_product.save()
        add_to_cart(req, product_id=self.inactive_product.pk, quantity=1)
        self.inactive_product.is_active = False
        self.inactive_product.save()
        with self.assertRaises(ValidationError):
            validate_checkout(checkout)


class CheckoutViewsAndFormsTests(CheckoutBaseTestCase):
    """
    Integration tests covering Forms, URLs routing, and Class-Based Views.
    """
    def test_start_checkout_with_empty_cart_redirects(self):
        res = self.client.get(reverse("checkout:start"))
        self.assertRedirects(res, reverse("cart:cart_detail"))

    def test_shipping_view_rendering_and_submission(self):
        # Add item to bag
        self.client.force_login(self.user)
        self.client.post(reverse("cart:add", kwargs={"product_id": self.product.pk}), {"quantity": 2})

        # Render shipping view
        res = self.client.get(reverse("checkout:shipping"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "checkout/shipping.html")

        # Submit shipping form
        shipping_post_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Main St",
            "city": "Los Angeles",
            "county_or_state": "CA",
            "postal_code": "90001",
            "country": "US",
            "notes": "Please leave at door.",
        }
        res_post = self.client.post(reverse("checkout:shipping"), shipping_post_data)
        self.assertRedirects(res_post, reverse("checkout:billing"))

        # Verify snapshotted address details
        checkout = Cart.objects.get(user=self.user).checkout_session
        self.assertIsNotNone(checkout.shipping_address)
        self.assertEqual(checkout.shipping_address.recipient_name, "Jane Doe")
        self.assertEqual(checkout.notes, "Please leave at door.")

    def test_billing_view_same_as_shipping_submission(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart:add", kwargs={"product_id": self.product.pk}), {"quantity": 1})

        # Submit shipping first
        shipping_post_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Main St",
            "city": "Los Angeles",
            "county_or_state": "CA",
            "postal_code": "90001",
            "country": "US",
        }
        self.client.post(reverse("checkout:shipping"), shipping_post_data)
        
        # Post billing same as shipping
        res = self.client.post(reverse("checkout:billing"), {"billing_same_as_shipping": "true"})
        self.assertRedirects(res, reverse("checkout:review"))

        checkout = Cart.objects.get(user=self.user).checkout_session
        self.assertTrue(checkout.billing_same_as_shipping)

    def test_billing_view_custom_address_submission(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart:add", kwargs={"product_id": self.product.pk}), {"quantity": 1})

        # Submit shipping first
        shipping_post_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Main St",
            "city": "Los Angeles",
            "county_or_state": "CA",
            "postal_code": "90001",
            "country": "US",
        }
        self.client.post(reverse("checkout:shipping"), shipping_post_data)

        billing_post_data = {
            "billing_same_as_shipping": "false",
            "recipient_name": "John Smith",
            "phone_number": "+15559876543",
            "address_line_1": "456 Custom Ln",
            "city": "Seattle",
            "county_or_state": "WA",
            "postal_code": "98101",
            "country": "US",
        }
        res = self.client.post(reverse("checkout:billing"), billing_post_data)
        self.assertRedirects(res, reverse("checkout:review"))

        checkout = Cart.objects.get(user=self.user).checkout_session
        self.assertFalse(checkout.billing_same_as_shipping)
        self.assertIsNotNone(checkout.billing_address)
        self.assertEqual(checkout.billing_address.recipient_name, "John Smith")

    def test_saved_address_re_use_in_checkout(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart:add", kwargs={"product_id": self.product.pk}), {"quantity": 1})

        # Save an address in profile Address Book
        saved_addr = Address.objects.create(
            user=self.user,
            label="Home",
            recipient_name="Jane Doe Profile",
            phone_number="+15551234567",
            address_line_1="789 Profile Lane",
            city="New York",
            county_or_state="NY",
            postal_code="10001",
            country="US"
        )

        # Select saved address on shipping step
        res = self.client.post(reverse("checkout:shipping"), {"saved_address_id": saved_addr.pk})
        self.assertRedirects(res, reverse("checkout:billing"))

        # Verify address copy
        checkout = Cart.objects.get(user=self.user).checkout_session
        self.assertEqual(checkout.shipping_address.recipient_name, "Jane Doe Profile")
        self.assertEqual(checkout.shipping_address.address_line_1, "789 Profile Lane")

    def test_review_view_totals(self):
        self.client.force_login(self.user)
        self.client.post(reverse("cart:add", kwargs={"product_id": self.product.pk}), {"quantity": 2})

        # Complete shipping & billing info
        shipping_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        }
        self.client.post(reverse("checkout:shipping"), shipping_data)
        self.client.post(reverse("checkout:billing"), {"billing_same_as_shipping": "true"})

        # Load review page
        res = self.client.get(reverse("checkout:review"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "checkout/review.html")

        # Verify summary context variables
        self.assertEqual(res.context["checkout_totals"]["subtotal"], Decimal("900.00"))
        self.assertEqual(res.context["checkout_totals"]["grand_total"], Decimal("2544.00"))  # Includes 16% VAT and flat shipping via dynamic StoreSettings
        self.assertEqual(res.context["checkout_totals"]["item_count"], 2)


class CheckoutVariantTests(CheckoutBaseTestCase):
    """
    Test suite verifying checkout validations and review when cart items contain Product Variants.
    """
    def setUp(self):
        super().setUp()
        self.opt_size = ProductOption.objects.create(name="Size", display_name="Size", sort_order=1)
        self.val_40 = ProductOptionValue.objects.create(option=self.opt_size, value="40R", display_order=1)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="ATELIER-40R",
            price_override=Decimal("480.00"),
            stock_quantity=5,
            is_active=True
        )
        ProductVariantOption.objects.create(variant=self.variant, option_value=self.val_40)

    def test_validate_checkout_with_variant_stock_exceeded(self):
        """Verify validate_checkout raises ValidationError when variant stock is exceeded."""
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product.pk, quantity=3, variant_id=self.variant.pk)

        checkout_session = get_or_create_checkout(req)
        update_shipping(checkout_session, {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        })
        update_billing(checkout_session, {}, billing_same_as_shipping=True)

        # Reduce variant stock below requested quantity
        self.variant.stock_quantity = 2
        self.variant.save()

        with self.assertRaises(ValidationError) as ctx:
            validate_checkout(checkout_session)
        self.assertIn("exceeds available stock", str(ctx.exception))

    def test_validate_checkout_with_inactive_variant(self):
        """Verify validate_checkout raises ValidationError when variant becomes inactive."""
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product.pk, quantity=1, variant_id=self.variant.pk)

        checkout_session = get_or_create_checkout(req)
        update_shipping(checkout_session, {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        })
        update_billing(checkout_session, {}, billing_same_as_shipping=True)

        self.variant.is_active = False
        self.variant.save()

        with self.assertRaises(ValidationError) as ctx:
            validate_checkout(checkout_session)
        self.assertIn("no longer active or available", str(ctx.exception))

    def test_review_view_with_variant_items(self):
        """Verify review screen renders item with variant details and accurate totals."""
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product.pk, quantity=2, variant_id=self.variant.pk)

        shipping_data = {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "123 Atelier Ave",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        }
        self.client.post(reverse("checkout:shipping"), shipping_data)
        self.client.post(reverse("checkout:billing"), {"billing_same_as_shipping": "true"})

        res = self.client.get(reverse("checkout:review"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ATELIER-40R")
        self.assertContains(res, "40R")

