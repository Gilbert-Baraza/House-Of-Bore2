# wishlist/urls.py
"""
wishlist/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for the Wishlist application.
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from wishlist import views

app_name = "wishlist"

urlpatterns = [
    path("", views.WishlistView.as_view(), name="wishlist"),
    path("add/<int:product_id>/", views.AddToWishlistView.as_view(), name="add"),
    path("remove/<int:product_id>/", views.RemoveFromWishlistView.as_view(), name="remove"),
    path("clear/", views.ClearWishlistView.as_view(), name="clear"),
]
