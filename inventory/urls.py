from django.urls import path

from .views import (
    InventoryDashboardView,
    InventoryMovementListView,
    adjustment_form,
    alerts_view,
    product_inventory_view,
    stock_history_view,
    valuation_view,
)

app_name = "inventory"

urlpatterns = [
    path("dashboard/inventory/", InventoryDashboardView.as_view(), name="dashboard"),
    path("dashboard/inventory/movements/", InventoryMovementListView.as_view(), name="movement_list"),
    path("dashboard/inventory/adjust/<int:pk>/", adjustment_form, name="adjustment_form"),
    path("dashboard/inventory/valuation/", valuation_view, name="valuation"),
    path("dashboard/inventory/alerts/", alerts_view, name="alerts"),
    path("dashboard/inventory/history/<int:pk>/", stock_history_view, name="stock_history_for_inventory"),
    path("dashboard/inventory/history/", stock_history_view, name="stock_history"),
    path("dashboard/inventory/product/<int:pk>/", product_inventory_view, name="product_inventory"),
]
