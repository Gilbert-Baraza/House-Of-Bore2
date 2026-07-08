# pricing/urls.py
"""
pricing/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for pricing operations such as coupon application and removal.
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from pricing import views

app_name = "pricing"

urlpatterns = [
    path("coupon/apply/", views.ApplyCouponView.as_view(), name="apply_coupon"),
    path("coupon/remove/", views.RemoveCouponView.as_view(), name="remove_coupon"),
]
