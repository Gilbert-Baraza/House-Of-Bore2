# pricing/tests.py
"""
pricing/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for the Pricing, Promotions & Discounts engine.
Tests model rules, calculation accuracy, rounding invariants, coupon application,
shipping thresholds, tax regional logic, and view endpoints.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from cart.models import Cart, CartItem
from checkout.models import CheckoutAddress
from pricing.models import Coupon, Promotion, CouponUsageLog
from pricing.services import (
    quantize_money,
    calculate_subtotal,
    calculate_discount,
    calculate_coupon,
    calculate_shipping,
    calculate_tax,
    calculate_total,
    pricing_breakdown,
    apply_coupon_to_cart,
    remove_coupon_from_cart,
    record_and_increment_coupon_usage,
)
from products.models import Brand, Category, Product

User = get_user_model()


class CouponModelTests(TestCase):
    """
    Unit tests for Coupon validation and status helper methods.
    """
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_clean_validation(self):
        coupon = Coupon(code="NEG", discount_type="fixed", discount_value=Decimal("-10.00"))
        with self.assertRaises(ValidationError):
            coupon.clean()

        coupon_pct = Coupon(code="OVER", discount_type="percentage", discount_value=Decimal("150.00"))
        with self.assertRaises(ValidationError):
            coupon_pct.clean()

    def test_validity_checks(self):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="SUMMER20",
            discount_type="percentage",
            discount_value=Decimal("20.00"),
            minimum_order_amount=Decimal("50.00"),
            active=True
        )
        self.assertTrue(coupon.is_valid_now())
        self.assertFalse(coupon.is_valid_for_subtotal(Decimal("40.00")))
        self.assertTrue(coupon.is_valid_for_subtotal(Decimal("60.00")))

        # Expired
        coupon.expires_at = now - timedelta(days=1)
        coupon.save()
        self.assertFalse(coupon.is_valid_now())

        # Usage cap reached
        coupon.expires_at = None
        coupon.usage_limit = 5
        coupon.usage_count = 5
        coupon.save()
        self.assertFalse(coupon.is_valid_now())


class PromotionModelTests(TestCase):
    """
    Unit tests for Promotion model behaviors.
    """
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_promotion_validity_window(self):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="Flash Sale",
            promotion_type="store_wide",
            discount_type="percentage",
            discount_value=Decimal("15.00"),
            starts_at=now - timedelta(hours=2),
            expires_at=now + timedelta(hours=2),
            active=True
        )
        self.assertTrue(promo.is_valid_now())

        promo.active = False
        promo.save()
        self.assertFalse(promo.is_valid_now())


class PricingServicesTests(TestCase):
    """
    Core engine unit tests verifying financial formulas and quantization.
    """
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="buyer@example.com", password="password123")
        self.brand = Brand.objects.create(name="Luxury House", slug="luxury-house")
        self.cat = Category.objects.create(name="Apparel", slug="apparel")
        self.product = Product.objects.create(
            brand=self.brand,
            category=self.cat,
            name="Silk Trench",
            slug="silk-trench",
            price=Decimal("100.00")
        )
        self.cart = Cart.objects.create(user=self.user)
        self.item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=2,
            unit_price=self.product.price
        )  # Subtotal = $200.00

    def test_quantize_money(self):
        self.assertEqual(quantize_money(Decimal("10.004")), Decimal("10.00"))
        self.assertEqual(quantize_money(Decimal("10.005")), Decimal("10.01"))

    def test_calculate_subtotal(self):
        self.assertEqual(calculate_subtotal(self.cart), Decimal("200.00"))
        self.assertEqual(calculate_subtotal(None), Decimal("0.00"))

    def test_calculate_discount_store_wide_percentage(self):
        Promotion.objects.create(
            name="10% Off Everything",
            promotion_type="store_wide",
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            active=True
        )
        discount, applied = calculate_discount(Decimal("200.00"), self.cart)
        self.assertEqual(discount, Decimal("20.00"))
        self.assertEqual(len(applied), 1)

    def test_calculate_discount_category_fixed(self):
        promo = Promotion.objects.create(
            name="$15 Off Apparel",
            promotion_type="category",
            discount_type="fixed",
            discount_value=Decimal("15.00"),
            active=True
        )
        promo.categories.add(self.cat)
        # $15 off per unit for 2 units of Apparel = $30.00
        discount, applied = calculate_discount(Decimal("200.00"), self.cart)
        self.assertEqual(discount, Decimal("30.00"))

    def test_calculate_coupon(self):
        coupon = Coupon.objects.create(
            code="SAVE25",
            discount_type="percentage",
            discount_value=Decimal("25.00"),
            maximum_discount_amount=Decimal("30.00")
        )
        # 25% of $200 is $50, capped at $30
        res = calculate_coupon(Decimal("200.00"), coupon)
        self.assertEqual(res, Decimal("30.00"))

    def test_calculate_shipping_thresholds(self):
        self.assertEqual(calculate_shipping(Decimal("49999.99")), Decimal("1500.00"))
        self.assertEqual(calculate_shipping(Decimal("50000.00")), Decimal("0.00"))
        self.assertEqual(calculate_shipping(Decimal("50.00"), shipping_method="express"), Decimal("2250.00"))

    def test_calculate_tax_regional(self):
        # Default store tax percentage is 16.00%
        self.assertEqual(calculate_tax(Decimal("100.00"), None), Decimal("16.00"))

    def test_pricing_breakdown_full_pipeline(self):
        coupon = Coupon.objects.create(
            code="FIXED20",
            discount_type="fixed",
            discount_value=Decimal("20.00"),
            minimum_order_amount=Decimal("100.00")
        )
        self.cart.coupon = coupon
        self.cart.save()

        breakdown = pricing_breakdown(self.cart)
        self.assertEqual(breakdown["subtotal"], Decimal("200.00"))
        self.assertEqual(breakdown["coupon_discount"], Decimal("20.00"))
        # $180 remaining < $50000 free shipping threshold -> $1500 shipping
        self.assertEqual(breakdown["shipping"], Decimal("1500.00"))
        # Tax default 16% of $180 = $28.80
        self.assertEqual(breakdown["tax"], Decimal("28.80"))
        # Grand total = $180 + $1500 + $28.80 = $1708.80
        self.assertEqual(breakdown["grand_total"], Decimal("1708.80"))

    def test_coupon_application_and_removal(self):
        coupon = Coupon.objects.create(
            code="VIP100",
            discount_type="fixed",
            discount_value=Decimal("100.00"),
            minimum_order_amount=Decimal("150.00")
        )
        applied = apply_coupon_to_cart(self.cart, "vip100")
        self.assertEqual(applied, coupon)
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.coupon, coupon)

        remove_coupon_from_cart(self.cart)
        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.coupon)

    def tearDown(self):
        cache.clear()


class PricingViewsTests(TestCase):
    """
    Integration tests for coupon application endpoints.
    """
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(email="shopper@example.com", password="password123")
        self.client.force_login(self.user)
        self.brand = Brand.objects.create(name="House", slug="house")
        self.cat = Category.objects.create(name="Bags", slug="bags")
        self.product = Product.objects.create(
            brand=self.brand,
            category=self.cat,
            name="Leather Tote",
            slug="leather-tote",
            price=Decimal("300.00")
        )
        self.cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1, unit_price=self.product.price)
        self.coupon = Coupon.objects.create(
            code="WELCOME50",
            discount_type="fixed",
            discount_value=Decimal("50.00"),
            active=True
        )

    def tearDown(self):
        cache.clear()

    def test_apply_coupon_view_success(self):
        url = reverse("pricing:apply_coupon")
        resp = self.client.post(url, {"code": "WELCOME50", "next": reverse("cart:cart_detail")})
        self.assertRedirects(resp, reverse("cart:cart_detail"))
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.coupon, self.coupon)

    def test_apply_coupon_view_invalid(self):
        url = reverse("pricing:apply_coupon")
        resp = self.client.post(url, {"code": "INVALID_CODE"})
        self.assertEqual(resp.status_code, 302)
        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.coupon)

    def test_remove_coupon_view(self):
        self.cart.coupon = self.coupon
        self.cart.save()
        url = reverse("pricing:remove_coupon")
        resp = self.client.post(url, {"next": reverse("cart:cart_detail")})
        self.assertRedirects(resp, reverse("cart:cart_detail"))
        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.coupon)


class PricingImprovementsTests(TestCase):
    """
    Test suite for architectural improvements: atomic coupon usage logging,
    cart breakdown caching, and Free Shipping progress bar calculations.
    """
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="luxury_shopper@example.com", password="password123")
        self.brand = Brand.objects.create(name="Atelier Brand", slug="atelier-brand")
        self.cat = Category.objects.create(name="Handbags", slug="handbags")
        self.product = Product.objects.create(
            brand=self.brand,
            category=self.cat,
            name="Atelier Tote",
            slug="atelier-tote",
            price=Decimal("100.00"),
            stock_quantity=50
        )
        self.cart = Cart.objects.create(user=self.user)
        self.item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
            unit_price=self.product.price
        )

    def test_record_and_increment_coupon_usage_atomic(self):
        coupon = Coupon.objects.create(
            code="ATELIER50",
            discount_type="fixed",
            discount_value=Decimal("50.00"),
            usage_limit=1,
            usage_count=0
        )
        # First redemption should succeed
        record_and_increment_coupon_usage("ATELIER50", user=self.user, order_id="ORD-1001", discount_amount=Decimal("50.00"))
        coupon.refresh_from_db()
        self.assertEqual(coupon.usage_count, 1)
        self.assertEqual(CouponUsageLog.objects.count(), 1)
        log = CouponUsageLog.objects.first()
        self.assertEqual(log.coupon, coupon)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.order_id, "ORD-1001")
        self.assertEqual(log.discount_amount, Decimal("50.00"))

        # Second redemption should fail due to usage limit reaching cap
        with self.assertRaises(ValidationError):
            record_and_increment_coupon_usage("ATELIER50", user=self.user, order_id="ORD-1002", discount_amount=Decimal("50.00"))

    def test_request_lifecycle_breakdown_caching(self):
        breakdown1 = pricing_breakdown(self.cart)
        self.assertTrue(hasattr(self.cart, "_cached_breakdown"))
        self.assertEqual(self.cart._cached_breakdown, breakdown1)

        # Modifying item should clear cache when item is saved
        self.item.quantity = 2
        self.item.save()
        self.assertFalse(hasattr(self.cart, "_cached_breakdown"))

        breakdown2 = pricing_breakdown(self.cart)
        self.assertEqual(breakdown2["subtotal"], Decimal("200.00"))
        self.assertTrue(hasattr(self.cart, "_cached_breakdown"))

    def test_free_shipping_progress_metrics(self):
        # 1 unit @ $100.00 -> subtotal $100.00, threshold $50000.00 -> remaining $49900.00
        breakdown = pricing_breakdown(self.cart)
        self.assertEqual(breakdown["free_shipping_threshold"], Decimal("50000.00"))
        self.assertEqual(breakdown["free_shipping_remaining"], Decimal("49900.00"))
        self.assertEqual(breakdown["free_shipping_progress_pct"], 0) # int(100/50000 * 100) = 0%

        # Increase quantity to 500 units @ $100.00 = $50000.00 -> free shipping unlocked!
        self.item.quantity = 500
        self.item.save()
        breakdown2 = pricing_breakdown(self.cart)
        self.assertEqual(breakdown2["free_shipping_remaining"], Decimal("0.00"))
        self.assertEqual(breakdown2["free_shipping_progress_pct"], 100)

    def test_dynamic_shipping_and_tax_from_store_settings(self):
        from settings.models import StoreSettings
        st = StoreSettings.load()
        st.free_shipping_threshold = Decimal("250.00")
        st.flat_shipping_rate = Decimal("25.00")
        st.tax_percentage = Decimal("10.00")
        st.save()

        # Item at $100 -> shipping should be $25.00, threshold remaining $150.00
        self.item.quantity = 1
        self.item.save()
        breakdown = pricing_breakdown(self.cart)
        self.assertEqual(breakdown["shipping"], Decimal("25.00"))
        self.assertEqual(breakdown["free_shipping_threshold"], Decimal("250.00"))
        self.assertEqual(breakdown["free_shipping_remaining"], Decimal("150.00"))

    def tearDown(self):
        cache.clear()

