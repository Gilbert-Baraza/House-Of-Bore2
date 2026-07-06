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

from django.db.models import Count, F, Prefetch, Q, QuerySet
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
    "price_asc": ("price", "name"),
    "price_desc": ("-price", "name"),
    "featured": ("-is_featured", "-created_at", "name"),
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


def get_low_stock_products() -> QuerySet[Product]:
    """
    Returns active products that are running low on inventory.
    Useful for administrative alerts and merchandising replenishment.
    """
    return Product.objects.active().filter(
        stock_quantity__lte=F("low_stock_threshold"),
        stock_quantity__gt=0
    ).select_related("category", "brand")
