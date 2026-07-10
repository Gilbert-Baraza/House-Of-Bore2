# payments/views.py
"""
payments/views.py
──────────────────────────────────────────────────────────────────────────────
Thin views handling gateway initiation, customer browser return/cancel flows, and
secure, idempotent gateway webhook endpoints (`/payments/webhooks/paypal/`, etc.).
All transactional state mutations and gateway API requests are delegated to `payments.services`.
──────────────────────────────────────────────────────────────────────────────
"""

import json
from typing import Any
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from orders.selectors import get_order
from payments.models import GatewayChoices, Payment, PaymentStatus
from payments.services import (
    create_payment,
    initiate_payment,
    process_webhook_payload,
    verify_payment,
)


@method_decorator(csrf_exempt, name="dispatch")
class PayPalWebhookView(View):
    """
    Secure webhook endpoint for PayPal event deliveries (`/payments/webhooks/paypal/`).
    Enforces signature validation and idempotent processing via `process_webhook_payload`.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        log_entry, result = process_webhook_payload(GatewayChoices.PAYPAL, request)
        if result.get("success"):
            return JsonResponse({"status": "received", "event_id": log_entry.event_id}, status=200)
        return JsonResponse({"status": "error", "message": log_entry.error_message}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class MpesaWebhookView(View):
    """
    Secure callback endpoint for M-Pesa Daraja STK Push (`/payments/webhooks/mpesa/`).
    Processes `stkCallback` payload, extracts receipt details, and deducts inventory only on confirmation.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        log_entry, result = process_webhook_payload(GatewayChoices.MPESA, request)
        if result.get("success"):
            return JsonResponse({"ResultCode": "0", "ResultDesc": "Accepted"}, status=200)
        return JsonResponse({"ResultCode": "1", "ResultDesc": log_entry.error_message}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """
    Secure webhook endpoint for Stripe event deliveries (`/payments/webhooks/stripe/`).
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        log_entry, result = process_webhook_payload(GatewayChoices.STRIPE, request)
        if result.get("success"):
            return JsonResponse({"status": "received", "event_id": log_entry.event_id}, status=200)
        return JsonResponse({"status": "error", "message": log_entry.error_message}, status=400)


class PaymentInitiateView(View):
    """
    Initiate payment processing for an existing order (`/payments/initiate/<order_number>/`).
    Creates `Payment` record and redirects customer to gateway checkout or confirmation screen.
    """
    def post(self, request: HttpRequest, order_number: str, *args: Any, **kwargs: Any) -> HttpResponse:
        session_key = getattr(request.session, "session_key", None)
        order = get_order(order_number=order_number, user=request.user, session_key=session_key)

        if not order:
            messages.error(request, "Order not found or access denied.")
            return redirect("orders:list" if request.user.is_authenticated else "accounts:login")

        if order.is_cancelled or order.is_paid:
            messages.warning(request, f"Order {order.order_number} cannot be processed for payment.")
            return redirect("orders:detail", order_number=order.order_number)

        gateway = request.POST.get("gateway", GatewayChoices.PAYPAL)
        phone_number = request.POST.get("phone_number", "")

        metadata = {}
        if phone_number:
            metadata["phone_number"] = phone_number

        try:
            payment = create_payment(order, gateway=gateway, metadata=metadata)
            return_url = request.build_absolute_uri(
                reverse("payments:return", kwargs={"payment_reference": payment.payment_reference})
            )
            cancel_url = request.build_absolute_uri(
                reverse("payments:cancel", kwargs={"payment_reference": payment.payment_reference})
            )

            payment, result = initiate_payment(
                payment,
                request=request,
                return_url=return_url,
                cancel_url=cancel_url,
                phone_number=phone_number,
            )

            if result.get("redirect_url"):
                return redirect(result["redirect_url"])

            if gateway == GatewayChoices.MPESA:
                messages.info(
                    request,
                    f"STK Push prompt sent to {phone_number}. Please enter your M-Pesa PIN on your phone to complete payment."
                )
                return redirect("orders:detail", order_number=order.order_number)

            messages.success(request, f"Payment initiated ({payment.payment_reference}).")
            return redirect("orders:detail", order_number=order.order_number)

        except Exception as str_e:
            messages.error(request, f"Unable to initiate payment: {str(str_e)}")
            return redirect("orders:detail", order_number=order.order_number)


class PaymentReturnView(View):
    """
    Endpoint where gateway redirects customer upon successful authorization (`/payments/return/<payment_reference>/`).
    Executes authoritative server-side verification before confirming order.
    """
    def get(self, request: HttpRequest, payment_reference: str, *args: Any, **kwargs: Any) -> HttpResponse:
        payment = get_object_or_404(Payment, payment_reference=payment_reference)

        # Extract gateway query parameters (e.g. PayPal token, PayerID, or mock status)
        token = request.GET.get("token")
        payer_id = request.GET.get("PayerID")
        simulated_status = request.GET.get("simulated_status", "COMPLETED")

        payment, verified = verify_payment(
            payment,
            token=token,
            PayerID=payer_id,
            simulated_status=simulated_status,
        )

        if verified or payment.is_completed:
            messages.success(
                request,
                f"Payment verified successfully! Your order {payment.order.order_number} is now confirmed."
            )
        else:
            messages.warning(
                request,
                f"Payment verification pending or failed for order {payment.order.order_number}. Please check status."
            )

        return redirect("orders:detail", order_number=payment.order.order_number)


class PaymentCancelView(View):
    """
    Endpoint where gateway redirects customer upon cancellation (`/payments/cancel/<payment_reference>/`).
    """
    def get(self, request: HttpRequest, payment_reference: str, *args: Any, **kwargs: Any) -> HttpResponse:
        payment = get_object_or_404(Payment, payment_reference=payment_reference)
        if not payment.is_completed and payment.status != PaymentStatus.CANCELLED:
            payment.status = PaymentStatus.CANCELLED
            payment.save(update_fields=["status", "updated_at"])

        messages.info(request, f"Payment attempt ({payment.payment_reference}) was cancelled.")
        return redirect("orders:detail", order_number=payment.order.order_number)
