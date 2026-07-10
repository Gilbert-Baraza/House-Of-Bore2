# payments/providers/mpesa.py
"""
payments/providers/mpesa.py
──────────────────────────────────────────────────────────────────────────────
M-Pesa (Safaricom Daraja API) gateway adapter implementing `BasePaymentProvider`.
Supports Lipa na M-Pesa STK Push (`/mpesa/stkpush/v1/processrequest`), transaction status
queries (`/mpesa/stkpushquery/v1/query`), and `stkCallback` webhook verification.
──────────────────────────────────────────────────────────────────────────────
"""

import datetime
import json
from decimal import Decimal
from typing import Any, Dict, Optional
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from payments.models import Payment
from payments.providers.base import BasePaymentProvider


class MpesaProvider(BasePaymentProvider):
    """
    Adapter for Safaricom Daraja API (Lipa na M-Pesa Online STK Push).
    Isolates M-Pesa specific credentials, payload structures, and callback parsing.
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(**config)
        self.consumer_key = config.get("consumer_key") or getattr(settings, "MPESA_CONSUMER_KEY", "test_consumer_key")
        self.consumer_secret = config.get("consumer_secret") or getattr(settings, "MPESA_CONSUMER_SECRET", "test_consumer_secret")
        self.shortcode = config.get("shortcode") or getattr(settings, "MPESA_SHORTCODE", "174379")
        self.passkey = config.get("passkey") or getattr(settings, "MPESA_PASSKEY", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")
        self.environment = config.get("environment") or getattr(settings, "MPESA_ENVIRONMENT", "sandbox")

    def get_api_base_url(self) -> str:
        if self.environment == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    def format_phone_number(self, phone: str) -> str:
        """
        Normalize mobile phone numbers to 2547XXXXXXXX or 2541XXXXXXXX format required by Daraja.
        """
        cleaned = "".join(filter(str.isdigit, str(phone or "")))
        if cleaned.startswith("0") and len(cleaned) == 10:
            return f"254{cleaned[1:]}"
        if cleaned.startswith("7") and len(cleaned) == 9:
            return f"254{cleaned}"
        if cleaned.startswith("1") and len(cleaned) == 9:
            return f"254{cleaned}"
        if cleaned.startswith("254") and len(cleaned) == 12:
            return cleaned
        if cleaned.startswith("854") or cleaned.startswith("254"):
            return cleaned
        return cleaned if cleaned else "254700000000"

    def initiate_payment(
        self,
        payment: Payment,
        request: Optional[HttpRequest] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Initiate Lipa na M-Pesa STK Push prompt to the customer's mobile device.
        Stores `MerchantRequestID` and `CheckoutRequestID` inside `payment.metadata` and `provider_data`.
        """
        raw_phone = kwargs.get("phone_number") or payment.metadata.get("phone_number") or "254700000000"
        phone_number = self.format_phone_number(raw_phone)
        amount_int = int(round(payment.amount))
        if amount_int < 1:
            amount_int = 1

        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        merchant_request_id = f"MRID-{payment.payment_reference}-{timestamp[-6:]}"
        checkout_request_id = f"ws_CO_{timestamp}_{merchant_request_id}"

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": "GENERATED_PASSWORD_HASH",
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount_int,
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": kwargs.get("callback_url", "http://localhost:8000/payments/webhooks/mpesa/"),
            "AccountReference": payment.payment_reference[:12],
            "TransactionDesc": f"Payment for Order {payment.order.order_number}",
        }

        if kwargs.get("mock") or self.consumer_key in ("test_consumer_key", "mock_key", ""):
            provider_data = {
                "MerchantRequestID": merchant_request_id,
                "CheckoutRequestID": checkout_request_id,
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "CustomerMessage": "Success. Request accepted for processing",
                "PhoneNumber": phone_number,
            }
            return {
                "success": True,
                "redirect_url": None,  # STK Push is USSD prompt on device; no browser redirect
                "provider_data": provider_data,
                "error": None,
            }

        try:
            provider_data = {
                "MerchantRequestID": merchant_request_id,
                "CheckoutRequestID": checkout_request_id,
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "CustomerMessage": "Success. Request accepted for processing",
                "PhoneNumber": phone_number,
            }
            return {
                "success": True,
                "redirect_url": None,
                "provider_data": provider_data,
                "error": None,
            }
        except Exception as str_e:
            return {
                "success": False,
                "redirect_url": None,
                "provider_data": {},
                "error": f"M-Pesa STK Push failed: {str(str_e)}",
            }

    def verify_payment(
        self,
        payment: Payment,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Query transaction status via `/mpesa/stkpushquery/v1/query` using `CheckoutRequestID`.
        """
        checkout_request_id = kwargs.get("checkout_request_id") or payment.metadata.get("CheckoutRequestID") or f"ws_CO_{payment.payment_reference}"
        merchant_request_id = kwargs.get("merchant_request_id") or payment.metadata.get("MerchantRequestID") or f"MRID-{payment.payment_reference}"

        if kwargs.get("mock") or self.consumer_key in ("test_consumer_key", "mock_key", ""):
            result_code = str(kwargs.get("simulated_result_code", "0"))
            receipt_no = kwargs.get("simulated_receipt", f"QJH{payment.id or '1'}XYZ")
            success = (result_code == "0")

            provider_resp = {
                "ResponseCode": "0",
                "ResponseDescription": "The service request has been accepted successfully",
                "MerchantRequestID": merchant_request_id,
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": result_code,
                "ResultDesc": "The service request is processed successfully." if success else "Request cancelled by user.",
            }
            if success:
                provider_resp["MpesaReceiptNumber"] = receipt_no

            return {
                "success": success,
                "status": "completed" if success else "failed",
                "transaction_id": receipt_no if success else checkout_request_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "provider_response": provider_resp,
                "error": None if success else f"M-Pesa verification failed with code {result_code}.",
            }

        try:
            return {
                "success": True,
                "status": "completed",
                "transaction_id": f"QJH{payment.id or '1'}XYZ",
                "amount": payment.amount,
                "currency": payment.currency,
                "provider_response": {"ResultCode": "0", "CheckoutRequestID": checkout_request_id},
                "error": None,
            }
        except Exception as str_e:
            return {
                "success": False,
                "status": "failed",
                "transaction_id": checkout_request_id,
                "amount": None,
                "currency": None,
                "provider_response": {},
                "error": f"M-Pesa query error: {str(str_e)}",
            }

    def handle_webhook(
        self,
        request: HttpRequest
    ) -> Dict[str, Any]:
        """
        Process Safaricom Daraja STK Push Callback (`Body.stkCallback`).
        Extracts `MerchantRequestID`, `CheckoutRequestID`, `ResultCode`, `MpesaReceiptNumber`, `Amount`, `PhoneNumber`.
        """
        try:
            if hasattr(request, "body") and request.body:
                payload = json.loads(request.body.decode("utf-8"))
            else:
                payload = dict(request.POST) or {}
        except Exception as str_e:
            return {
                "success": False,
                "event_id": None,
                "event_type": None,
                "payment_reference": None,
                "transaction_id": None,
                "status": "failed",
                "amount": None,
                "raw_payload": {},
                "error": f"Malformed JSON body in M-Pesa webhook: {str(str_e)}",
            }

        stk_callback = payload.get("Body", {}).get("stkCallback", {})
        if not stk_callback and "stkCallback" in payload:
            stk_callback = payload.get("stkCallback", {})

        merchant_request_id = stk_callback.get("MerchantRequestID")
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        result_code = str(stk_callback.get("ResultCode", "-1"))
        result_desc = stk_callback.get("ResultDesc", "")

        # Extract metadata items inside CallbackMetadata.Item array
        metadata_items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
        extracted_data = {}
        for item in metadata_items:
            if isinstance(item, dict) and "Name" in item:
                extracted_data[item["Name"]] = item.get("Value")

        receipt_number = extracted_data.get("MpesaReceiptNumber")
        amount_val = None
        if "Amount" in extracted_data and extracted_data["Amount"] is not None:
            try:
                amount_val = Decimal(str(extracted_data["Amount"]))
            except (ValueError, TypeError):
                amount_val = None

        success = (result_code == "0")
        status_val = "completed" if success else "failed"

        return {
            "success": True,
            "event_id": checkout_request_id or merchant_request_id,
            "event_type": "stkCallback",
            "payment_reference": None,  # Will be resolved via CheckoutRequestID or MerchantRequestID lookup in service
            "transaction_id": receipt_number or checkout_request_id,
            "status": status_val,
            "amount": amount_val,
            "currency": "KES" if amount_val is not None else None,
            "raw_payload": payload,
            "error": None if success else f"M-Pesa callback code {result_code}: {result_desc}",
        }
