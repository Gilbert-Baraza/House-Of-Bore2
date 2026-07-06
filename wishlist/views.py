# wishlist/views.py
"""
wishlist/views.py
──────────────────────────────────────────────────────────────────────────────
Class-based views for managing customer wishlists.

Enforces authentication via LoginRequiredMixin, delegates business logic to
services and selectors, implements pagination, and restricts mutating actions
strictly to POST requests for CSRF protection and HTTP semantic compliance.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import ListView, View

from products.models import Product
from wishlist.selectors import get_user_wishlist, get_wishlist_products
from wishlist.services import add_to_wishlist, clear_wishlist, remove_from_wishlist


class WishlistView(LoginRequiredMixin, ListView):
    """
    Renders the authenticated customer's wishlist page with pagination.
    """
    template_name = "wishlist/wishlist.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        return get_wishlist_products(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["wishlist"] = get_user_wishlist(self.request.user)
        context["active_nav"] = "wishlist"
        return context


class AddToWishlistView(LoginRequiredMixin, View):
    """
    Adds a specified product to the authenticated customer's wishlist.
    Strictly accepts POST requests to guarantee CSRF validation.
    """

    def post(self, request: HttpRequest, product_id: int) -> HttpResponse:
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        try:
            item, created = add_to_wishlist(request.user, product)
            if created:
                messages.success(request, f'"{product.name}" has been added to your wishlist.')
            else:
                messages.info(request, f'"{product.name}" is already in your wishlist.')
        except ValueError as e:
            messages.error(request, str(e))

        redirect_url = request.META.get("HTTP_REFERER") or reverse("wishlist:wishlist")
        return redirect(redirect_url)


class RemoveFromWishlistView(LoginRequiredMixin, View):
    """
    Removes a specified product from the authenticated customer's wishlist.
    Strictly accepts POST requests to guarantee CSRF validation.
    """

    def post(self, request: HttpRequest, product_id: int) -> HttpResponse:
        product = get_object_or_404(Product, pk=product_id)
        removed = remove_from_wishlist(request.user, product)
        if removed:
            messages.success(request, f'"{product.name}" has been removed from your wishlist.')
        else:
            messages.info(request, f'"{product.name}" was not found in your wishlist.')

        redirect_url = request.META.get("HTTP_REFERER") or reverse("wishlist:wishlist")
        return redirect(redirect_url)


class ClearWishlistView(LoginRequiredMixin, View):
    """
    Removes all items from the authenticated customer's wishlist.
    Strictly accepts POST requests to guarantee CSRF validation.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        count = clear_wishlist(request.user)
        if count > 0:
            messages.success(request, f"Cleared {count} items from your wishlist.")
        else:
            messages.info(request, "Your wishlist was already empty.")

        return redirect(reverse("wishlist:wishlist"))
