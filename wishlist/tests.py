# wishlist/tests.py
"""
wishlist/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for the Wishlist application.

Covers models, constraints, signals, selectors, caching, services, views,
permissions, and template rendering.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Brand, Category, Product
from wishlist.models import Wishlist, WishlistItem
from wishlist.selectors import (
    get_user_wishlist,
    get_user_wishlist_product_ids,
    get_wishlist_products,
    wishlist_contains,
)
from wishlist.services import add_to_wishlist, clear_wishlist, remove_from_wishlist

User = get_user_model()


class WishlistBaseTestCase(TestCase):
    """
    Base test setup creating test users, categories, brands, and products.
    """

    def setUp(self):
        cache.clear()
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
            name="Watches",
            slug="watches",
            is_active=True,
        )
        self.brand = Brand.objects.create(
            name="Rolex",
            slug="rolex",
            is_active=True,
        )
        self.product1 = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Submariner",
            slug="submariner",
            price=Decimal("12000.00"),
            stock_quantity=5,
            is_active=True,
        )
        self.product2 = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Daytona",
            slug="daytona",
            price=Decimal("35000.00"),
            stock_quantity=2,
            is_active=True,
        )


class WishlistModelTests(WishlistBaseTestCase):
    """
    Tests database models, helper methods, constraints, and cascading deletes.
    """

    def test_wishlist_creation_and_helpers(self):
        wishlist = Wishlist.objects.create(user=self.user)
        self.assertEqual(str(wishlist), f"Wishlist for {self.user}")
        self.assertEqual(wishlist.item_count(), 0)
        self.assertFalse(wishlist.contains(self.product1))

        # Add product
        item1 = wishlist.add_product(self.product1)
        self.assertEqual(wishlist.item_count(), 1)
        self.assertTrue(wishlist.contains(self.product1))
        self.assertEqual(str(item1), f"{self.product1.name} in {wishlist}")

        # Adding same product again should return existing item without duplicating
        item1_dup = wishlist.add_product(self.product1)
        self.assertEqual(item1.pk, item1_dup.pk)
        self.assertEqual(wishlist.item_count(), 1)

        # Remove product
        removed = wishlist.remove_product(self.product1)
        self.assertTrue(removed)
        self.assertEqual(wishlist.item_count(), 0)
        self.assertFalse(wishlist.contains(self.product1))

        # Removing again returns False
        self.assertFalse(wishlist.remove_product(self.product1))

    def test_unique_constraint(self):
        wishlist = Wishlist.objects.create(user=self.user)
        WishlistItem.objects.create(wishlist=wishlist, product=self.product1)
        with self.assertRaises(IntegrityError):
            WishlistItem.objects.create(wishlist=wishlist, product=self.product1)

    def test_cascading_deletes(self):
        wishlist = Wishlist.objects.create(user=self.user)
        wishlist.add_product(self.product1)
        wishlist.add_product(self.product2)
        self.assertEqual(WishlistItem.objects.count(), 2)

        # Deleting product deletes its wishlist item
        self.product1.delete()
        self.assertEqual(WishlistItem.objects.count(), 1)
        self.assertEqual(wishlist.item_count(), 1)

        # Deleting user deletes wishlist and remaining items
        self.user.delete()
        self.assertEqual(Wishlist.objects.count(), 0)
        self.assertEqual(WishlistItem.objects.count(), 0)


class WishlistSelectorAndServiceTests(WishlistBaseTestCase):
    """
    Tests selectors, caching layer, and business services.
    """

    def test_services_auto_create_wishlist(self):
        self.assertFalse(Wishlist.objects.filter(user=self.user).exists())
        item, created = add_to_wishlist(self.user, self.product1)
        self.assertTrue(created)
        self.assertTrue(Wishlist.objects.filter(user=self.user).exists())
        self.assertEqual(self.user.wishlist.item_count(), 1)

    def test_selectors_and_caching(self):
        add_to_wishlist(self.user, self.product1)
        
        # Test selectors
        wishlist = get_user_wishlist(self.user)
        self.assertIsNotNone(wishlist)
        products = get_wishlist_products(self.user)
        self.assertEqual(list(products), [self.product1])
        self.assertTrue(wishlist_contains(self.user, self.product1))
        self.assertFalse(wishlist_contains(self.user, self.product2))

        # Test ID caching
        ids_first_call = get_user_wishlist_product_ids(self.user)
        self.assertEqual(ids_first_call, {self.product1.pk})
        
        # Verify cache is set
        cache_key = f"user_wishlist_ids_{self.user.pk}"
        self.assertEqual(cache.get(cache_key), {self.product1.pk})

        # Add second item -> signal should invalidate cache
        add_to_wishlist(self.user, self.product2)
        self.assertIsNone(cache.get(cache_key))
        ids_second_call = get_user_wishlist_product_ids(self.user)
        self.assertEqual(ids_second_call, {self.product1.pk, self.product2.pk})

        # Remove item -> signal should invalidate cache
        remove_from_wishlist(self.user, self.product1)
        self.assertIsNone(cache.get(cache_key))
        self.assertEqual(get_user_wishlist_product_ids(self.user), {self.product2.pk})

        # Clear wishlist -> should invalidate cache and return count
        count = clear_wishlist(self.user)
        self.assertEqual(count, 1)
        self.assertEqual(get_user_wishlist_product_ids(self.user), set())


class WishlistViewTests(WishlistBaseTestCase):
    """
    Tests class-based views, URL routing, authentication protection, and flash messages.
    """

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_guest_redirected_to_login(self):
        urls = [
            reverse("wishlist:wishlist"),
            reverse("wishlist:add", args=[self.product1.pk]),
            reverse("wishlist:remove", args=[self.product1.pk]),
            reverse("wishlist:clear"),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

    def test_get_request_to_action_views_not_allowed(self):
        self.client.force_login(self.user)
        urls = [
            reverse("wishlist:add", args=[self.product1.pk]),
            reverse("wishlist:remove", args=[self.product1.pk]),
            reverse("wishlist:clear"),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405)

    def test_wishlist_page_rendering(self):
        self.client.force_login(self.user)
        
        # Empty state
        response = self.client.get(reverse("wishlist:wishlist"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wishlist/wishlist.html")
        self.assertContains(response, "Your Wishlist is Empty")

        # Populated state
        add_to_wishlist(self.user, self.product1)
        response = self.client.get(reverse("wishlist:wishlist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submariner")
        self.assertContains(response, "Clear Wishlist")

    def test_add_to_wishlist_view(self):
        self.client.force_login(self.user)
        url = reverse("wishlist:add", args=[self.product1.pk])
        
        # POST request
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(wishlist_contains(self.user, self.product1))
        self.assertContains(response, "has been added to your wishlist")

        # Adding again shows info message
        response = self.client.post(url, follow=True)
        self.assertContains(response, "is already in your wishlist")

    def test_remove_from_wishlist_view(self):
        self.client.force_login(self.user)
        add_to_wishlist(self.user, self.product1)
        url = reverse("wishlist:remove", args=[self.product1.pk])
        
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(wishlist_contains(self.user, self.product1))
        self.assertContains(response, "has been removed from your wishlist")

    def test_clear_wishlist_view(self):
        self.client.force_login(self.user)
        add_to_wishlist(self.user, self.product1)
        add_to_wishlist(self.user, self.product2)
        url = reverse("wishlist:clear")
        
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_wishlist_products(self.user).count(), 0)
        self.assertContains(response, "Cleared 2 items from your wishlist")

    def test_context_processor_in_navbar(self):
        self.client.force_login(self.user)
        add_to_wishlist(self.user, self.product1)
        
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        # Check that context processor variables are present
        self.assertEqual(response.context["wishlist_count"], 1)
        self.assertIn(self.product1.pk, response.context["user_wishlist_ids"])

    def test_move_to_cart_view(self):
        self.client.force_login(self.user)
        add_to_wishlist(self.user, self.product1)
        url = reverse("wishlist:move_to_cart", args=[self.product1.pk])

        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        # Verify item removed from wishlist
        self.assertFalse(wishlist_contains(self.user, self.product1))
        # Verify item added to cart
        from cart.selectors import get_cart
        cart = get_cart(response.wsgi_request)
        self.assertTrue(cart.items.filter(product=self.product1).exists())
