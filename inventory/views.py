from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView

from dashboard.permissions import (
    DashboardPermissionRequiredMixin,
    dashboard_permission_required,
    has_dashboard_permission,
)
from dashboard.services import create_audit_log
from .forms import InventoryAdjustmentForm
from .models import Inventory, InventoryMovement
from .selectors import (
    damaged_inventory,
    inventory_value,
    low_stock_products,
    most_adjusted_products,
    out_of_stock_products,
    products_to_reorder,
    recent_movements,
    reserved_inventory,
)
from .services import adjust_stock, mark_damaged, process_return


def _inventory_summary_context() -> dict:
    return {
        "active_nav": "inventory",
        "inventory_value": inventory_value()["total"] or 0,
        "low_stock": low_stock_products(limit=8),
        "out_of_stock": out_of_stock_products(limit=8),
        "recent_movements": recent_movements(limit=8),
        "reserved": reserved_inventory()[:8],
        "damaged": damaged_inventory()[:8],
        "reorder": products_to_reorder(limit=8),
        "most_adjusted": most_adjusted_products(limit=8),
    }


class InventoryDashboardView(DashboardPermissionRequiredMixin, TemplateView):
    required_permissions = ["inventory.view_inventory"]
    template_name = "dashboard/inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_inventory_summary_context())
        return context


class InventoryMovementListView(DashboardPermissionRequiredMixin, ListView):
    required_permissions = ["inventory.view_inventory"]
    model = InventoryMovement
    template_name = "dashboard/inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 20

    def get_queryset(self):
        return InventoryMovement.objects.select_related("inventory", "inventory__product_variant", "performed_by").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_nav"] = "inventory"
        return context


@dashboard_permission_required("inventory.view_inventory")
def adjustment_form(request, pk):
    inventory = get_object_or_404(Inventory, pk=pk)
    if request.method == "POST":
        form = InventoryAdjustmentForm(request.POST)
        if form.is_valid():
            quantity = form.cleaned_data["quantity"]
            action = form.cleaned_data["action"]
            notes = form.cleaned_data["notes"]
            reason = form.cleaned_data["reason"]
            required_permission = "inventory.process_returns" if action == "return" else "inventory.adjust_inventory"
            if not has_dashboard_permission(request.user, required_permission):
                messages.error(request, "You do not have permission to perform that inventory action.")
                return redirect("inventory:dashboard")
            try:
                ledger_notes = f"[{reason}] {notes}".strip() if notes else reason
                if action == "increase":
                    inventory.add_stock(quantity, performed_by=request.user, notes=ledger_notes, movement_type="manual_increase", reference_type="staff_adjustment")
                elif action == "decrease":
                    inventory.remove_stock(quantity, performed_by=request.user, notes=ledger_notes, movement_type="manual_decrease", reference_type="staff_adjustment")
                elif action == "correction":
                    adjust_stock(inventory, quantity if quantity > 0 else -quantity, performed_by=request.user, reason=reason, notes=ledger_notes, reference_type="staff_adjustment")
                elif action == "damage":
                    mark_damaged(inventory, quantity, performed_by=request.user, notes=ledger_notes, reference_type="staff_adjustment")
                elif action == "return":
                    process_return(inventory, quantity, performed_by=request.user, notes=ledger_notes, reference_type="staff_adjustment")
                
                ip_address = request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None
                user_agent = request.META.get("HTTP_USER_AGENT", "")[:512] if hasattr(request, "META") and request.META.get("HTTP_USER_AGENT") else None
                create_audit_log(
                    user=request.user,
                    action="UPDATE",
                    model_name="Inventory",
                    object_id=str(inventory.pk),
                    description=f"Adjusted stock ({action}: {quantity}) — Reason: {reason or action.title()}",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                messages.success(request, "Inventory adjusted successfully.")
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect("inventory:dashboard")
    else:
        form = InventoryAdjustmentForm()
    return render(request, "dashboard/inventory/adjustment_form.html", {"form": form, "inventory": inventory, "active_nav": "inventory"})


@dashboard_permission_required("inventory.view_inventory")
def valuation_view(request):
    inventories = Inventory.objects.select_related("product_variant", "product_variant__product").all()
    total_value = sum(inv.valuation() for inv in inventories)
    return render(request, "dashboard/inventory/valuation.html", {"inventories": inventories, "total_value": total_value, "inventory_count": inventories.count(), "active_nav": "inventory"})


@dashboard_permission_required("inventory.view_inventory")
def alerts_view(request):
    return render(request, "dashboard/inventory/alerts.html", {"low_stock": low_stock_products(limit=20), "out_of_stock": out_of_stock_products(limit=20), "reorder": products_to_reorder(limit=20), "active_nav": "inventory"})


@dashboard_permission_required("inventory.view_inventory")
def product_inventory_view(request, pk):
    inventory = get_object_or_404(Inventory, pk=pk)
    movements = inventory.movements.select_related("performed_by").order_by("-created_at")[:10]
    return render(request, "dashboard/inventory/product_inventory.html", {"inventory": inventory, "movements": movements, "active_nav": "inventory"})


@dashboard_permission_required("inventory.view_inventory")
def stock_history_view(request, pk=None):
    if pk is not None:
        inventory = get_object_or_404(Inventory, pk=pk)
        movements = inventory.movements.select_related("performed_by").order_by("-created_at")[:50]
    else:
        inventory = None
        movements = InventoryMovement.objects.select_related("inventory", "inventory__product_variant", "performed_by").order_by("-created_at")[:100]
    return render(request, "dashboard/inventory/stock_history.html", {"inventory": inventory, "movements": movements, "active_nav": "inventory"})

