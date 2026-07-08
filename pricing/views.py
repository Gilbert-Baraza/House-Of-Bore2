# pricing/views.py
"""
pricing/views.py
──────────────────────────────────────────────────────────────────────────────
Views for applying and removing promotional coupon codes during shopping and checkout.
Keep views thin by delegating validation and application logic to pricing.services.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View
from cart.selectors import get_cart
from pricing.forms import CouponApplyForm
from pricing.services import apply_coupon_to_cart, remove_coupon_from_cart


class ApplyCouponView(View):
    """
    Handle POST submissions to apply a discount coupon code to the active shopping bag.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = CouponApplyForm(request.POST)
        redirect_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "cart:cart_detail"

        if not form.is_valid():
            messages.error(request, "Please enter a valid promotional code.")
            return redirect(redirect_url)

        cart = get_cart(request)
        if not cart or cart.item_count() == 0:
            messages.error(request, "Your shopping bag is empty. Add items before applying a promo code.")
            return redirect(redirect_url)

        code = form.cleaned_data["code"]
        try:
            coupon = apply_coupon_to_cart(cart, code)
            messages.success(request, f"Promotional code '{coupon.code}' applied successfully (-${coupon.discount_value:.2f}).")
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.error(request, msg)

        return redirect(redirect_url)


class RemoveCouponView(View):
    """
    Handle POST submissions to detach any applied discount coupon from the active shopping bag.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        redirect_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "cart:cart_detail"
        cart = get_cart(request)
        if cart:
            remove_coupon_from_cart(cart)
            messages.success(request, "Promotional code removed.")
        return redirect(redirect_url)
