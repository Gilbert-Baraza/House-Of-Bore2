# payments/services.py
"""
payments/services.py
──────────────────────────────────────────────────────────────────────────────
Service layer encapsulating all business logic for payment creation, gateway
initiation, server-side verification, idempotent webhook processing, order status
updates, cart clearing, and inventory deduction.

Enforces critical invariant: Inventory is deducted ONLY AFTER confirmed server-side
payment verification (`process_success`), preventing stock depletion from unpaid
or abandoned checkout sessions.
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from orders.models import Order, OrderStatus
from orders.models import PaymentStatus as OrderPaymentStatus
from payments.models import GatewayChoices, Payment, PaymentStatus, PaymentWebhookLog
from payments.providers import get_provider
from products.models import Product, ProductVariant

logger = logging.getLogger(__name__)


def generate_payment_reference() -> str:
    """
    Generate a unique, human-readable payment reference string independent of database IDs.
    Format: PAY-YYYYMMDD-000001
    """
    today_str = timezone.now().strftime("%Y%m%d")
    prefix = f"PAY-{today_str}-"

    latest_payment = (
        Payment.objects.filter(payment_reference__startswith=prefix)
        .order_by("-payment_reference")
        .first()
    )

    if latest_payment:
        try:
            last_seq = int(latest_payment.payment_reference.split("-")[-1])
            seq = last_seq + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    for _ in range(100):
        ref = f"{prefix}{seq:06d}"
        if not Payment.objects.filter(payment_reference=ref).exists():
            return ref
        seq += 1

    micro_str = timezone.now().strftime("%H%M%S%f")[:8]
    return f"PAY-{today_str}-{micro_str}"


@transaction.atomic
def create_payment(
    order: Order,
    gateway: str,
    amount: Optional[Decimal] = None,
    currency: Optional[str] = None,
    **kwargs: Any
) -> Payment:
    """
    Create a new `Payment` record in PENDING status for the specified `Order`.
    Validates that the order has not been cancelled or already marked as paid.
    """
    if order.is_cancelled:
        raise ValidationError("Cannot create payment for a cancelled order.")
    if order.is_paid:
        raise ValidationError("Order has already been paid.")

    gateway_clean = str(gateway or "").lower().strip()
    valid_gateways = [g.value for g in GatewayChoices]
    if gateway_clean not in valid_gateways:
        raise ValidationError(f"Invalid gateway code: '{gateway}'. Must be one of {valid_gateways}.")

    payment_amount = amount if amount is not None else order.grand_total
    payment_currency = currency if currency is not None else order.currency
    metadata = kwargs.get("metadata", {})

    ref = generate_payment_reference()
    for _ in range(3):
        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    order=order,
                    payment_reference=ref,
                    gateway=gateway_clean,
                    amount=payment_amount,
                    currency=payment_currency,
                    status=PaymentStatus.PENDING,
                    metadata=metadata,
                )
            return payment
        except IntegrityError:
            ref = generate_payment_reference()

    raise ValidationError("Could not generate unique payment reference. Please retry.")


@transaction.atomic
def initiate_payment(
    payment: Payment,
    request: Optional[HttpRequest] = None,
    **kwargs: Any
) -> Tuple[Payment, Dict[str, Any]]:
    """
    Initiate the payment process with the external gateway via the provider adapter.
    Updates `initiated_at`, status, `transaction_id`, and `provider_response`.
    """
    if payment.is_completed:
        raise ValidationError("Payment has already been completed.")
    if payment.status in (PaymentStatus.CANCELLED, PaymentStatus.EXPIRED):
        raise ValidationError(f"Cannot initiate payment in status '{payment.status}'.")

    provider = get_provider(payment.gateway, **kwargs)
    result = provider.initiate_payment(payment, request=request, **kwargs)

    payment.initiated_at = timezone.now()
    payment.provider_response = result.get("provider_data", {})

    if result.get("success"):
        payment.status = PaymentStatus.PROCESSING
        # If the provider returned a transaction ID during initiation (e.g. PayPal Order ID or Stripe PI ID)
        provider_data = result.get("provider_data", {})
        if provider_data.get("id"):
            payment.transaction_id = str(provider_data["id"])
    else:
        payment.status = PaymentStatus.FAILED

    payment.save()
    return payment, result


@transaction.atomic
def verify_payment(
    payment: Payment,
    **kwargs: Any
) -> Tuple[Payment, bool]:
    """
    Perform authoritative server-side verification against the gateway API.
    Calls `process_success` or `process_failure` based on the verification result.
    """
    if payment.is_completed:
        return payment, True

    provider = get_provider(payment.gateway, **kwargs)
    result = provider.verify_payment(payment, **kwargs)

    if result.get("success"):
        tx_id = result.get("transaction_id")
        provider_resp = result.get("provider_response", {})
        payment = process_success(payment, provider_response=provider_resp, transaction_id=tx_id)
        return payment, True
    else:
        error_msg = result.get("error", "Payment verification failed.")
        provider_resp = result.get("provider_response", {})
        payment = process_failure(payment, error_message=error_msg, provider_response=provider_resp)
        return payment, False


@transaction.atomic
def process_success(
    payment: Payment,
    provider_response: Optional[Dict[str, Any]] = None,
    transaction_id: Optional[str] = None
) -> Payment:
    """
    Authoritative success handler executed atomically when a payment is verified or
    confirmed via webhook. Selects records `for_update()` to prevent race conditions.

    Executes in exact sequence:
    1. Mark Payment as COMPLETED
    2. Update Order payment status to PAID
    3. Transition Order status to PAID
    4. Deduct inventory (strictly after confirmed payment)
    5. Clear customer cart
    6. Trigger confirmation notifications
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    order = Order.objects.select_for_update().get(pk=payment.order_id)

    # Idempotency check: if payment and order are already finalized, return without re-deducting stock
    if payment.status == PaymentStatus.COMPLETED and order.payment_status == OrderPaymentStatus.PAID:
        logger.info(f"Idempotent check: Payment {payment.payment_reference} already completed.")
        return payment

    payment.status = PaymentStatus.COMPLETED
    payment.completed_at = timezone.now()
    if transaction_id:
        payment.transaction_id = transaction_id
    if provider_response:
        payment.provider_response = provider_response
    payment.save()

    # Update Order status and financial flags
    update_order_status(order, new_status=OrderStatus.PAID, payment_status=OrderPaymentStatus.PAID)

    # Deduct inventory ONLY AFTER confirmed payment
    deduct_inventory(order)

    # Clear customer shopping cart
    clear_customer_cart(order)

    # Trigger order/payment confirmation notification
    send_confirmation(order, payment=payment)

    return payment


@transaction.atomic
def process_failure(
    payment: Payment,
    error_message: str = "",
    provider_response: Optional[Dict[str, Any]] = None
) -> Payment:
    """
    Controlled failure handler executing when gateway verification rejects a transaction.
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status in (PaymentStatus.COMPLETED, PaymentStatus.CANCELLED):
        return payment

    payment.status = PaymentStatus.FAILED
    payment.completed_at = timezone.now()
    if provider_response:
        payment.provider_response = provider_response
    payment.save()

    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status == OrderStatus.PENDING and order.payment_status != OrderPaymentStatus.PAID:
        note = f"Payment attempt {payment.payment_reference} failed: {error_message}".strip()
        update_order_status(order, new_status=order.status, payment_status=OrderPaymentStatus.FAILED, note=note)

        try:
            from notifications.models import EventChoices
            from notifications.services import publish_event
            recipient = (order.user.email if (order.user and order.user.email) else None) or \
                        (order.shipping_address_snapshot.get("email") if isinstance(order.shipping_address_snapshot, dict) else None) or \
                        (order.billing_address_snapshot.get("email") if isinstance(order.billing_address_snapshot, dict) else None)
            if recipient:
                publish_event(
                    event=EventChoices.PAYMENT_FAILED,
                    recipient=recipient,
                    user=order.user,
                    order=order,
                    payment=payment,
                )
        except Exception as exc:
            logger.error(f"Error publishing payment failure notification for Order {order.order_number}: {exc}")

    return payment


@transaction.atomic
def update_order_status(
    order: Order,
    new_status: str = OrderStatus.PAID,
    payment_status: str = OrderPaymentStatus.PAID,
    note: str = ""
) -> Order:
    """
    Update order lifecycle and payment status, appending an auditable note to `customer_notes`.
    """
    order.status = new_status
    order.payment_status = payment_status

    if not note:
        note = f"Payment status confirmed as {payment_status} via payment gateway."
    timestamp_str = timezone.now().strftime("%Y-%m-%d %H:%M")
    order.customer_notes = f"{order.customer_notes}\n[{timestamp_str}] {note}".strip()
    order.save()
    return order


@transaction.atomic
def deduct_inventory(order: Order) -> None:
    """
    Deduct exact stock quantities for all items in the order.
    Enforces strict row-level locking via `select_for_update()` to maintain accurate
    inventory counts under concurrent payment completions.

    Note: Designed to support future inventory reservation architecture cleanly.
    """
    for item in order.items.all().select_for_update():
        # Check if item corresponds to a specific ProductVariant
        if item.sku:
            variant = ProductVariant.objects.select_for_update().filter(sku=item.sku).first()
            if variant:
                variant.stock_quantity = max(0, variant.stock_quantity - item.quantity)
                variant.save(update_fields=["stock_quantity", "updated_at"])

        # Also decrement parent Product inventory if present
        if item.product_id:
            product = Product.objects.select_for_update().filter(pk=item.product_id).first()
            if product:
                product.stock_quantity = max(0, product.stock_quantity - item.quantity)
                product.save(update_fields=["stock_quantity"])


@transaction.atomic
def clear_customer_cart(order: Order) -> None:
    """
    Clear items from the customer's shopping cart upon confirmed payment.
    Marks the originating checkout session as completed.
    """
    if order.checkout_session:
        order.checkout_session.status = "completed"
        order.checkout_session.save(update_fields=["status", "updated_at"])

        if order.checkout_session.cart:
            order.checkout_session.cart.items.all().delete()
            if hasattr(order.checkout_session.cart, "_cached_breakdown"):
                delattr(order.checkout_session.cart, "_cached_breakdown")


def send_confirmation(order: Order, payment: Optional[Payment] = None) -> bool:
    """
    Trigger confirmation notification via the centralized `notifications` service.
    Publishes payment_successful and order_created events asynchronously without blocking.
    """
    logger.info(
        f"Confirmation sent for Order {order.order_number} (Total: {order.grand_total} {order.currency}). "
        f"Payment Ref: {payment.payment_reference if payment else 'N/A'}"
    )
    try:
        from notifications.models import EventChoices
        from notifications.services import publish_event

        recipient = (order.user.email if (order.user and order.user.email) else None) or \
                    (order.shipping_address_snapshot.get("email") if isinstance(order.shipping_address_snapshot, dict) else None) or \
                    (order.billing_address_snapshot.get("email") if isinstance(order.billing_address_snapshot, dict) else None)

        if recipient:
            if payment:
                publish_event(
                    event=EventChoices.PAYMENT_SUCCESSFUL,
                    recipient=recipient,
                    user=order.user,
                    order=order,
                    payment=payment,
                )
            publish_event(
                event=EventChoices.ORDER_CREATED,
                recipient=recipient,
                user=order.user,
                order=order,
                payment=payment,
            )
    except Exception as exc:
        logger.error(f"Error publishing order confirmation notification for Order {order.order_number}: {exc}")

    return True


@transaction.atomic
def process_webhook_payload(gateway: str, request: HttpRequest) -> Tuple[PaymentWebhookLog, Dict[str, Any]]:
    """
    Orchestrate secure, idempotent webhook processing across supported gateways.
    Validates payload signature via provider adapter and deduplicates `event_id`.
    """
    provider = get_provider(gateway)
    webhook_result = provider.handle_webhook(request)

    event_id = webhook_result.get("event_id") or f"{gateway}-unknown-{timezone.now().timestamp()}"
    event_type = webhook_result.get("event_type", "webhook_event")
    raw_payload = webhook_result.get("raw_payload", {})
    headers_dict = dict(request.headers) if hasattr(request, "headers") else {}

    # Check for duplicate delivery (idempotency enforcement)
    if event_id and PaymentWebhookLog.objects.filter(gateway=gateway, event_id=event_id, status="processed").exists():
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="duplicate",
            error_message="Duplicate webhook event delivery ignored.",
        )
        return log_entry, {"success": True, "duplicate": True, "message": "Duplicate event."}

    if not webhook_result.get("success"):
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="failed",
            error_message=webhook_result.get("error", "Webhook verification failed."),
        )
        return log_entry, webhook_result

    # Resolve corresponding Payment attempt
    payment_reference = webhook_result.get("payment_reference")
    transaction_id = webhook_result.get("transaction_id")
    status_str = webhook_result.get("status")

    payment = None
    if payment_reference:
        payment = Payment.objects.filter(payment_reference=payment_reference).first()
    if not payment and transaction_id:
        payment = Payment.objects.filter(transaction_id=transaction_id).first()
    if not payment and gateway == GatewayChoices.MPESA and event_id:
        # Check metadata for CheckoutRequestID match
        for p in Payment.objects.filter(gateway=GatewayChoices.MPESA, status__in=[PaymentStatus.PENDING, PaymentStatus.PROCESSING]):
            if p.metadata.get("CheckoutRequestID") == event_id or p.metadata.get("MerchantRequestID") == event_id:
                payment = p
                break

    if not payment:
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="ignored",
            error_message="No matching Payment record found for this webhook.",
        )
        return log_entry, {"success": True, "ignored": True, "message": "No matching payment record."}

    # Execute appropriate payment transition
    if status_str in ("completed", "authorized"):
        webhook_amount = webhook_result.get("amount")
        webhook_currency = webhook_result.get("currency")

        # Strict monetary check within 0.01 tolerance
        if webhook_amount is not None and abs(Decimal(str(webhook_amount)) - payment.amount) > Decimal("0.01"):
            err_msg = f"Monetary mismatch: webhook reported amount {webhook_amount}, expected {payment.amount}"
            process_failure(payment, error_message=err_msg, provider_response=raw_payload)
            log_entry = PaymentWebhookLog.objects.create(
                gateway=gateway,
                event_id=event_id,
                event_type=event_type,
                payload=raw_payload,
                headers=headers_dict,
                status="failed",
                error_message=err_msg,
            )
            return log_entry, {"success": False, "error": err_msg, "payment": payment}

        # Strict currency check
        if webhook_currency is not None and str(webhook_currency).upper() != payment.currency.upper():
            err_msg = f"Currency mismatch: webhook reported currency {webhook_currency}, expected {payment.currency}"
            process_failure(payment, error_message=err_msg, provider_response=raw_payload)
            log_entry = PaymentWebhookLog.objects.create(
                gateway=gateway,
                event_id=event_id,
                event_type=event_type,
                payload=raw_payload,
                headers=headers_dict,
                status="failed",
                error_message=err_msg,
            )
            return log_entry, {"success": False, "error": err_msg, "payment": payment}

        process_success(payment, provider_response=raw_payload, transaction_id=transaction_id)
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="processed",
        )
        return log_entry, {"success": True, "processed": True, "payment": payment}
    elif status_str in ("failed", "cancelled"):
        error_desc = webhook_result.get("error") or f"Transaction marked as {status_str} via webhook."
        process_failure(payment, error_message=error_desc, provider_response=raw_payload)
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="processed",
        )
        return log_entry, {"success": True, "processed": True, "payment": payment}
    else:
        log_entry = PaymentWebhookLog.objects.create(
            gateway=gateway,
            event_id=event_id,
            event_type=event_type,
            payload=raw_payload,
            headers=headers_dict,
            status="processed",
            error_message=f"Webhook status '{status_str}' recorded without state transition.",
        )
        return log_entry, {"success": True, "processed": True, "payment": payment}
