# orders/views.py
"""
orders/views.py
──────────────────────────────────────────────────────────────────────────────
Thin views handling order creation from checkout (`OrderCreateView`), customer
order history (`OrderListView`), and order confirmation / detail (`OrderDetailView`).
All query logic is delegated to `orders.selectors` and transactional mutations to `orders.services`.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from checkout.services import get_checkout
from orders.selectors import get_customer_orders, get_order, get_order_items
from orders.services import create_order


class OrderCreateView(LoginRequiredMixin, View):
    """
    POST-only endpoint triggered when the customer submits the final checkout review screen.
    Converts the validated checkout session into a permanent Order. Requires authentication.
    """
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            messages.info(request, "Please sign in or create an account to place your order.")
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path(), login_url=reverse("accounts:login"))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        checkout_session = get_checkout(request)
        if not checkout_session or not checkout_session.cart or checkout_session.cart.item_count() == 0:
            messages.error(request, "Your checkout session is invalid or your cart is empty.")
            return redirect("cart:cart_detail")

        customer_notes = request.POST.get("customer_notes", "")

        try:
            order = create_order(request, checkout_session, customer_notes=customer_notes)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else " ".join(e.messages)
            messages.warning(request, f"Unable to place order: {msg}")
            return redirect("checkout:review")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred while placing your order: {str(e)}")
            return redirect("checkout:review")

        # Save order number in session for guest access verification if needed
        request.session["last_order_number"] = order.order_number
        messages.success(request, f"Order {order.order_number} has been created successfully!")
        return redirect("orders:detail", order_number=order.order_number)


class OrderListView(LoginRequiredMixin, ListView):
    """
    Paginated list view displaying all historical orders for the currently logged-in customer.
    Route: /account/orders/
    """
    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 10

    def get_queryset(self):
        return get_customer_orders(self.request.user)


class OrderDetailView(View):
    """
    Order confirmation and historical detail screen.
    Verifies user or guest session access rights before rendering snapshotted order details.
    Route: /account/orders/<order_number>/
    """
    template_name = "orders/order_detail.html"

    def get(self, request: HttpRequest, order_number: str, *args: Any, **kwargs: Any) -> HttpResponse:
        session_key = getattr(request.session, "session_key", None)
        order = get_order(order_number=order_number, user=request.user, session_key=session_key)

        if not order:
            if request.user.is_authenticated:
                messages.error(request, "Order not found or you do not have permission to view it.")
                return redirect("orders:list")
            else:
                messages.error(request, "Order not found or your session has expired. Please log in if you have an account.")
                return redirect("accounts:login")

        order_items = get_order_items(order)

        return render(request, self.template_name, {
            "order": order,
            "order_items": order_items,
        })
