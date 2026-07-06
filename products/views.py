# products/views.py
"""
Class-based views for the public product catalog.
Views are kept thin — all ORM logic is encapsulated in selectors.py.
"""

from django.http import Http404
from django.views.generic import DetailView, ListView

from products.models import Brand, Category, Product
from products.selectors import (
    DEFAULT_SORT,
    SORT_OPTIONS,
    get_active_products,
    get_brand_by_slug,
    get_brands_with_product_counts,
    get_categories_with_product_counts,
    get_category_by_slug,
    get_product_by_slug,
    get_products_by_brand,
    get_products_by_category,
    get_related_products,
)
from products.services import increment_product_views


# ─── Products ─────────────────────────────────────────────────────────────────

class ProductListView(ListView):
    """
    Displays a paginated, sortable grid of all active products.
    Supports server-side sorting via `?sort=price_asc` query parameter.
    """
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        sort = self.request.GET.get("sort", DEFAULT_SORT)
        return get_active_products(sort=sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_sort = self.request.GET.get("sort", DEFAULT_SORT)
        context["current_sort"] = current_sort
        context["sort_options"] = SORT_OPTIONS
        context["breadcrumbs"] = [
            {"label": "Home", "url": "/"},
            {"label": "Products", "url": None},
        ]
        return context


class ProductDetailView(DetailView):
    """
    Public product detail showcase.
    Retrieves product by slug with eager loading, increments view count atomically,
    and supplies related products and hierarchical breadcrumbs.
    """
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = "product"
    slug_url_kwarg = "slug"

    def get_object(self, queryset=None):
        try:
            return get_product_by_slug(self.kwargs["slug"])
        except Product.DoesNotExist:
            raise Http404("Product not found.")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        increment_product_views(self.object)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = context["product"]
        context["related_products"] = get_related_products(product, limit=4)
        
        breadcrumbs = [
            {"label": "Home", "url": "/"},
            {"label": "Products", "url": "/products/"},
        ]
        if product.category:
            ancestors = product.category.get_ancestors()
            for ancestor in ancestors:
                breadcrumbs.append({"label": ancestor.name, "url": f"/category/{ancestor.slug}/"})
            breadcrumbs.append({"label": product.category.name, "url": f"/category/{product.category.slug}/"})
        breadcrumbs.append({"label": product.name, "url": None})
        context["breadcrumbs"] = breadcrumbs
        return context




# ─── Categories ───────────────────────────────────────────────────────────────

class CategoryListView(ListView):
    """
    Displays the full category tree annotated with product counts.
    """
    model = Category
    template_name = "products/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return get_categories_with_product_counts()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"label": "Home", "url": "/"},
            {"label": "Categories", "url": None},
        ]
        return context


class CategoryDetailView(ListView):
    """
    Displays a single category with its products in a sortable, paginated grid.
    Also shows child subcategories for hierarchical navigation.
    """
    model = Product
    template_name = "products/category_detail.html"
    context_object_name = "products"
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        try:
            self.category = get_category_by_slug(self.kwargs["slug"])
        except Category.DoesNotExist:
            raise Http404("Category not found.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        sort = self.request.GET.get("sort", DEFAULT_SORT)
        return get_products_by_category(self.category, sort=sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category"] = self.category
        context["child_categories"] = self.category.children.filter(is_active=True).order_by("sort_order", "name")
        current_sort = self.request.GET.get("sort", DEFAULT_SORT)
        context["current_sort"] = current_sort
        context["sort_options"] = SORT_OPTIONS

        # Build breadcrumbs from root to current category
        breadcrumbs = [
            {"label": "Home", "url": "/"},
            {"label": "Categories", "url": "/categories/"},
        ]
        for ancestor in self.category.get_ancestors():
            breadcrumbs.append({"label": ancestor.name, "url": f"/category/{ancestor.slug}/"})
        breadcrumbs.append({"label": self.category.name, "url": None})
        context["breadcrumbs"] = breadcrumbs
        return context


# ─── Brands ───────────────────────────────────────────────────────────────────

class BrandListView(ListView):
    """
    Displays all active brands annotated with product counts.
    """
    model = Brand
    template_name = "products/brand_list.html"
    context_object_name = "brands"

    def get_queryset(self):
        return get_brands_with_product_counts()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = [
            {"label": "Home", "url": "/"},
            {"label": "Brands", "url": None},
        ]
        return context


class BrandDetailView(ListView):
    """
    Displays a single brand with its products in a sortable, paginated grid.
    """
    model = Product
    template_name = "products/brand_detail.html"
    context_object_name = "products"
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        try:
            self.brand = get_brand_by_slug(self.kwargs["slug"])
        except Brand.DoesNotExist:
            raise Http404("Brand not found.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        sort = self.request.GET.get("sort", DEFAULT_SORT)
        return get_products_by_brand(self.brand, sort=sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["brand"] = self.brand
        current_sort = self.request.GET.get("sort", DEFAULT_SORT)
        context["current_sort"] = current_sort
        context["sort_options"] = SORT_OPTIONS
        context["breadcrumbs"] = [
            {"label": "Home", "url": "/"},
            {"label": "Brands", "url": "/brands/"},
            {"label": self.brand.name, "url": None},
        ]
        return context
