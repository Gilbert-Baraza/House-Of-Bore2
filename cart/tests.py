# cart/tests.py
"""
cart/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for the Shopping Cart application.

Covers models, constraints, selectors, services, session merging upon login,
Class-Based Views, security isolation, stock validation, and context processor.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.contrib.sessions.middleware import SessionMiddleware

from products.models import Brand, Category, Product
from cart.models import Cart, CartItem
from cart.selectors import (
    get_cart,
    get_cart_items,
    cart_item_count,
    cart_total,
)
from cart.services import (
    get_or_create_cart,
    add_to_cart,
    update_quantity,
    remove_from_cart,
    clear_cart,
    merge_carts,
    calculate_totals,
)
from cart.context_processors import cart as cart_context_processor

User = get_user_model()


class CartBaseTestCase(TestCase):
    """
    Base setup creating test users, categories, brands, and catalog products.
    """
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="customer@example.com",
            password="SecurePassword123!",
            first_name="Jane",
            last_name="Doe",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="SecurePassword123!",
            first_name="John",
            last_name="Smith",
        )
        self.category = Category.objects.create(
            name="Haute Couture",
            slug="haute-couture",
            is_active=True,
        )
        self.brand = Brand.objects.create(
            name="Atelier Bore",
            slug="atelier-bore",
            is_active=True,
        )
        self.product1 = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Silk Trench Coat",
            slug="silk-trench-coat",
            price=Decimal("2500.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.product2 = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Cashmere Sweater",
            slug="cashmere-sweater",
            price=Decimal("1200.00"),
            stock_quantity=5,
            is_active=True,
        )
        self.out_of_stock_product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Limited Edition Watch",
            slug="limited-edition-watch",
            price=Decimal("15000.00"),
            stock_quantity=0,
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Archived Scarf",
            slug="archived-scarf",
            price=Decimal("450.00"),
            stock_quantity=10,
            is_active=False,
        )

    def add_session_to_request(self, request):
        """Helper to attach session middleware to RequestFactory requests."""
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request


class CartModelTests(CartBaseTestCase):
    """
    Test database constraints, validation rules, and subtotal calculations.
    """
    def test_cart_creation_user_and_guest(self):
        user_cart = Cart.objects.create(user=self.user)
        self.assertEqual(user_cart.user, self.user)
        self.assertIn("User: customer@example.com", str(user_cart))

        guest_cart = Cart.objects.create(session_key="testsessionkey123")
        self.assertEqual(guest_cart.session_key, "testsessionkey123")
        self.assertIn("Guest:", str(guest_cart))

    def test_cart_clean_requires_user_or_session(self):
        cart = Cart()
        with self.assertRaises(ValidationError):
            cart.clean()

    def test_one_active_cart_per_user_constraint(self):
        Cart.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            Cart.objects.create(user=self.user)

    def test_one_active_cart_per_session_constraint(self):
        Cart.objects.create(session_key="unique_session_key")
        with self.assertRaises(IntegrityError):
            Cart.objects.create(session_key="unique_session_key")

    def test_cart_item_subtotal_and_cart_totals(self):
        cart = Cart.objects.create(user=self.user)
        item1 = CartItem.objects.create(
            cart=cart,
            product=self.product1,
            quantity=2,
            unit_price=self.product1.price
        )
        item2 = CartItem.objects.create(
            cart=cart,
            product=self.product2,
            quantity=1,
            unit_price=self.product2.price
        )

        self.assertEqual(item1.subtotal(), Decimal("5000.00"))
        self.assertEqual(item2.subtotal(), Decimal("1200.00"))
        self.assertEqual(cart.subtotal(), Decimal("6200.00"))
        self.assertEqual(cart.item_count(), 3)

    def test_cart_item_unique_product_per_cart(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product1, quantity=1, unit_price=Decimal("2500.00"))
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(cart=cart, product=self.product1, quantity=2, unit_price=Decimal("2500.00"))

    def test_cart_item_clean_validation(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem(cart=cart, product=self.product1, quantity=0, unit_price=Decimal("2500.00"))
        with self.assertRaises(ValidationError):
            item.clean()

        item_neg_price = CartItem(cart=cart, product=self.product1, quantity=1, unit_price=Decimal("-10.00"))
        with self.assertRaises(ValidationError):
            item_neg_price.clean()


class CartSelectorsTests(CartBaseTestCase):
    """
    Test read-only selector queries and prefetching.
    """
    def test_get_cart_authenticated_and_guest(self):
        user_cart = Cart.objects.create(user=self.user)
        req_user = self.factory.get("/")
        req_user.user = self.user
        self.assertEqual(get_cart(req_user), user_cart)

        guest_cart = Cart.objects.create(session_key="guestsessionabc")
        req_guest = self.factory.get("/")
        req_guest = self.add_session_to_request(req_guest)
        req_guest.session._session_key = "guestsessionabc"
        self.assertEqual(get_cart(req_guest), guest_cart)

    def test_get_cart_returns_none_when_empty(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        self.assertIsNone(get_cart(req))

    def test_cart_selectors_empty_handling(self):
        self.assertEqual(get_cart_items(None), [])
        self.assertEqual(cart_item_count(None), 0)
        self.assertEqual(cart_total(None), Decimal("0.00"))


class CartServicesTests(CartBaseTestCase):
    """
    Test business operations: adding, updating, removing, clearing, and stock validation.
    """
    def test_get_or_create_cart_guest_session_initialization(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        self.assertIsNotNone(req.session.session_key)
        
        cart = get_or_create_cart(req)
        self.assertEqual(cart.session_key, req.session.session_key)
        self.assertIsNone(cart.user)

    def test_add_to_cart_success_and_quantity_increment(self):
        req = self.factory.get("/")
        req.user = self.user
        
        item = add_to_cart(req, product_id=self.product1.pk, quantity=2)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, self.product1.price)

        # Increment existing item
        item_updated = add_to_cart(req, product_id=self.product1.pk, quantity=3)
        self.assertEqual(item_updated.quantity, 5)

    def test_add_to_cart_stock_and_status_validation(self):
        req = self.factory.get("/")
        req.user = self.user

        with self.assertRaises(ValidationError):
            add_to_cart(req, product_id=self.out_of_stock_product.pk, quantity=1)

        with self.assertRaises(ValidationError):
            add_to_cart(req, product_id=self.inactive_product.pk, quantity=1)

        with self.assertRaises(ValidationError):
            add_to_cart(req, product_id=self.product1.pk, quantity=50)

    def test_update_quantity_and_removal(self):
        req = self.factory.get("/")
        req.user = self.user
        item = add_to_cart(req, product_id=self.product1.pk, quantity=2)

        updated = update_quantity(req, item_id=item.pk, quantity=4)
        self.assertEqual(updated.quantity, 4)

        # Updating to 0 removes item
        removed_item = update_quantity(req, item_id=item.pk, quantity=0)
        self.assertIsNone(removed_item)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_remove_from_cart_and_clear_cart(self):
        req = self.factory.get("/")
        req.user = self.user
        item1 = add_to_cart(req, product_id=self.product1.pk, quantity=1)
        item2 = add_to_cart(req, product_id=self.product2.pk, quantity=1)

        self.assertTrue(remove_from_cart(req, item_id=item1.pk))
        self.assertFalse(remove_from_cart(req, item_id=9999))  # Non-existent ID
        self.assertEqual(CartItem.objects.count(), 1)

        clear_cart(req)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_calculate_totals_formatting(self):
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product1.pk, quantity=2)
        add_to_cart(req, product_id=self.product2.pk, quantity=1)

        cart = get_cart(req)
        totals = calculate_totals(cart)
        self.assertEqual(totals["item_count"], 3)
        self.assertEqual(totals["subtotal"], Decimal("6200.00"))
        self.assertFalse(totals["is_empty"])


class CartMergeTests(CartBaseTestCase):
    """
    Test guest session cart merging into authenticated user carts upon login.
    """
    def test_merge_carts_when_user_has_no_cart(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        guest_cart = get_or_create_cart(req)
        add_to_cart(req, product_id=self.product1.pk, quantity=2)

        merged_cart = merge_carts(req, self.user)
        self.assertEqual(merged_cart.user, self.user)
        self.assertIsNone(merged_cart.session_key)
        self.assertEqual(merged_cart.item_count(), 2)

    def test_merge_carts_with_duplicate_products_and_clamping(self):
        # 1. Create guest cart with 8x product1
        req_guest = self.factory.get("/")
        req_guest = self.add_session_to_request(req_guest)
        guest_cart = get_or_create_cart(req_guest)
        add_to_cart(req_guest, product_id=self.product1.pk, quantity=8)
        add_to_cart(req_guest, product_id=self.product2.pk, quantity=2)

        # 2. Create existing user cart with 4x product1 (stock limit is 10)
        user_cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=user_cart, product=self.product1, quantity=4, unit_price=self.product1.price)

        # 3. Perform merge
        merged_cart = merge_carts(req_guest, self.user)
        self.assertEqual(merged_cart, user_cart)
        self.assertFalse(Cart.objects.filter(pk=guest_cart.pk).exists())

        # Check product1 quantity is clamped to max stock (10) instead of 12
        item1 = merged_cart.items.get(product=self.product1)
        self.assertEqual(item1.quantity, 10)

        # Check product2 was transferred cleanly
        item2 = merged_cart.items.get(product=self.product2)
        self.assertEqual(item2.quantity, 2)

    def test_user_logged_in_signal_triggers_merge(self):
        req = self.factory.get("/")
        req = self.add_session_to_request(req)
        add_to_cart(req, product_id=self.product1.pk, quantity=3)

        # Send signal
        user_logged_in.send(sender=self.user.__class__, request=req, user=self.user)
        
        user_cart = Cart.objects.get(user=self.user)
        self.assertEqual(user_cart.item_count(), 3)


class CartViewsAndURLsTests(CartBaseTestCase):
    """
    Test Class-Based Views, URL routing, flash messages, and redirects.
    """
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_cart_detail_view_empty_and_populated(self):
        response_empty = self.client.get(reverse("cart:cart_detail"))
        self.assertEqual(response_empty.status_code, 200)
        self.assertTemplateUsed(response_empty, "cart/cart_empty.html")

        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product1.pk, quantity=1)

        response_populated = self.client.get(reverse("cart:cart_detail"))
        self.assertEqual(response_populated.status_code, 200)
        self.assertTemplateUsed(response_populated, "cart/cart_detail.html")
        self.assertIn("cart_items", response_populated.context)
        self.assertIn("cart_totals", response_populated.context)

    def test_add_to_cart_view_post_and_get(self):
        url = reverse("cart:add", kwargs={"product_id": self.product1.pk})
        
        # GET should redirect to cart detail
        res_get = self.client.get(url)
        self.assertRedirects(res_get, reverse("cart:cart_detail"))

        # POST adds item
        res_post = self.client.post(url, {"quantity": 2}, follow=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertContains(res_post, "Added Silk Trench Coat to your shopping bag.")

    def test_update_cart_item_view_post(self):
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        item = add_to_cart(req, product_id=self.product1.pk, quantity=1)

        url = reverse("cart:update", kwargs={"item_id": item.pk})
        res = self.client.post(url, {"quantity": 4}, follow=True)
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)
        self.assertContains(res, "Updated quantity for Silk Trench Coat.")

    def test_remove_cart_item_view_post(self):
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        item = add_to_cart(req, product_id=self.product1.pk, quantity=1)

        url = reverse("cart:remove", kwargs={"item_id": item.pk})
        res = self.client.post(url, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertContains(res, "Item removed from your shopping bag.")

    def test_clear_cart_view_post(self):
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product1.pk, quantity=1)
        add_to_cart(req, product_id=self.product2.pk, quantity=1)

        url = reverse("cart:clear")
        res = self.client.post(url, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertContains(res, "Your shopping bag has been emptied.")


class CartSecurityAndIsolationTests(CartBaseTestCase):
    """
    Test security rules: user cart isolation and guest session isolation.
    """
    def test_user_cannot_access_other_users_cart_items(self):
        # User 1 has product1
        req1 = self.factory.get("/")
        req1.user = self.user
        item1 = add_to_cart(req1, product_id=self.product1.pk, quantity=2)

        # Case 1: User 2 has no cart yet and tries to update User 1's item
        self.client.force_login(self.other_user)
        url_update = reverse("cart:update", kwargs={"item_id": item1.pk})
        res1 = self.client.post(url_update, {"quantity": 5}, follow=True)
        self.assertContains(res1, "Shopping cart not found.")

        # Case 2: User 2 has their own cart and tries to update User 1's item
        Cart.objects.create(user=self.other_user)
        res2 = self.client.post(url_update, {"quantity": 5}, follow=True)
        self.assertContains(res2, "Cart item not found.")
        
        item1.refresh_from_db()
        self.assertEqual(item1.quantity, 2)  # Unchanged


class CartContextProcessorTests(CartBaseTestCase):
    """
    Test global template context processor availability.
    """
    def test_context_processor_injects_cart_metrics(self):
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product1.pk, quantity=3)

        ctx = cart_context_processor(req)
        self.assertIn("cart", ctx)
        self.assertEqual(ctx["cart_item_count"], 3)
        self.assertEqual(ctx["cart_subtotal"], Decimal("7500.00"))


class CartRefactoredFeatureTests(CartBaseTestCase):
    """
    Integration and unit tests verifying refactored shopping cart features,
    specifically session cycling during login, relative action-based updates,
    and N+1 prefetch optimizations.
    """
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_merge_carts_on_actual_login_with_key_rotation(self):
        # 1. Start guest session and add product to guest cart
        self.client.get("/")
        guest_session_key_initial = self.client.session.session_key
        
        url_add = reverse("cart:add", kwargs={"product_id": self.product1.pk})
        self.client.post(url_add, {"quantity": 2})
        
        # Verify guest cart exists and is associated with initial session key
        guest_cart = Cart.objects.get(session_key=guest_session_key_initial)
        self.assertEqual(guest_cart.item_count(), 2)

        # 2. Log in using the test client, triggering Django session cycling
        url_login = reverse("accounts:login")
        res = self.client.post(url_login, {
            "email": "customer@example.com",
            "password": "SecurePassword123!",
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        # Verify key rotation: session key has changed
        guest_session_key_after = self.client.session.session_key
        self.assertNotEqual(guest_session_key_initial, guest_session_key_after)

        # Verify guest cart has been merged into the authenticated user's cart
        user_cart = Cart.objects.get(user=self.user)
        self.assertEqual(user_cart.item_count(), 2)

        # Verify the guest cart is deleted from the database
        self.assertFalse(Cart.objects.filter(session_key=guest_session_key_initial).exists())

    def test_action_based_quantity_updates(self):
        self.client.force_login(self.user)
        req = self.factory.get("/")
        req.user = self.user
        item = add_to_cart(req, product_id=self.product1.pk, quantity=3)

        # Simulate relative decrease post request
        url_update = reverse("cart:update", kwargs={"item_id": item.pk})
        res_dec = self.client.post(url_update, {"action": "decrease", "quantity": "3"})
        self.assertEqual(res_dec.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        # Simulate relative increase post request
        res_inc = self.client.post(url_update, {"action": "increase", "quantity": "2"})
        self.assertEqual(res_inc.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

        # Simulate direct input post request (no action param)
        res_direct = self.client.post(url_update, {"quantity": "5"})
        self.assertEqual(res_direct.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_primary_image_prefetch_no_n_plus_one(self):
        req = self.factory.get("/")
        req.user = self.user
        add_to_cart(req, product_id=self.product1.pk, quantity=1)
        add_to_cart(req, product_id=self.product2.pk, quantity=1)

        # Fetch cart using selectors to trigger prefetching
        cart_obj = get_cart(req)
        
        # Accessing get_primary_image() on all prefetched products should not hit database
        with self.assertNumQueries(0):
            for item in cart_obj.items.all():
                item.product.get_primary_image()
