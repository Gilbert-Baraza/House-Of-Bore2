# dashboard/order_views.py
"""
dashboard/order_views.py
──────────────────────────────────────────────────────────────────────────────
Administrative presentation and action controller for customer orders.
Provides store managers and customer service personnel with paginated order
queues, detailed order audit views, controlled status transition endpoints,
and fulfillment workflow bridges.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from dashboard.permissions import DashboardPermissionRequiredMixin, has_dashboard_permission
from dashboard.services import create_audit_log
from fulfillment.services import create_fulfillment_order
from orders.models import Order, OrderStatus, PaymentStatus
from orders.selectors import get_admin_orders, get_admin_order_statistics, get_order
from orders.services import transition_order_status


class StaffOrdersListView(DashboardPermissionRequiredMixin, ListView):
    """
    Paginated administrative order queue with multi-dimensional filtering
    (status, payment status, keyword search) and summary KPI cards.
    """
    required_permissions = ["orders.view_order"]
    template_name = "dashboard/orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        status_filter = self.request.GET.get("status", "all")
        payment_filter = self.request.GET.get("payment_status", "all")
        search_query = self.request.GET.get("search", "")
        return get_admin_orders(
            status=status_filter,
            payment_status=payment_filter,
            search=search_query,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "orders",
            "stats": get_admin_order_statistics(),
            "status_filter": self.request.GET.get("status", "all"),
            "payment_filter": self.request.GET.get("payment_status", "all"),
            "search_query": self.request.GET.get("search", ""),
            "order_statuses": OrderStatus.choices,
            "payment_statuses": PaymentStatus.choices,
            "can_change_order": has_dashboard_permission(self.request.user, "orders.change_order"),
        })
        return context


class StaffOrderDetailView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Complete administrative inspection view for a customer order.
    Displays financial breakdowns, address snapshots, line items, payment status,
    and operational fulfillment links.
    """
    required_permissions = ["orders.view_order"]
    template_name = "dashboard/orders/order_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        order_number = self.kwargs["order_number"]
        order = get_order(order_number=order_number, user=self.request.user)
        if not order:
            raise Http404(f"Order {order_number} does not exist or access is restricted.")

        context.update({
            "active_nav": "orders",
            "order": order,
            "items": order.items.all(),
            "fulfillment": getattr(order, "fulfillment_order", None),
            "shipping_addr": order.shipping_address_snapshot or {},
            "billing_addr": order.billing_address_snapshot or {},
            "order_statuses": OrderStatus.choices,
            "can_change_order": has_dashboard_permission(self.request.user, "orders.change_order"),
        })
        return context


class StaffOrderTransitionView(DashboardPermissionRequiredMixin, View):
    """
    POST-only endpoint for performing atomic order status transitions.
    """
    required_permissions = ["orders.change_order"]

    def post(self, request: HttpRequest, order_number: str, *args: Any, **kwargs: Any) -> HttpResponse:
        order = get_order(order_number=order_number, user=request.user)
        if not order:
            raise Http404(f"Order {order_number} not found.")

        new_status = request.POST.get("new_status", "").strip()
        note = request.POST.get("note", "").strip()

        try:
            old_status_label = order.get_status_display()
            transition_order_status(order=order, new_status=new_status, note=note)
            new_status_label = order.get_status_display()

            create_audit_log(
                user=request.user,
                action="UPDATE",
                model_name="Order",
                object_id=str(order.pk),
                description=f"Transitioned order {order.order_number} from '{old_status_label}' to '{new_status_label}'.",
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Order {order.order_number} status updated to {new_status_label}.")
        except Exception as exc:
            messages.error(request, f"Failed to transition status: {str(exc)}")

        return redirect("dashboard:order_detail", order_number=order.order_number)


class StaffOrderNotesUpdateView(DashboardPermissionRequiredMixin, View):
    """
    POST-only endpoint for modifying customer notes or administrative order notes.
    """
    required_permissions = ["orders.change_order"]

    def post(self, request: HttpRequest, order_number: str, *args: Any, **kwargs: Any) -> HttpResponse:
        order = get_order(order_number=order_number, user=request.user)
        if not order:
            raise Http404(f"Order {order_number} not found.")

        customer_notes = request.POST.get("customer_notes", "").strip()
        order.customer_notes = customer_notes
        order.save(update_fields=["customer_notes", "updated_at"])

        create_audit_log(
            user=request.user,
            action="UPDATE",
            model_name="Order",
            object_id=str(order.pk),
            description=f"Updated customer/delivery notes for order {order.order_number}.",
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Notes for order {order.order_number} updated successfully.")
        return redirect("dashboard:order_detail", order_number=order.order_number)


class StaffOrderCreateFulfillmentView(DashboardPermissionRequiredMixin, View):
    """
    POST-only endpoint to initialize a FulfillmentOrder and jump directly to
    the warehouse processing timeline.
    """
    required_permissions = ["orders.change_order"]

    def post(self, request: HttpRequest, order_number: str, *args: Any, **kwargs: Any) -> HttpResponse:
        order = get_order(order_number=order_number, user=request.user)
        if not order:
            raise Http404(f"Order {order_number} not found.")

        try:
            fo = create_fulfillment_order(order=order, performed_by=request.user)
            create_audit_log(
                user=request.user,
                action="CREATE",
                model_name="FulfillmentOrder",
                object_id=str(fo.pk),
                description=f"Initialized fulfillment workflow for order {order.order_number}.",
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Fulfillment workflow initialized for order {order.order_number}.")
            return redirect("fulfillment:timeline", pk=fo.pk)
        except Exception as exc:
            messages.error(request, f"Could not create fulfillment order: {str(exc)}")
            return redirect("dashboard:order_detail", order_number=order.order_number)
