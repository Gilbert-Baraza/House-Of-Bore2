# cart/views.py
"""
cart/views.py
──────────────────────────────────────────────────────────────────────────────
Class-Based Views for the shopping cart system.
Keeps views thin by delegating business logic to services and queries to selectors.
Provides flash messaging and safe redirection.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from cart.selectors import get_cart, get_cart_items
from cart.services import (
    add_to_cart,
    update_quantity,
    remove_from_cart,
    clear_cart,
    calculate_totals,
)


class CartDetailView(TemplateView):
    """
    Render the interactive shopping cart page or the luxury empty state.
    """
    template_name = "cart/cart_detail.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        cart_obj = get_cart(self.request)
        items = get_cart_items(cart_obj)
        totals = calculate_totals(cart_obj)

        if totals["is_empty"]:
            self.template_name = "cart/cart_empty.html"

        context["cart_items"] = items
        context["cart_totals"] = totals
        return context


class AddToCartView(View):
    """
    Handle POST requests to add a product to the shopping bag.
    """
    def post(self, request: HttpRequest, product_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        quantity_str = request.POST.get("quantity", 1)
        try:
            quantity = int(quantity_str)
        except (ValueError, TypeError):
            quantity = 1

        variant_id_str = request.POST.get("variant_id") or request.GET.get("variant_id")
        variant_id = None
        if variant_id_str and str(variant_id_str).isdigit():
            variant_id = int(variant_id_str)

        try:
            item = add_to_cart(request, product_id=product_id, quantity=quantity, variant_id=variant_id)
            name = item.product.name
            if item.product_variant:
                name += f" ({item.product_variant.get_options_summary()})"
            messages.success(request, f"Added {name} to your shopping bag.")
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.error(request, msg)
        except Exception:
            messages.error(request, "We were unable to add this item to your bag at this time.")

        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("cart:cart_detail")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseRedirect:
        return redirect("cart:cart_detail")


class UpdateCartItemView(View):
    """
    Handle POST requests to update the quantity of a specific line item in the bag.
    """
    def post(self, request: HttpRequest, item_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        quantity_str = request.POST.get("quantity", 1)
        action = request.POST.get("action")  # 'decrease' or 'increase'

        try:
            quantity = int(quantity_str)
        except (ValueError, TypeError):
            quantity = 1

        try:
            item = update_quantity(request, item_id=item_id, quantity=quantity, action=action)
            if item:
                messages.success(request, f"Updated quantity for {item.product.name}.")
            else:
                messages.info(request, "Item removed from your shopping bag.")
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.error(request, msg)
        except Exception:
            messages.error(request, "We were unable to update your bag item at this time.")

        return redirect("cart:cart_detail")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseRedirect:
        return redirect("cart:cart_detail")


class RemoveCartItemView(View):
    """
    Handle POST requests to remove a specific line item from the bag.
    """
    def post(self, request: HttpRequest, item_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        removed = remove_from_cart(request, item_id=item_id)
        if removed:
            messages.info(request, "Item removed from your shopping bag.")
        else:
            messages.warning(request, "Item not found in your bag.")
        return redirect("cart:cart_detail")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseRedirect:
        return redirect("cart:cart_detail")


class ClearCartView(View):
    """
    Handle POST requests to remove all items from the shopping bag.
    """
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        clear_cart(request)
        messages.info(request, "Your shopping bag has been emptied.")
        return redirect("cart:cart_detail")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseRedirect:
        return redirect("cart:cart_detail")
