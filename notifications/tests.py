# notifications/tests.py
"""
notifications/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive unit and integration verification for the notifications engine.
Covers models, providers, email template rendering, Celery worker dispatch,
delivery audit logs, and integration with orders and payment hooks.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from checkout.models import CheckoutSession
from notifications.admin import NotificationAdmin, NotificationDeliveryLogAdmin
from notifications.models import (
    ChannelChoices,
    DeliveryLogStatusChoices,
    EventChoices,
    Notification,
    NotificationDeliveryLog,
    NotificationStatusChoices,
)
from notifications.providers import get_provider
from notifications.providers.email import EmailProvider
from notifications.providers.sms import SmsProvider
from notifications.providers.whatsapp import WhatsAppProvider
from notifications.services import (
    log_delivery,
    publish_event,
    queue_notification,
    retry_notification,
    send_email,
    send_notification,
    send_sms,
    send_whatsapp,
)
from orders.models import Order, OrderItem, OrderStatus
from orders.models import PaymentStatus as OrderPaymentStatus
from payments.models import GatewayChoices, Payment, PaymentStatus
from payments.services import process_failure, send_confirmation
from products.models import Category, Product, ProductVariant

User = get_user_model()


class NotificationModelAndAdminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="notif_client@houseofbore.com",
            password="SecurePassword123!"
        )

    def test_notification_and_log_model_lifecycle(self):
        notif = Notification.objects.create(
            user=self.user,
            channel=ChannelChoices.EMAIL,
            event=EventChoices.ORDER_CREATED,
            recipient="notif_client@houseofbore.com",
            subject="Order Confirmed",
            status=NotificationStatusChoices.PENDING,
        )
        self.assertIn("Notification #", str(notif))
        self.assertEqual(notif.status, NotificationStatusChoices.PENDING)

        log_entry = log_delivery(
            notification=notif,
            channel=notif.channel,
            provider="email_smtp",
            recipient=notif.recipient,
            status=DeliveryLogStatusChoices.SUCCESS,
        )
        self.assertIn("DeliveryLog #", str(log_entry))
        self.assertEqual(notif.delivery_logs.count(), 1)

    def test_admin_readonly_permissions(self):
        notif = Notification.objects.create(
            recipient="test@example.com",
            channel=ChannelChoices.EMAIL,
            event=EventChoices.ACCOUNT_REGISTERED,
        )
        admin_instance = NotificationAdmin(Notification, None)
        log_admin_instance = NotificationDeliveryLogAdmin(NotificationDeliveryLog, None)
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_delete_permission(None, notif))
        self.assertFalse(log_admin_instance.has_add_permission(None))


class ChannelProviderTests(TestCase):
    def test_provider_factory(self):
        self.assertIsInstance(get_provider(ChannelChoices.EMAIL), EmailProvider)
        self.assertIsInstance(get_provider(ChannelChoices.SMS), SmsProvider)
        self.assertIsInstance(get_provider(ChannelChoices.WHATSAPP), WhatsAppProvider)
        with self.assertRaises(ValueError):
            get_provider("unsupported_channel")

    def test_email_provider_validation_and_send(self):
        provider = EmailProvider()
        self.assertTrue(provider.validate("client@houseofbore.com"))
        self.assertFalse(provider.validate("not-an-email"))
        self.assertFalse(provider.validate(""))

        # Send test message
        result = provider.send(
            recipient="client@houseofbore.com",
            subject="Welcome Client",
            content="Plain text content",
            html_content="<p>HTML content</p>"
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, "Welcome Client")
        self.assertEqual(sent_email.body, "Plain text content")
        self.assertEqual(len(sent_email.alternatives), 1)
        self.assertEqual(sent_email.alternatives[0][0], "<p>HTML content</p>")
        self.assertEqual(sent_email.alternatives[0][1], "text/html")

    def test_sms_provider_placeholder(self):
        provider = SmsProvider()
        self.assertTrue(provider.validate("+14155552671"))
        self.assertFalse(provider.validate("abc1234"))

        result = provider.send(recipient="+14155552671", subject="", content="Your OTP is 123456")
        self.assertTrue(result["success"])
        self.assertIn("sms_sim_", result["message_id"])

    def test_whatsapp_provider_placeholder(self):
        provider = WhatsAppProvider()
        self.assertTrue(provider.validate("+447911123456"))

        # Text format
        res_text = provider.send(recipient="+447911123456", subject="", content="Hello via WhatsApp")
        self.assertTrue(res_text["success"])

        # Template format
        res_tmpl = provider.send(
            recipient="+447911123456",
            subject="",
            content="",
            metadata={"template_name": "order_alert", "language_code": "en_US"}
        )
        self.assertTrue(res_tmpl["success"])
        self.assertEqual(res_tmpl["raw_response"]["payload"]["type"], "template")


class NotificationServiceAndTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="service_test@houseofbore.com",
            password="SecurePassword123!"
        )
        category = Category.objects.create(name="Bespoke Suit", slug="bespoke-suit")
        self.product = Product.objects.create(
            name="Silk Dinner Jacket",
            slug="silk-dinner-jacket",
            category=category,
            price=Decimal("1800.00"),
            short_description="Elegant evening jacket",
            description="Handcrafted silk dinner jacket.",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="JCK-SLK-42R",
            price_override=Decimal("1800.00"),
            stock_quantity=10,
        )
        self.order = Order.objects.create(
            order_number="HOB-TEST-001",
            user=self.user,
            subtotal=Decimal("1800.00"),
            shipping_total=Decimal("50.00"),
            tax_total=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            grand_total=Decimal("1850.00"),
            shipping_address_snapshot={"email": "service_test@houseofbore.com"},
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name="Silk Dinner Jacket",
            sku="JCK-SLK-42R",
            quantity=1,
            unit_price=Decimal("1800.00"),
            line_total=Decimal("1800.00"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            payment_reference="PAY-TEST-001",
            gateway=GatewayChoices.STRIPE,
            amount=Decimal("1850.00"),
            currency="USD",
            status=PaymentStatus.COMPLETED,
        )

    def test_publish_event_email_templates_and_celery_dispatch(self):
        mail.outbox.clear()
        notif = publish_event(
            event=EventChoices.ORDER_CREATED,
            recipient=self.user.email,
            channel=ChannelChoices.EMAIL,
            user=self.user,
            order=self.order,
            payment=self.payment,
        )
        notif.refresh_from_db()
        # With CELERY_TASK_ALWAYS_EAGER=True, the task executes synchronously
        self.assertEqual(notif.status, NotificationStatusChoices.SENT)
        self.assertIsNotNone(notif.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("HOB-TEST-001", mail.outbox[0].subject)
        self.assertIn("Silk Dinner Jacket", mail.outbox[0].body)
        self.assertEqual(notif.delivery_logs.count(), 1)
        self.assertEqual(notif.delivery_logs.first().status, DeliveryLogStatusChoices.SUCCESS)

    def test_publish_payment_successful_and_failed_events(self):
        mail.outbox.clear()
        notif_succ = publish_event(
            event=EventChoices.PAYMENT_SUCCESSFUL,
            recipient=self.user.email,
            user=self.user,
            order=self.order,
            payment=self.payment,
        )
        notif_succ.refresh_from_db()
        self.assertEqual(notif_succ.status, NotificationStatusChoices.SENT)
        self.assertIn("PAY-TEST-001", mail.outbox[0].subject)

        notif_fail = publish_event(
            event=EventChoices.PAYMENT_FAILED,
            recipient=self.user.email,
            user=self.user,
            order=self.order,
            payment=self.payment,
        )
        notif_fail.refresh_from_db()
        self.assertEqual(notif_fail.status, NotificationStatusChoices.SENT)
        self.assertIn("Payment Failed", mail.outbox[1].subject)

    def test_convenience_send_methods(self):
        mail.outbox.clear()
        notif_email = send_email(
            recipient="direct@houseofbore.com",
            subject="Direct Email Test",
            text_content="Direct text",
            html_content="<b>Direct html</b>",
        )
        notif_email.refresh_from_db()
        self.assertEqual(notif_email.status, NotificationStatusChoices.SENT)
        self.assertEqual(len(mail.outbox), 1)

        notif_sms = send_sms(recipient="+14155552671", content="SMS content")
        notif_sms.refresh_from_db()
        self.assertEqual(notif_sms.status, NotificationStatusChoices.SENT)

        notif_wa = send_whatsapp(recipient="+14155552671", content="WA content")
        notif_wa.refresh_from_db()
        self.assertEqual(notif_wa.status, NotificationStatusChoices.SENT)

    def test_retry_notification(self):
        notif = Notification.objects.create(
            recipient="bad_address",
            channel=ChannelChoices.EMAIL,
            event=EventChoices.ACCOUNT_REGISTERED,
            status=NotificationStatusChoices.FAILED,
            error_message="Initial failure",
        )
        try:
            retry_notification(notif)
        except Exception:
            pass  # Expected when CELERY_TASK_ALWAYS_EAGER propagates autoretry exceptions synchronously
        notif.refresh_from_db()
        self.assertEqual(notif.status, NotificationStatusChoices.FAILED)
        self.assertTrue(notif.delivery_logs.filter(status=DeliveryLogStatusChoices.RETRY).exists())

    def test_publish_event_fallback(self):
        notif = publish_event(
            event="unmapped_custom_event",
            recipient="fallback@houseofbore.com",
            channel=ChannelChoices.EMAIL,
            extra_context={"subject": "Custom Alert", "text_content": "Fallback body text"}
        )
        notif.refresh_from_db()
        self.assertEqual(notif.status, NotificationStatusChoices.SENT)
        self.assertEqual(notif.subject, "Custom Alert")
        self.assertIn("Fallback body text", notif.metadata.get("text_content", ""))

    def test_send_notification_already_sent_skips_dispatch(self):
        notif = Notification.objects.create(
            recipient="skip@houseofbore.com",
            channel=ChannelChoices.EMAIL,
            event=EventChoices.ACCOUNT_REGISTERED,
            status=NotificationStatusChoices.SENT,
        )
        mail.outbox.clear()
        initial_log_count = notif.delivery_logs.count()
        # Call send_notification directly on an already SENT notification
        returned_notif = send_notification(notif.pk)
        self.assertEqual(returned_notif.status, NotificationStatusChoices.SENT)
        self.assertEqual(len(mail.outbox), 0)  # No second email sent
        self.assertEqual(returned_notif.delivery_logs.count(), initial_log_count)  # No duplicate log created


class PaymentAndOrderIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="hook_test@houseofbore.com",
            password="SecurePassword123!"
        )
        self.order = Order.objects.create(
            order_number="HOB-HOOK-001",
            user=self.user,
            subtotal=Decimal("500.00"),
            shipping_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            grand_total=Decimal("500.00"),
            status=OrderStatus.PENDING,
            payment_status=OrderPaymentStatus.AWAITING_PAYMENT,
            shipping_address_snapshot={"email": "hook_test@houseofbore.com"},
        )
        self.payment = Payment.objects.create(
            order=self.order,
            payment_reference="PAY-HOOK-001",
            gateway=GatewayChoices.PAYPAL,
            amount=Decimal("500.00"),
            currency="USD",
            status=PaymentStatus.PENDING,
        )

    def test_send_confirmation_hook(self):
        mail.outbox.clear()
        initial_notif_count = Notification.objects.count()
        send_confirmation(self.order, payment=self.payment)
        self.assertEqual(Notification.objects.count(), initial_notif_count + 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_process_failure_hook(self):
        mail.outbox.clear()
        initial_notif_count = Notification.objects.count()
        process_failure(self.payment, error_message="Card expired")
        self.assertEqual(Notification.objects.count(), initial_notif_count + 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Payment Failed", mail.outbox[0].subject)
