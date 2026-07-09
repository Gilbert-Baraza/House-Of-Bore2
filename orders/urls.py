# orders/urls.py
"""
orders/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for order creation (`/create/`) and customer order history
(`/account/orders/`).
Namespace: "orders"
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from orders import views

app_name = "orders"

urlpatterns = [
    path("orders/create/", views.OrderCreateView.as_view(), name="create"),
    path("account/orders/", views.OrderListView.as_view(), name="list"),
    path("account/orders/<str:order_number>/", views.OrderDetailView.as_view(), name="detail"),
]
