# products/selectors.py
"""
Query utilities and database selectors for the products app.
Encapsulates ORM logic to keep views clean and avoid N+1 query performance bottlenecks.

Performance notes:
  - select_related("category", "brand") joins Category and Brand in a single SQL query
    instead of issuing a separate query per product row (eliminates N+1 on FK lookups).
  - prefetch_related("images") issues a second query to batch-load all ProductImage rows,
    which is cheaper than N lazy loads when rendering product cards with thumbnails.
"""

from decimal import Decimal, InvalidOperation
from django.core.cache import cache
from django.db.models import Count, F, Prefetch, Q, QuerySet
from core.templatetags.query_helpers import is_truthy
from products.models import Brand, Category, Product, ProductImage


# ─── Category Selectors ──────────────────────────────────────────────────────
def get_active_categories() -> QuerySet[Category]:
    """Returns all active categories ordered by sort_order then name."""
    return Category.objects.filter(is_active=True).order_by("sort_order", "name")


def get_root_categories() -> QuerySet[Category]:
    """Returns only top-level (root) active categories."""
    return Category.objects.filter(parent__isnull=True, is_active=True).order_by("sort_order", "name")


def get_category_tree() -> QuerySet[Category]:
    """
    Returns root categories with their active children prefetched in two queries total.
    Used for navigation and the category list page.
    """
    active_children = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    return Category.objects.filter(parent__isnull=True, is_active=True).prefetch_related(
        Prefetch("children", queryset=active_children)
    ).order_by("sort_order", "name")


def get_category_by_slug(slug: str) -> Category:
    """Returns a single active category by slug, or raises Category.DoesNotExist."""
    return Category.objects.get(slug=slug, is_active=True)


def get_categories_with_product_counts() -> QuerySet[Category]:
    """
    Returns root categories annotated with their active product count.
    Uses a single annotated query — no N+1 for counting products per category.
    """
    active_children = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    return Category.objects.filter(
        parent__isnull=True, is_active=True
    ).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).prefetch_related(
        Prefetch("children", queryset=active_children)
    ).order_by("sort_order", "name")


# ─── Brand Selectors ─────────────────────────────────────────────────────────
def get_active_brands() -> QuerySet[Brand]:
    """Returns all active brands ordered alphabetically."""
    return Brand.objects.filter(is_active=True).order_by("name")


def get_featured_brands() -> QuerySet[Brand]:
    """Returns only featured, active brands."""
    return Brand.objects.filter(is_active=True, is_featured=True).order_by("name")


def get_brand_by_slug(slug: str) -> Brand:
    """Returns a single active brand by slug, or raises Brand.DoesNotExist."""
    return Brand.objects.get(slug=slug, is_active=True)


def get_brands_with_product_counts() -> QuerySet[Brand]:
    """
    Returns active brands annotated with their active product count.
    Single annotated query eliminates the need for per-brand count queries.
    """
    return Brand.objects.filter(is_active=True).annotate(
        product_count=Count("products", filter=Q(products__is_active=True))
    ).order_by("name")


# ─── Product Selectors ───────────────────────────────────────────────────────

# Mapping of user-facing sort keys to ORM order_by arguments.
# Centralised here so views and tests reference the same source of truth.
SORT_OPTIONS = {
    "newest": ("-created_at", "name"),
    "oldest": ("created_at", "name"),
    "price_asc": ("price", "name"),
    "price_desc": ("-price", "name"),
    "name_asc": ("name",),
    "name_desc": ("-name",),
    "featured": ("-is_featured", "-created_at", "name"),
    "popular": ("-view_count", "-created_at", "name"),
}
DEFAULT_SORT = "newest"


def _base_product_qs() -> QuerySet[Product]:
    """
    Shared base queryset for all product selectors.
    Applies select_related and prefetch_related once to avoid duplication.
    """
    primary_images = ProductImage.objects.filter(is_primary=True)
    return (
        Product.objects.active()
        .select_related("category", "brand")
        .prefetch_related(Prefetch("images", queryset=primary_images, to_attr="primary_images"))
    )


def apply_sorting(qs: QuerySet[Product], sort_key: str) -> QuerySet[Product]:
    """
    Applies a sort ordering to a product queryset based on a user-supplied key.
    Falls back to DEFAULT_SORT if the key is unrecognised.
    """
    ordering = SORT_OPTIONS.get(sort_key, SORT_OPTIONS[DEFAULT_SORT])
    return qs.order_by(*ordering)


def get_active_products(sort: str = DEFAULT_SORT) -> QuerySet[Product]:
    """Returns all published products with optimised eager loading and sorting."""
    return apply_sorting(_base_product_qs(), sort)


def get_featured_products() -> QuerySet[Product]:
    """Returns featured products for homepage and lookbook showcases."""
    return _base_product_qs().filter(is_featured=True).order_by("-created_at", "name")


def get_new_arrivals() -> QuerySet[Product]:
    """Returns products flagged as new season arrivals."""
    return _base_product_qs().filter(is_new_arrival=True).order_by("-created_at", "name")


def get_latest_products(limit: int = 8) -> QuerySet[Product]:
    """Returns the N most recently created active products."""
    return _base_product_qs().order_by("-created_at")[:limit]


def get_products_by_category(category: Category, sort: str = DEFAULT_SORT) -> QuerySet[Product]:
    """
    Returns active products belonging to a specific category *and* all its active descendants.
    Supports hierarchical browsing — selecting "Men's Clothing" also shows "Tailored Suiting" items.
    """
    categories = category.get_descendants(include_self=True)
    return apply_sorting(_base_product_qs().filter(category__in=categories), sort)


def get_products_by_brand(brand: Brand, sort: str = DEFAULT_SORT) -> QuerySet[Product]:
    """Returns active products crafted by a specific brand atelier."""
    return apply_sorting(_base_product_qs().filter(brand=brand), sort)


def get_product_by_slug(slug: str) -> Product:
    """
    Returns a single active product by slug with category, brand, and all images prefetched.
    Raises Product.DoesNotExist if not found.
    """
    return (
        Product.objects.active()
        .select_related("category", "brand")
        .prefetch_related("images")
        .get(slug=slug)
    )


def get_related_products(product: Product, limit: int = 4) -> QuerySet[Product]:
    """
    Returns active products belonging to the same category or its descendants,
    excluding the given product itself. Sliced to the specified limit and ordered
    by featured merchandising status and creation date.
    """
    if not product.category_id:
        return Product.objects.none()
    categories = product.category.get_descendants(include_self=True)
    return (
        _base_product_qs()
        .filter(category__in=categories)
        .exclude(pk=product.pk)
        .order_by("-is_featured", "-created_at")[:limit]
    )


def get_low_stock_products() -> QuerySet[Product]:
    """
    Returns active products that are running low on inventory.
    Useful for administrative alerts and merchandising replenishment.
    """
    return Product.objects.active().filter(
        stock_quantity__lte=F("low_stock_threshold"),
        stock_quantity__gt=0
    ).select_related("category", "brand")


# ─── Search, Filtering & Discovery Selectors ──────────────────────────────────

def search_products(query: str | None, queryset: QuerySet[Product] | None = None) -> QuerySet[Product]:
    """
    Performs case-insensitive partial matching across product name, short description,
    and full description. Gracefully returns the unfiltered queryset if query is empty.
    """
    if queryset is None:
        queryset = _base_product_qs()
    if not query:
        return queryset
    query_str = str(query).strip()
    if not query_str:
        return queryset
    return queryset.filter(
        Q(name__icontains=query_str)
        | Q(short_description__icontains=query_str)
        | Q(description__icontains=query_str)
    ).distinct()


def filter_products(
    queryset: QuerySet[Product] | None = None,
    category_slug: str | None = None,
    brand_slug: str | None = None,
    min_price: str | Decimal | float | int | None = None,
    max_price: str | Decimal | float | int | None = None,
    availability: str | None = None,
    featured: bool | str | None = None,
    new: bool | str | None = None,
    sale: bool | str | None = None,
) -> QuerySet[Product]:
    """
    Applies server-side domain filters to a product queryset.
    Handles category hierarchy, brands, price bounds, availability, and promotional toggles.
    """
    if queryset is None:
        queryset = _base_product_qs()

    # Category filter (includes hierarchical descendants)
    if category_slug:
        try:
            cat = Category.objects.get(slug=str(category_slug).strip(), is_active=True)
            categories = cat.get_descendants(include_self=True)
            queryset = queryset.filter(category__in=categories)
        except Category.DoesNotExist:
            return Product.objects.none()

    # Brand filter
    if brand_slug:
        try:
            brand = Brand.objects.get(slug=str(brand_slug).strip(), is_active=True)
            queryset = queryset.filter(brand=brand)
        except Brand.DoesNotExist:
            return Product.objects.none()

    # Price range filters
    if min_price is not None and str(min_price).strip() != "":
        try:
            min_val = Decimal(str(min_price).strip())
            if min_val >= 0:
                queryset = queryset.filter(price__gte=min_val)
        except (ValueError, TypeError, InvalidOperation):
            pass

    if max_price is not None and str(max_price).strip() != "":
        try:
            max_val = Decimal(str(max_price).strip())
            if max_val >= 0:
                queryset = queryset.filter(price__lte=max_val)
        except (ValueError, TypeError, InvalidOperation):
            pass

    # Availability filter
    if availability:
        avail_str = str(availability).strip().lower()
        if avail_str == "in-stock":
            queryset = queryset.filter(stock_quantity__gt=0)
        elif avail_str == "out-of-stock":
            queryset = queryset.filter(stock_quantity=0)

    # Merchandising toggles
    if is_truthy(featured):
        queryset = queryset.filter(is_featured=True)

    if is_truthy(new):
        queryset = queryset.filter(is_new_arrival=True)

    if is_truthy(sale):
        queryset = queryset.filter(
            compare_at_price__isnull=False,
            compare_at_price__gt=F("price")
        )

    return queryset


def sort_products(queryset: QuerySet[Product] | None = None, sort_key: str = DEFAULT_SORT) -> QuerySet[Product]:
    """
    Applies sorting to a product queryset.
    """
    if queryset is None:
        queryset = _base_product_qs()
    return apply_sorting(queryset, sort_key)


def get_filter_options() -> dict:
    """
    Returns available filter options (categories, brands) annotated with active product counts
    for rendering in the filter sidebar. Cached for 15 minutes to avoid redundant aggregation queries.
    """
    options = cache.get("catalog_filter_options")
    if options is None:
        options = {
            "categories": get_categories_with_product_counts(),
            "brands": get_brands_with_product_counts(),
        }
        cache.set("catalog_filter_options", options, 900)  # 15 minutes TTL
    return options


