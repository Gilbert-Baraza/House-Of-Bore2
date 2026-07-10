# products/urls.py
"""
URL configuration for the public product catalog.

Routes:
    /products/                 → Product listing (sortable, paginated)
    /products/<slug>/          → Product detail page
    /categories/               → Category listing
    /category/<slug>/          → Category detail with product grid
    /brands/                   → Brand listing
    /brand/<slug>/             → Brand detail with product grid
"""

from django.urls import path
from products.views import (
    BrandDetailView,
    BrandListView,
    CategoryDetailView,
    CategoryListView,
    ComparisonMatrixView,
    ClearComparisonView,
    ProductDetailView,
    ProductListView,
    ToggleComparisonView,
)

app_name = "products"

urlpatterns = [
    # Comparison Routes (must precede slug route)
    path("products/compare/", ComparisonMatrixView.as_view(), name="comparison_matrix"),
    path("products/compare/toggle/<int:product_id>/", ToggleComparisonView.as_view(), name="toggle_comparison"),
    path("products/compare/clear/", ClearComparisonView.as_view(), name="clear_comparison"),

    # Products
    path("products/", ProductListView.as_view(), name="product_list"),
    path("products/<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),

    # Categories
    path("categories/", CategoryListView.as_view(), name="category_list"),
    path("category/<slug:slug>/", CategoryDetailView.as_view(), name="category_detail"),

    # Brands
    path("brands/", BrandListView.as_view(), name="brand_list"),
    path("brand/<slug:slug>/", BrandDetailView.as_view(), name="brand_detail"),
]
