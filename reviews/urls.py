# reviews/urls.py
"""
reviews/urls.py
──────────────────────────────────────────────────────────────────────────────
URL configuration for product reviews and ratings.

Routes:
    /reviews/product/<slug>/add/    → Create a review for a product
    /reviews/review/<pk>/edit/      → Edit an existing review
    /reviews/review/<pk>/delete/    → Delete an existing review
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path

from reviews.views import CreateReviewView, DeleteReviewView, UpdateReviewView

app_name = "reviews"

urlpatterns = [
    path(
        "product/<slug:product_slug>/add/",
        CreateReviewView.as_view(),
        name="create_review",
    ),
    path(
        "review/<int:pk>/edit/",
        UpdateReviewView.as_view(),
        name="update_review",
    ),
    path(
        "review/<int:pk>/delete/",
        DeleteReviewView.as_view(),
        name="delete_review",
    ),
]
