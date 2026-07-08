# checkout/urls.py
"""
checkout/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routes for the checkout foundation application.
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from checkout import views

app_name = "checkout"

urlpatterns = [
    path("", views.CheckoutStartView.as_view(), name="start"),
    path("shipping/", views.ShippingView.as_view(), name="shipping"),
    path("billing/", views.BillingView.as_view(), name="billing"),
    path("review/", views.CheckoutReviewView.as_view(), name="review"),
]
