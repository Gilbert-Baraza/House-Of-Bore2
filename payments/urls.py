# payments/urls.py
"""
payments/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routes for gateway webhooks and customer payment navigation.
Namespace: "payments"
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from payments import views

app_name = "payments"

urlpatterns = [
    # Gateway initiation and browser return/cancel navigation
    path("initiate/<str:order_number>/", views.PaymentInitiateView.as_view(), name="initiate"),
    path("return/<str:payment_reference>/", views.PaymentReturnView.as_view(), name="return"),
    path("cancel/<str:payment_reference>/", views.PaymentCancelView.as_view(), name="cancel"),

    # Idempotent gateway webhook endpoints
    path("webhooks/paypal/", views.PayPalWebhookView.as_view(), name="webhook_paypal"),
    path("webhooks/mpesa/", views.MpesaWebhookView.as_view(), name="webhook_mpesa"),
    path("webhooks/stripe/", views.StripeWebhookView.as_view(), name="webhook_stripe"),
]
