# cart/urls.py
"""
cart/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for the shopping cart application.
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from cart import views

app_name = "cart"

urlpatterns = [
    path("", views.CartDetailView.as_view(), name="cart_detail"),
    path("add/<int:product_id>/", views.AddToCartView.as_view(), name="add"),
    path("update/<int:item_id>/", views.UpdateCartItemView.as_view(), name="update"),
    path("remove/<int:item_id>/", views.RemoveCartItemView.as_view(), name="remove"),
    path("clear/", views.ClearCartView.as_view(), name="clear"),
]
