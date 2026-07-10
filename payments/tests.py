# payments/tests.py
"""
payments/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for Phase 4.5 — Payment Processing & Gateway
Integration. Verifies database models, provider abstraction (`get_provider`),
gateway adapters (`PayPalProvider`, `MpesaProvider`, `StripeProvider`), payment
services (`process_success`, `deduct_inventory`), idempotency, and URL views.
──────────────────────────────────────────────────────────────────────────────
"""

import json
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from cart.services import add_to_cart
from checkout.services import get_or_create_checkout, update_billing, update_shipping
from orders.models import Order, OrderItem, OrderStatus
from orders.models import PaymentStatus as OrderPaymentStatus
from orders.services import create_order
from payments.models import GatewayChoices, Payment, PaymentStatus, PaymentWebhookLog
from payments.providers import get_provider
from payments.providers.base import BasePaymentProvider
from payments.providers.mpesa import MpesaProvider
from payments.providers.paypal import PayPalProvider
from payments.providers.stripe import StripeProvider
from payments.services import (
    clear_customer_cart,
    create_payment,
    deduct_inventory,
    generate_payment_reference,
    initiate_payment,
    process_failure,
    process_success,
    process_webhook_payload,
    verify_payment,
)
from products.models import Brand, Category, Product, ProductOption, ProductOptionValue, ProductVariant, ProductVariantOption

User = get_user_model()


class PaymentBaseTestCase(TestCase):
    """
    Common fixture setup for all payment and gateway integration tests.
    """
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()
        self.user = User.objects.create_user(
            email="payer@example.com",
            password="SecurePassword123!",
            first_name="Jane",
            last_name="Doe",
        )
        self.category = Category.objects.create(name="Suits", slug="suits", is_active=True)
        self.brand = Brand.objects.create(name="HOB Atelier", slug="hob-atelier", is_active=True)
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Classic Tuxedo",
            slug="classic-tuxedo",
            price=Decimal("1000.00"),
            stock_quantity=20,
            is_active=True,
        )
        self.opt_size = ProductOption.objects.create(name="Size", display_name="Size")
        self.val_40r = ProductOptionValue.objects.create(option=self.opt_size, value="40R", display_order=1)
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="TUX-BLK-40R",
            price_override=Decimal("1200.00"),
            stock_quantity=10,
            is_active=True,
        )
        ProductVariantOption.objects.create(variant=self.variant, option_value=self.val_40r)

    def setup_session(self, request):
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def create_test_order(self, quantity=2) -> Order:
        req = self.factory.get("/")
        self.setup_session(req)
        req.user = self.user
        checkout = get_or_create_checkout(req)
        add_to_cart(req, product_id=self.product.pk, quantity=quantity, variant_id=self.variant.pk)
        update_shipping(checkout, {
            "recipient_name": "Jane Doe",
            "phone_number": "+15551234567",
            "address_line_1": "100 Luxury Way",
            "city": "Beverly Hills",
            "county_or_state": "CA",
            "postal_code": "90210",
            "country": "US",
        })
        update_billing(checkout, {}, billing_same_as_shipping=True)
        return create_order(req, checkout)


class PaymentModelAndReferenceTests(PaymentBaseTestCase):
    """
    Verify `Payment` and `PaymentWebhookLog` model fields and unique reference generation.
    """
    def test_generate_payment_reference_uniqueness(self):
        ref1 = generate_payment_reference()
        order = self.create_test_order()
        Payment.objects.create(
            order=order,
            payment_reference=ref1,
            gateway=GatewayChoices.PAYPAL,
            amount=Decimal("100.00"),
        )
        ref2 = generate_payment_reference()
        self.assertTrue(ref1.startswith("PAY-"))
        self.assertNotEqual(ref1, ref2)

    def test_payment_and_webhook_model_lifecycle(self):
        order = self.create_test_order()
        payment = Payment.objects.create(
            order=order,
            payment_reference="PAY-20260710-TEST01",
            gateway=GatewayChoices.PAYPAL,
            amount=Decimal("2400.00"),
            currency="USD",
            status=PaymentStatus.PENDING,
        )
        self.assertEqual(payment.order, order)
        self.assertFalse(payment.is_completed)
        self.assertTrue(payment.is_pending_or_processing)
        self.assertIn("PAY-20260710-TEST01", str(payment))

        log_entry = PaymentWebhookLog.objects.create(
            gateway=GatewayChoices.PAYPAL,
            event_id="EVT-123",
            event_type="CHECKOUT.ORDER.APPROVED",
            payload={"id": "EVT-123", "status": "APPROVED"},
            status="processed",
        )
        self.assertEqual(log_entry.status, "processed")
        self.assertIn("EVT-123", str(log_entry))


class ProviderAbstractionLayerTests(PaymentBaseTestCase):
    """
    Verify the `get_provider()` factory and `BasePaymentProvider` common interface.
    """
    def test_get_provider_factory_instantiation(self):
        self.assertIsInstance(get_provider(GatewayChoices.PAYPAL), PayPalProvider)
        self.assertIsInstance(get_provider(GatewayChoices.MPESA), MpesaProvider)
        self.assertIsInstance(get_provider(GatewayChoices.STRIPE), StripeProvider)
        self.assertIsInstance(get_provider(GatewayChoices.MANUAL), BasePaymentProvider)

    def test_invalid_gateway_code_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            get_provider("invalid_gateway_name")

    def test_base_provider_refund_placeholder(self):
        provider = get_provider(GatewayChoices.PAYPAL)
        order = self.create_test_order()
        payment = Payment.objects.create(
            order=order,
            payment_reference="PAY-REF-REFUND",
            gateway=GatewayChoices.PAYPAL,
            amount=Decimal("100.00"),
        )
        res = provider.refund(payment, amount=Decimal("100.00"))
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "not_implemented")
        self.assertIn("reserved for future milestones", res["error"])


class GatewayAdaptersTests(PaymentBaseTestCase):
    """
    Verify each provider adapter (`PayPalProvider`, `MpesaProvider`, `StripeProvider`)
    for payment initiation, verification, and webhook parsing.
    """
    def test_paypal_provider_initiate_verify_and_webhook(self):
        provider = PayPalProvider(client_id="test_client_id", mock=True)
        order = self.create_test_order()
        payment = Payment.objects.create(
            order=order,
            payment_reference="PAY-PP-001",
            gateway=GatewayChoices.PAYPAL,
            amount=Decimal("2400.00"),
        )

        init_res = provider.initiate_payment(payment, mock=True)
        self.assertTrue(init_res["success"])
        self.assertIn("checkoutnow", init_res["redirect_url"])

        verify_res = provider.verify_payment(payment, mock=True, simulated_status="COMPLETED")
        self.assertTrue(verify_res["success"])
        self.assertEqual(verify_res["status"], "completed")

        req = self.factory.post(
            "/payments/webhooks/paypal/",
            data=json.dumps({"id": "WH-PP-123", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "CAP-999"}}),
            content_type="application/json",
        )
        wh_res = provider.handle_webhook(req)
        self.assertTrue(wh_res["success"])
        self.assertEqual(wh_res["event_id"], "WH-PP-123")
        self.assertEqual(wh_res["status"], "completed")

    def test_mpesa_provider_initiate_verify_and_webhook(self):
        provider = MpesaProvider(consumer_key="test_consumer_key", mock=True)
        order = self.create_test_order()
        payment = Payment.objects.create(
            order=order,
            payment_reference="PAY-MP-001",
            gateway=GatewayChoices.MPESA,
            amount=Decimal("2400.00"),
        )

        init_res = provider.initiate_payment(payment, phone_number="0712345678", mock=True)
        self.assertTrue(init_res["success"])
        self.assertEqual(init_res["provider_data"]["PhoneNumber"], "254712345678")
        self.assertIn("MerchantRequestID", init_res["provider_data"])

        verify_res = provider.verify_payment(payment, mock=True, simulated_result_code="0")
        self.assertTrue(verify_res["success"])
        self.assertEqual(verify_res["status"], "completed")

        stk_payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "MRID-001",
                    "CheckoutRequestID": "ws_CO_123",
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 2400.00},
                            {"Name": "MpesaReceiptNumber", "Value": "QJH999XYZ"},
                            {"Name": "PhoneNumber", "Value": 254712345678},
                        ]
                    },
                }
            }
        }
        req = self.factory.post("/payments/webhooks/mpesa/", data=json.dumps(stk_payload), content_type="application/json")
        wh_res = provider.handle_webhook(req)
        self.assertTrue(wh_res["success"])
        self.assertEqual(wh_res["transaction_id"], "QJH999XYZ")
        self.assertEqual(wh_res["amount"], Decimal("2400.00"))
        self.assertEqual(wh_res["status"], "completed")

    def test_stripe_provider_initiate_verify_and_webhook(self):
        provider = StripeProvider(secret_key="test_sk", mock=True)
        order = self.create_test_order()
        payment = Payment.objects.create(
            order=order,
            payment_reference="PAY-ST-001",
            gateway=GatewayChoices.STRIPE,
            amount=Decimal("2400.00"),
        )

        init_res = provider.initiate_payment(payment, mock=True)
        self.assertTrue(init_res["success"])
        self.assertEqual(init_res["provider_data"]["amount"], 240000)

        verify_res = provider.verify_payment(payment, mock=True, simulated_status="succeeded")
        self.assertTrue(verify_res["success"])
        self.assertEqual(verify_res["status"], "completed")

        stripe_payload = {
            "id": "evt_stripe_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123",
                    "amount": 240000,
                    "status": "succeeded",
                    "metadata": {"payment_reference": "PAY-ST-001"},
                }
            },
        }
        req = self.factory.post("/payments/webhooks/stripe/", data=json.dumps(stripe_payload), content_type="application/json")
        wh_res = provider.handle_webhook(req)
        self.assertTrue(wh_res["success"])
        self.assertEqual(wh_res["event_id"], "evt_stripe_1")
        self.assertEqual(wh_res["amount"], Decimal("2400.00"))
        self.assertEqual(wh_res["status"], "completed")


class PaymentServiceAndInventoryTests(PaymentBaseTestCase):
    """
    Verify payment lifecycle, server-side verification, order status updates,
    and strict invariant: inventory deducted ONLY after confirmed payment.
    """
    def test_create_payment_validates_order_state(self):
        order = self.create_test_order()
        payment = create_payment(order, gateway=GatewayChoices.PAYPAL)
        self.assertEqual(payment.status, PaymentStatus.PENDING)

        # Cannot create payment for cancelled order
        order.status = OrderStatus.CANCELLED
        order.save()
        with self.assertRaises(ValidationError):
            create_payment(order, gateway=GatewayChoices.PAYPAL)

    def test_inventory_deducted_only_after_confirmed_payment(self):
        order = self.create_test_order(quantity=2)
        # Verify initial variant inventory before payment
        self.variant.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(self.product.stock_quantity, 20)

        # Create payment & initiate -> still no inventory deduction
        payment = create_payment(order, gateway=GatewayChoices.MANUAL)
        payment, _ = initiate_payment(payment, mock=True)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

        # Now process successful server-side payment verification
        process_success(payment, transaction_id="TX-SUCCESS-100")

        self.variant.refresh_from_db()
        self.product.refresh_from_db()
        # Exactly 2 units deducted after confirmed payment
        self.assertEqual(self.variant.stock_quantity, 8)
        self.assertEqual(self.product.stock_quantity, 18)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.payment_status, OrderPaymentStatus.PAID)

    def test_process_success_is_idempotent_no_double_inventory_deduction(self):
        order = self.create_test_order(quantity=3)
        payment = create_payment(order, gateway=GatewayChoices.MANUAL)

        # First verification
        process_success(payment, transaction_id="TX-IDEMPOTENT-001")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)  # 10 - 3 = 7

        # Second verification (e.g. duplicate webhook or retry)
        process_success(payment, transaction_id="TX-IDEMPOTENT-001")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)  # Remains 7! No double deduction!

    def test_process_failure_updates_records_safely(self):
        order = self.create_test_order()
        payment = create_payment(order, gateway=GatewayChoices.STRIPE)
        process_failure(payment, error_message="Insufficient funds")

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(order.payment_status, OrderPaymentStatus.FAILED)
        self.assertIn("Insufficient funds", order.customer_notes)


class WebhookAndEndpointIntegrationTests(PaymentBaseTestCase):
    """
    Verify HTTP endpoints for initiation, browser return/cancel, and webhooks.
    """
    def test_initiate_view_and_return_flow(self):
        order = self.create_test_order()
        self.client.force_login(self.user)

        res = self.client.post(
            reverse("payments:initiate", kwargs={"order_number": order.order_number}),
            {"gateway": GatewayChoices.PAYPAL},
        )
        self.assertIn(res.status_code, (302, 303))
        payment = Payment.objects.filter(order=order).first()
        self.assertIsNotNone(payment)

        # Simulate browser return from gateway
        return_res = self.client.get(
            reverse("payments:return", kwargs={"payment_reference": payment.payment_reference}),
            {"simulated_status": "COMPLETED"},
        )
        self.assertEqual(return_res.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)

    def test_duplicate_webhook_payload_deduplication(self):
        order = self.create_test_order()
        payment = create_payment(order, gateway=GatewayChoices.STRIPE)
        payment.transaction_id = "pi_12345"
        payment.save()

        payload = {
            "id": "evt_duplicate_001",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_12345",
                    "amount": int(payment.amount * 100),
                    "currency": payment.currency.lower(),
                    "status": "succeeded",
                    "metadata": {"payment_reference": payment.payment_reference},
                }
            },
        }

        # First webhook delivery
        res1 = self.client.post("/payments/webhooks/stripe/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(PaymentWebhookLog.objects.count(), 1)
        self.assertEqual(PaymentWebhookLog.objects.first().status, "processed")

        # Second delivery with exact same event id -> logged as duplicate, status 200 returned
        res2 = self.client.post("/payments/webhooks/stripe/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(PaymentWebhookLog.objects.count(), 2)
        dup_log = PaymentWebhookLog.objects.order_by("-created_at").first()
        self.assertEqual(dup_log.status, "duplicate")

    def test_monetary_and_currency_mismatch_rejection(self):
        order = self.create_test_order()
        payment = create_payment(order, gateway=GatewayChoices.STRIPE)
        payment.transaction_id = "pi_mismatch_001"
        payment.save()

        # Send webhook reporting 1.00 USD (100 cents) against 2400.00 USD order
        payload = {
            "id": "evt_mismatch_001",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_mismatch_001",
                    "amount": 100,
                    "currency": "usd",
                    "status": "succeeded",
                    "metadata": {"payment_reference": payment.payment_reference},
                }
            },
        }
        res = self.client.post("/payments/webhooks/stripe/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        log = PaymentWebhookLog.objects.filter(event_id="evt_mismatch_001").first()
        self.assertEqual(log.status, "failed")
        self.assertIn("Monetary mismatch", log.error_message)

    def test_expire_pending_payments_command(self):
        order = self.create_test_order()
        p1 = create_payment(order, gateway=GatewayChoices.PAYPAL)
        p2 = create_payment(order, gateway=GatewayChoices.STRIPE)
        p2.status = PaymentStatus.PROCESSING
        p2.save()

        import datetime
        Payment.objects.filter(pk__in=[p1.pk, p2.pk]).update(
            created_at=timezone.now() - datetime.timedelta(hours=30)
        )

        call_command("expire_pending_payments", "--hours", "24")
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, PaymentStatus.EXPIRED)
        self.assertEqual(p2.status, PaymentStatus.EXPIRED)

    def test_replay_failed_webhooks_command(self):
        order = self.create_test_order()
        payment = create_payment(order, gateway=GatewayChoices.STRIPE)
        payment.transaction_id = "pi_replay_001"
        payment.save()

        # Create a failed webhook log
        log_entry = PaymentWebhookLog.objects.create(
            gateway=GatewayChoices.STRIPE,
            event_id="evt_replay_001",
            event_type="payment_intent.succeeded",
            payload={
                "id": "evt_replay_001",
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_replay_001",
                        "amount": int(payment.amount * 100),
                        "currency": payment.currency.lower(),
                        "status": "succeeded",
                        "metadata": {"payment_reference": payment.payment_reference},
                    }
                },
            },
            status="failed",
            error_message="Initial transient failure",
        )

        call_command("replay_failed_webhooks", "--status", "failed", "--event-id", "evt_replay_001")
        log_entry.refresh_from_db()
        self.assertEqual(log_entry.status, "processed")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.COMPLETED)

