# fulfillment/urls.py
"""
fulfillment/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for the Order Fulfillment & Shipping Operations dashboard.
Includes:
1. Operational queues (`dashboard/fulfillment/`, `dashboard/fulfillment/queue/`)
2. Workflow interfaces (`picking/<pk>/`, `packing/<pk>/`, `shipment/<pk>/`, `timeline/<pk>/`)
3. RMA requests (`returns/`, `exchanges/`)
4. Action mutations (`assign/<pk>/`, `pick/start/<pk>/`, `pick/complete/<pk>/`, etc.)
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from . import views

app_name = "fulfillment"

urlpatterns = [
    # Dashboard & Queues
    path("dashboard/fulfillment/", views.FulfillmentDashboardView.as_view(), name="dashboard"),
    path("dashboard/fulfillment/queue/", views.OrderQueueView.as_view(), name="queue"),

    # Detail Workflow Views
    path("dashboard/fulfillment/<int:pk>/picking/", views.PickingView.as_view(), name="picking"),
    path("dashboard/fulfillment/<int:pk>/packing/", views.PackingView.as_view(), name="packing"),
    path("dashboard/fulfillment/<int:pk>/shipment/", views.ShipmentDetailView.as_view(), name="shipment_detail"),
    path("dashboard/fulfillment/<int:pk>/timeline/", views.ShipmentTimelineView.as_view(), name="timeline"),

    # Returns & Exchanges Queues
    path("dashboard/fulfillment/returns/", views.ReturnsListView.as_view(), name="returns"),
    path("dashboard/fulfillment/exchanges/", views.ExchangeRequestsView.as_view(), name="exchanges"),

    # Action Mutations
    path("dashboard/fulfillment/<int:pk>/assign/", views.assign_order_view, name="assign"),
    path("dashboard/fulfillment/<int:pk>/pick/start/", views.start_picking_view, name="start_picking"),
    path("dashboard/fulfillment/<int:pk>/pick/complete/", views.complete_picking_view, name="complete_picking"),
    path("dashboard/fulfillment/<int:pk>/pack/start/", views.start_packing_view, name="start_packing"),
    path("dashboard/fulfillment/<int:pk>/pack/complete/", views.complete_packing_view, name="complete_packing"),
    path("dashboard/fulfillment/<int:pk>/shipment/create/", views.create_shipment_view, name="create_shipment"),
    path("dashboard/fulfillment/<int:pk>/dispatch/", views.dispatch_order_view, name="dispatch_order"),
    path("dashboard/fulfillment/<int:pk>/deliver/", views.confirm_delivery_view, name="confirm_delivery"),
    path("dashboard/fulfillment/<int:pk>/return/initiate/", views.initiate_return_view, name="initiate_return"),
    path("dashboard/fulfillment/<int:pk>/cancel/", views.cancel_fulfillment_view, name="cancel_fulfillment"),
    path("dashboard/fulfillment/rma/<int:rma_pk>/process/", views.process_rma_view, name="process_rma"),
]
