# checkout/views.py
"""
checkout/views.py
──────────────────────────────────────────────────────────────────────────────
Class-Based Views for the checkout workflow pipeline.
Maintains thin views by delegating business operations to services and queries
to selectors. Includes form validation, saved address lookups, notes persistence,
and redirection validation.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from cart.selectors import get_cart
from checkout.services import (
    get_or_create_checkout,
    update_shipping,
    update_billing,
    validate_checkout,
    checkout_summary,
)
from checkout.selectors import get_checkout
from checkout.forms import CheckoutAddressForm, CheckoutNotesForm
from accounts.models import Address
from accounts.services import create_address


class CheckoutBaseView(LoginRequiredMixin, View):
    """
    Base validation view ensuring checkout can only be accessed by authenticated users with a non-empty cart.
    Redirects to login if unauthenticated, or back to shopping bag detail with a flash warning if cart is empty.
    """
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            messages.info(request, "Please sign in or create an account to proceed to checkout.")
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path(), login_url=reverse("accounts:login"))
        cart = get_cart(request)
        if not cart or cart.item_count() == 0:
            messages.warning(request, "Your shopping bag is empty. Please add pieces to proceed to checkout.")
            return redirect("cart:cart_detail")
        return super().dispatch(request, *args, **kwargs)


class CheckoutStartView(CheckoutBaseView, TemplateView):
    """
    Landing and step initialization view for Checkout.
    Generates the transient CheckoutSession and forwards the user.
    """
    template_name = "checkout/checkout.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        checkout_session = get_or_create_checkout(self.request)
        context["checkout_session"] = checkout_session
        return context


class ShippingView(CheckoutBaseView):
    """
    Handles rendering and processing of customer shipping address selection/entry,
    as well as delivery notes.
    """
    template_name = "checkout/shipping.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_or_create_checkout(request)
        
        # Prefill form with snapshotted address if already filled
        initial_data = {}
        if checkout_session.shipping_address:
            addr = checkout_session.shipping_address
            initial_data = {
                "recipient_name": addr.recipient_name,
                "phone_number": addr.phone_number,
                "company_name": addr.company_name,
                "address_line_1": addr.address_line_1,
                "address_line_2": addr.address_line_2,
                "city": addr.city,
                "county_or_state": addr.county_or_state,
                "postal_code": addr.postal_code,
                "country": addr.country,
            }
        
        form = CheckoutAddressForm(initial=initial_data)
        saved_addresses = request.user.addresses.all() if request.user.is_authenticated else []
        notes_form = CheckoutNotesForm(initial={"notes": checkout_session.notes})

        return render(request, self.template_name, {
            "form": form,
            "saved_addresses": saved_addresses,
            "checkout_session": checkout_session,
            "notes_form": notes_form,
        })

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_or_create_checkout(request)
        
        # Parse notes
        notes_form = CheckoutNotesForm(request.POST)
        if notes_form.is_valid():
            checkout_session.notes = notes_form.cleaned_data["notes"]
            checkout_session.save()

        # Check if user submitted a saved address ID from their profile Address Book
        saved_address_id = request.POST.get("saved_address_id")
        if request.user.is_authenticated and saved_address_id:
            try:
                saved_addr = Address.objects.get(pk=saved_address_id, user=request.user)
                address_data = {
                    "recipient_name": saved_addr.recipient_name,
                    "phone_number": saved_addr.phone_number,
                    "company_name": saved_addr.company_name,
                    "address_line_1": saved_addr.address_line_1,
                    "address_line_2": saved_addr.address_line_2,
                    "city": saved_addr.city,
                    "county_or_state": saved_addr.county_or_state,
                    "postal_code": saved_addr.postal_code,
                    "country": saved_addr.country,
                }
                update_shipping(checkout_session, address_data)
                messages.success(request, "Shipping address selected.")
                return redirect("checkout:billing")
            except Address.DoesNotExist:
                messages.error(request, "The selected saved address could not be found.")
                return redirect("checkout:shipping")

        # Fallback to validating new address entry
        form = CheckoutAddressForm(request.POST)
        if form.is_valid():
            address_data = form.cleaned_data
            update_shipping(checkout_session, address_data)
            
            # Persist address into customer's profile Address Book if requested
            if request.user.is_authenticated and request.POST.get("save_to_profile") == "true":
                try:
                    create_address(
                        user=request.user,
                        label=f"Shipping ({address_data['city']})",
                        address_type="shipping",
                        **address_data
                    )
                    messages.info(request, "Address saved to your profile Address Book.")
                except Exception:
                    pass

            return redirect("checkout:billing")

        saved_addresses = request.user.addresses.all() if request.user.is_authenticated else []
        return render(request, self.template_name, {
            "form": form,
            "saved_addresses": saved_addresses,
            "checkout_session": checkout_session,
            "notes_form": notes_form,
        })


class BillingView(CheckoutBaseView):
    """
    Handles rendering and processing of billing address selection/entry.
    Supports a toggle to share the shipping address details.
    """
    template_name = "checkout/billing.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_or_create_checkout(request)
        
        initial_data = {}
        if checkout_session.billing_address:
            addr = checkout_session.billing_address
            initial_data = {
                "recipient_name": addr.recipient_name,
                "phone_number": addr.phone_number,
                "company_name": addr.company_name,
                "address_line_1": addr.address_line_1,
                "address_line_2": addr.address_line_2,
                "city": addr.city,
                "county_or_state": addr.county_or_state,
                "postal_code": addr.postal_code,
                "country": addr.country,
            }
        elif checkout_session.shipping_address:
            # Smart default: prefill billing form from shipping address
            addr = checkout_session.shipping_address
            initial_data = {
                "recipient_name": addr.recipient_name,
                "phone_number": addr.phone_number,
                "company_name": addr.company_name,
                "address_line_1": addr.address_line_1,
                "address_line_2": addr.address_line_2,
                "city": addr.city,
                "county_or_state": addr.county_or_state,
                "postal_code": addr.postal_code,
                "country": addr.country,
            }

        form = CheckoutAddressForm(initial=initial_data)
        saved_addresses = request.user.addresses.all() if request.user.is_authenticated else []
        return render(request, self.template_name, {
            "form": form,
            "saved_addresses": saved_addresses,
            "checkout_session": checkout_session,
        })

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_or_create_checkout(request)
        billing_same = request.POST.get("billing_same_as_shipping") == "true"

        if billing_same:
            update_billing(checkout_session, {}, billing_same_as_shipping=True)
            messages.success(request, "Billing set to match shipping address.")
            return redirect("checkout:review")

        # Check if user selected a saved address from profile
        saved_address_id = request.POST.get("saved_address_id")
        if request.user.is_authenticated and saved_address_id:
            try:
                saved_addr = Address.objects.get(pk=saved_address_id, user=request.user)
                address_data = {
                    "recipient_name": saved_addr.recipient_name,
                    "phone_number": saved_addr.phone_number,
                    "company_name": saved_addr.company_name,
                    "address_line_1": saved_addr.address_line_1,
                    "address_line_2": saved_addr.address_line_2,
                    "city": saved_addr.city,
                    "county_or_state": saved_addr.county_or_state,
                    "postal_code": saved_addr.postal_code,
                    "country": saved_addr.country,
                }
                update_billing(checkout_session, address_data, billing_same_as_shipping=False)
                messages.success(request, "Billing address selected.")
                return redirect("checkout:review")
            except Address.DoesNotExist:
                messages.error(request, "The selected saved address could not be found.")
                return redirect("checkout:billing")

        # Validate billing address entry form
        form = CheckoutAddressForm(request.POST)
        if form.is_valid():
            address_data = form.cleaned_data
            update_billing(checkout_session, address_data, billing_same_as_shipping=False)
            
            # Persist address into customer's profile Address Book if requested
            if request.user.is_authenticated and request.POST.get("save_to_profile") == "true":
                try:
                    create_address(
                        user=request.user,
                        label=f"Billing ({address_data['city']})",
                        address_type="billing",
                        **address_data
                    )
                    messages.info(request, "Address saved to your profile Address Book.")
                except Exception:
                    pass

            return redirect("checkout:review")

        saved_addresses = request.user.addresses.all() if request.user.is_authenticated else []
        return render(request, self.template_name, {
            "form": form,
            "saved_addresses": saved_addresses,
            "checkout_session": checkout_session,
        })


class CheckoutReviewView(CheckoutBaseView):
    """
    Renders the final order and validation check screen.
    Displays snapshotted details, order subtotal summary calculations,
    and placeholders for taxes and shipping.
    """
    template_name = "checkout/review.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_checkout(request)
        if not checkout_session:
            return redirect("checkout:shipping")

        try:
            # Perform inventory check, cart validation, and address complete check
            validate_checkout(checkout_session)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.warning(request, f"Review error: {msg}")
            
            # Safety checks redirecting to correct correction step
            if not checkout_session.shipping_address:
                return redirect("checkout:shipping")
            if not checkout_session.billing_same_as_shipping and not checkout_session.billing_address:
                return redirect("checkout:billing")
            return redirect("cart:cart_detail")

        summary = checkout_summary(checkout_session)
        cart_items = checkout_session.cart.items.all().select_related("product__brand", "product_variant")

        return render(request, self.template_name, {
            "checkout_session": checkout_session,
            "checkout_totals": summary,
            "cart_items": cart_items,
        })
