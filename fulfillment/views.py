# fulfillment/views.py
"""
fulfillment/views.py
──────────────────────────────────────────────────────────────────────────────
Thin presentation layer for the Order Fulfillment & Shipping Operations engine.
Delegates all database queries to `fulfillment.selectors` and all mutations and
workflow state transitions to `fulfillment.services`.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView

from dashboard.permissions import (
    DashboardPermissionRequiredMixin,
    dashboard_permission_required,
    has_dashboard_permission,
)
from dashboard.services import create_audit_log
from .forms import (
    PackingCompletionForm,
    PickingItemVerificationForm,
    ReturnInspectionForm,
    ShipmentCreationForm,
    StaffAssignmentForm,
)
from .models import FulfillmentOrder, FulfillmentWorkflowStatus, ReturnExchangeRequest
from .selectors import (
    active_shipments,
    delivery_exceptions,
    fulfillment_statistics,
    get_fulfillment_by_id,
    pending_packs,
    pending_picks,
    ready_for_dispatch,
    recent_events,
    return_exchange_requests,
)
from .services import (
    assign_order,
    cancel_fulfillment,
    complete_packing,
    complete_picking,
    confirm_delivery,
    create_shipment,
    dispatch_order,
    fulfillment_timeline,
    initiate_return,
    process_return_inspection,
    start_packing,
    start_picking,
)


class FulfillmentDashboardView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Central operational command center displaying real-time queues, statistics,
    and recent activity events.
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "fulfillment"
        context["stats"] = fulfillment_statistics()
        context["pending_picks"] = pending_picks()[:8]
        context["pending_packs"] = pending_packs()[:8]
        context["ready_dispatch"] = ready_for_dispatch()[:8]
        context["active_shipments"] = active_shipments()[:8]
        context["exceptions"] = delivery_exceptions()[:8]
        context["recent_events"] = recent_events(limit=12)
        return context


class OrderQueueView(DashboardPermissionRequiredMixin, ListView):
    """
    Filtered queue interface (`picking`, `packing`, `dispatch`, `exceptions`, `all`).
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/order_queue.html"
    context_object_name = "fulfillments"
    paginate_by = 25

    def get_queryset(self):
        queue_type = self.request.GET.get("queue", "all")
        if queue_type == "picking":
            return pending_picks()
        elif queue_type == "packing":
            return pending_packs()
        elif queue_type == "dispatch":
            return ready_for_dispatch()
        elif queue_type == "exceptions":
            return delivery_exceptions()
        from .selectors import _base_fulfillment_queryset
        return _base_fulfillment_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "fulfillment"
        context["queue_type"] = self.request.GET.get("queue", "all")
        context["stats"] = fulfillment_statistics()
        return context


class PickingView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Detail interface directing warehouse picking associates.
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/picking.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fo = get_object_or_404(FulfillmentOrder, pk=self.kwargs["pk"])
        context["active_nav"] = "fulfillment"
        context["fulfillment"] = fo
        context["assignment_form"] = StaffAssignmentForm(initial={"role": "picker", "staff_user": fo.assigned_picker})
        return context


class PackingView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Detail interface directing warehouse packing associates and box dimension entry.
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/packing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fo = get_object_or_404(FulfillmentOrder, pk=self.kwargs["pk"])
        context["active_nav"] = "fulfillment"
        context["fulfillment"] = fo
        context["assignment_form"] = StaffAssignmentForm(initial={"role": "packer", "staff_user": fo.assigned_packer})
        context["packing_form"] = PackingCompletionForm(initial={"notes": fo.internal_notes})
        return context


class ShipmentDetailView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Carrier label generation, tracking assignment, and courier integration interface.
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/shipment_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fo = get_object_or_404(FulfillmentOrder, pk=self.kwargs["pk"])
        shipment = fo.shipments.first()
        context["active_nav"] = "fulfillment"
        context["fulfillment"] = fo
        context["shipment"] = shipment
        initial_data = {
            "courier": shipment.courier if shipment else "FedEx Ground",
            "shipping_method": shipment.shipping_method if shipment else "Standard Ground",
            "tracking_number": shipment.tracking_number if shipment else "",
            "shipping_cost": shipment.shipping_cost if shipment else 0.00,
            "length": shipment.package_length if shipment else None,
            "width": shipment.package_width if shipment else None,
            "height": shipment.package_height if shipment else None,
            "weight": shipment.package_weight if shipment else None,
        }
        context["shipment_form"] = ShipmentCreationForm(initial=initial_data)
        return context


class ShipmentTimelineView(DashboardPermissionRequiredMixin, TemplateView):
    """
    Chronological tracking progression displaying picking, packing, dispatch, and delivery timestamps.
    """
    required_permissions = ["fulfillment.view_fulfillment"]
    template_name = "dashboard/fulfillment/shipment_timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fo = get_object_or_404(FulfillmentOrder, pk=self.kwargs["pk"])
        context["active_nav"] = "fulfillment"
        context["fulfillment"] = fo
        context["timeline"] = fulfillment_timeline(fo)
        return context


class ReturnsListView(DashboardPermissionRequiredMixin, ListView):
    """
    RMA returns inspection queue.
    """
    required_permissions = ["fulfillment.manage_returns"]
    template_name = "dashboard/fulfillment/returns.html"
    context_object_name = "rmas"
    paginate_by = 20

    def get_queryset(self):
        return return_exchange_requests().filter(request_type="return")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "fulfillment"
        return context


class ExchangeRequestsView(DashboardPermissionRequiredMixin, ListView):
    """
    RMA exchange inspection queue.
    """
    required_permissions = ["fulfillment.manage_returns"]
    template_name = "dashboard/fulfillment/exchange_requests.html"
    context_object_name = "rmas"
    paginate_by = 20

    def get_queryset(self):
        return return_exchange_requests().filter(request_type="exchange")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "fulfillment"
        return context


# ─── ACTION ENDPOINTS (MUTATIONS) ─────────────────────────────────────────────
@dashboard_permission_required("fulfillment.assign_orders")
def assign_order_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        form = StaffAssignmentForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data["role"]
            staff_user = form.cleaned_data["staff_user"]
            try:
                assign_order(fo, staff_user=staff_user, role=role, performed_by=request.user)
                create_audit_log(
                    user=request.user,
                    action="UPDATE",
                    model_name="FulfillmentOrder",
                    object_id=str(fo.pk),
                    description=f"Assigned {role} ({getattr(staff_user, 'email', 'Unassigned')}) to order {fo.order.order_number}.",
                )
                messages.success(request, f"Staff assignment ({role}) updated successfully.")
            except Exception as exc:
                messages.error(request, str(exc))
    return redirect(request.META.get("HTTP_REFERER", "fulfillment:dashboard"))


@dashboard_permission_required("fulfillment.pick_orders")
def start_picking_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        try:
            start_picking(fo, picker=request.user, performed_by=request.user)
            messages.success(request, f"Picking started for order {fo.order.order_number}.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:picking", pk=fo.pk)


@dashboard_permission_required("fulfillment.pick_orders")
def complete_picking_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        picked_data = []
        for key, value in request.POST.items():
            if key.startswith("picked_qty_"):
                item_id = int(key.split("_")[-1])
                picked_qty = int(value or 0)
                missing_qty = int(request.POST.get(f"missing_qty_{item_id}", 0))
                notes = request.POST.get(f"item_notes_{item_id}", "").strip()
                picked_data.append({
                    "item_id": item_id,
                    "picked_quantity": picked_qty,
                    "missing_quantity": missing_qty,
                    "notes": notes,
                })
        try:
            complete_picking(fo, picked_items_data=picked_data or None, performed_by=request.user, notes=request.POST.get("picking_notes", ""))
            create_audit_log(
                user=request.user,
                action="UPDATE",
                model_name="FulfillmentOrder",
                object_id=str(fo.pk),
                description=f"Completed picking verification for {fo.order.order_number}.",
            )
            messages.success(request, "Picking verification finalized and marked PICKED.")
            return redirect("fulfillment:packing", pk=fo.pk)
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:picking", pk=fo.pk)


@dashboard_permission_required("fulfillment.pack_orders")
def start_packing_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        try:
            start_packing(fo, packer=request.user, performed_by=request.user)
            messages.success(request, f"Packing started for order {fo.order.order_number}.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:packing", pk=fo.pk)


@dashboard_permission_required("fulfillment.pack_orders")
def complete_packing_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        form = PackingCompletionForm(request.POST)
        if form.is_valid():
            try:
                complete_packing(fo, performed_by=request.user, notes=form.cleaned_data["notes"])
                create_audit_log(
                    user=request.user,
                    action="UPDATE",
                    model_name="FulfillmentOrder",
                    object_id=str(fo.pk),
                    description=f"Completed packing verification for {fo.order.order_number}.",
                )
                messages.success(request, "Packing completed. Order is READY FOR DISPATCH.")
                return redirect("fulfillment:shipment_detail", pk=fo.pk)
            except Exception as exc:
                messages.error(request, str(exc))
    return redirect("fulfillment:packing", pk=fo.pk)


@dashboard_permission_required("fulfillment.dispatch_orders")
def create_shipment_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        form = ShipmentCreationForm(request.POST)
        if form.is_valid():
            try:
                dims = {
                    "length": form.cleaned_data.get("length"),
                    "width": form.cleaned_data.get("width"),
                    "height": form.cleaned_data.get("height"),
                    "weight": form.cleaned_data.get("weight"),
                }
                shipment = create_shipment(
                    fulfillment_order=fo,
                    courier=form.cleaned_data["courier"],
                    shipping_method=form.cleaned_data["shipping_method"],
                    tracking_number=form.cleaned_data.get("tracking_number", "").strip(),
                    shipping_cost=form.cleaned_data.get("shipping_cost") or 0.00,
                    dimensions=dims,
                    performed_by=request.user,
                )
                create_audit_log(
                    user=request.user,
                    action="CREATE",
                    model_name="Shipment",
                    object_id=str(shipment.pk),
                    description=f"Created shipment label ({shipment.courier}) for order {fo.order.order_number}.",
                )
                messages.success(request, f"Shipment created successfully. Tracking: {shipment.tracking_number}")
            except Exception as exc:
                messages.error(request, str(exc))
    return redirect("fulfillment:shipment_detail", pk=fo.pk)


@dashboard_permission_required("fulfillment.dispatch_orders")
def dispatch_order_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        try:
            dispatch_order(fo, performed_by=request.user, notes=request.POST.get("dispatch_notes", ""))
            create_audit_log(
                user=request.user,
                action="UPDATE",
                model_name="FulfillmentOrder",
                object_id=str(fo.pk),
                description=f"Dispatched order {fo.order.order_number} via courier.",
            )
            messages.success(request, f"Order {fo.order.order_number} marked SHIPPED & IN TRANSIT.")
            return redirect("fulfillment:timeline", pk=fo.pk)
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:shipment_detail", pk=fo.pk)


@dashboard_permission_required("fulfillment.confirm_delivery")
def confirm_delivery_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        try:
            confirm_delivery(fo, performed_by=request.user, notes=request.POST.get("delivery_notes", ""))
            create_audit_log(
                user=request.user,
                action="UPDATE",
                model_name="FulfillmentOrder",
                object_id=str(fo.pk),
                description=f"Confirmed delivery for order {fo.order.order_number}.",
            )
            messages.success(request, f"Order {fo.order.order_number} marked DELIVERED.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:timeline", pk=fo.pk)


@dashboard_permission_required("fulfillment.manage_returns")
def initiate_return_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        notes = request.POST.get("notes", "").strip()
        if not reason:
            messages.error(request, "A reason must be provided to initiate an RMA return.")
            return redirect("fulfillment:timeline", pk=fo.pk)
        try:
            rma = initiate_return(fo, reason=reason, performed_by=request.user, notes=notes)
            create_audit_log(
                user=request.user,
                action="CREATE",
                model_name="ReturnExchangeRequest",
                object_id=str(rma.pk),
                description=f"Initiated return request for order {fo.order.order_number}.",
            )
            messages.success(request, f"RMA return request #{rma.pk} created successfully.")
            return redirect("fulfillment:returns")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:timeline", pk=fo.pk)


@dashboard_permission_required("fulfillment.manage_returns")
def process_rma_view(request, rma_pk):
    rma = get_object_or_404(ReturnExchangeRequest, pk=rma_pk)
    if request.method == "POST":
        form = ReturnInspectionForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data["action"]
            notes = form.cleaned_data["notes"]
            try:
                process_return_inspection(rma, action=action, performed_by=request.user, notes=notes)
                create_audit_log(
                    user=request.user,
                    action="UPDATE",
                    model_name="ReturnExchangeRequest",
                    object_id=str(rma.pk),
                    description=f"Processed RMA #{rma.pk} ({action.upper()}).",
                )
                messages.success(request, f"RMA request #{rma.pk} updated to {rma.get_status_display()}.")
            except Exception as exc:
                messages.error(request, str(exc))
    redirect_url = "fulfillment:returns" if rma.request_type == "return" else "fulfillment:exchanges"
    return redirect(redirect_url)


@dashboard_permission_required("fulfillment.dispatch_orders")
def cancel_fulfillment_view(request, pk):
    fo = get_object_or_404(FulfillmentOrder, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "Cancelled by operational staff").strip()
        try:
            cancel_fulfillment(fo, reason=reason, performed_by=request.user)
            create_audit_log(
                user=request.user,
                action="UPDATE",
                model_name="FulfillmentOrder",
                object_id=str(fo.pk),
                description=f"Cancelled fulfillment for order {fo.order.order_number} ({reason}).",
            )
            messages.success(request, f"Fulfillment for order {fo.order.order_number} has been cancelled.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("fulfillment:dashboard")
