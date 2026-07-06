# products/views.py
"""
Class-based views for the public product catalog.
Views are kept thin — all ORM logic is encapsulated in selectors.py.
"""

from django.core.paginator import Paginator
from django.http import Http404
from django.views.generic import DetailView, ListView

from core.templatetags.query_helpers import is_truthy
from products.models import Brand, Category, Product
from reviews.forms import ReviewForm
from reviews.selectors import get_product_reviews, get_review_summary, get_user_review
from products.selectors import (
    DEFAULT_SORT,
    SORT_OPTIONS,
    filter_products,
    get_active_products,
    get_brand_by_slug,
    get_brands_with_product_counts,
    get_categories_with_product_counts,
    get_category_by_slug,
    get_filter_options,
    get_product_by_slug,
    get_products_by_brand,
    get_products_by_category,
    get_related_products,
    search_products,
    sort_products,
)
from products.services import increment_product_views


# ─── Products ─────────────────────────────────────────────────────────────────

class ProductListView(ListView):
    """
    Displays a paginated, sortable, and searchable grid of active products
    with support for hierarchical category and brand filtering, price ranges, and promotional toggles.
    """
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = get_active_products(sort=DEFAULT_SORT)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = search_products(query, queryset=qs)
        qs = filter_products(
            queryset=qs,
            category_slug=self.request.GET.get("category"),
            brand_slug=self.request.GET.get("brand"),
            min_price=self.request.GET.get("min_price"),
            max_price=self.request.GET.get("max_price"),
            availability=self.request.GET.get("availability"),
            featured=self.request.GET.get("featured"),
            new=self.request.GET.get("new"),
            sale=self.request.GET.get("sale"),
        )
        sort_key = self.request.GET.get("sort", DEFAULT_SORT)
        qs = sort_products(queryset=qs, sort_key=sort_key)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Current filter and search values
        current_q = self.request.GET.get("q", "").strip()
        current_category = self.request.GET.get("category", "").strip()
        current_brand = self.request.GET.get("brand", "").strip()
        current_min_price = self.request.GET.get("min_price", "").strip()
        current_max_price = self.request.GET.get("max_price", "").strip()
        current_availability = self.request.GET.get("availability", "").strip()
        current_featured = self.request.GET.get("featured", "").strip()
        current_new = self.request.GET.get("new", "").strip()
        current_sale = self.request.GET.get("sale", "").strip()
        current_sort = self.request.GET.get("sort", DEFAULT_SORT)

        # Count active filters (excluding sort and page)
        active_filters = 0
        if current_q:
            active_filters += 1
        if current_category:
            active_filters += 1
        if current_brand:
            active_filters += 1
        if current_min_price or current_max_price:
            active_filters += 1
        if current_availability:
            active_filters += 1
        if is_truthy(current_featured):
            active_filters += 1
        if is_truthy(current_new):
            active_filters += 1
        if is_truthy(current_sale):
            active_filters += 1

        context.update({
            "current_q": current_q,
            "current_category": current_category,
            "current_brand": current_brand,
            "current_min_price": current_min_price,
            "current_max_price": current_max_price,
            "current_availability": current_availability,
            "current_featured": current_featured,
            "current_new": current_new,
            "current_sale": current_sale,
            "current_sort": current_sort,
            "sort_options": SORT_OPTIONS,
            "filter_options": get_filter_options(),
            "active_filter_count": active_filters,
            "is_filtered": active_filters > 0,
        })

        # Dynamic SEO Strategy
        page_title = "Shop All Products"
        meta_description = "Browse the full House of Bore catalog. Premium clothing, footwear, and accessories crafted from the finest European materials."
        
        if current_q:
            page_title = f"Search results for '{current_q}'"
            meta_description = f"Browse House of Bore catalog search results for '{current_q}'. Premium menswear, womenswear, and accessories."
        elif current_category:
            try:
                cat = get_category_by_slug(current_category)
                page_title = cat.name
                meta_description = cat.description or f"Shop the {cat.name} collection at House of Bore."
            except Category.DoesNotExist:
                pass
        elif current_brand:
            try:
                brand = get_brand_by_slug(current_brand)
                page_title = brand.name
                meta_description = brand.description or f"Shop {brand.name} premium products at House of Bore."
            except Brand.DoesNotExist:
                pass
        elif is_truthy(current_sale):
            page_title = "Products on Sale"
            meta_description = "Explore premium House of Bore garments and accessories currently on sale."
        elif is_truthy(current_new):
            page_title = "New Arrivals"
            meta_description = "Discover the latest additions to the permanent House of Bore collection."
        elif is_truthy(current_featured):
            page_title = "Featured Collection"
            meta_description = "Explore our curated selection of featured garments and artifacts."

        context["page_title"] = page_title
        context["meta_description"] = meta_description

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
        
        # Reviews & Ratings
        review_summary = get_review_summary(product)
        context["review_summary"] = review_summary

        reviews_qs = get_product_reviews(product, approved_only=True)
        paginator = Paginator(reviews_qs, 5)  # 5 reviews per page
        page_number = self.request.GET.get("review_page", 1)
        page_obj = paginator.get_page(page_number)
        context["reviews_page"] = page_obj
        context["reviews"] = page_obj.object_list

        user_review = get_user_review(product, self.request.user)
        context["user_review"] = user_review
        if self.request.user.is_authenticated and not user_review:
            context["review_form"] = ReviewForm()
        else:
            context["review_form"] = None

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
