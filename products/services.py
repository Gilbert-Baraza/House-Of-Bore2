from decimal import Decimal
from typing import List, Optional, Any
from django.db import transaction
from django.db.models import F
from django.utils.text import slugify
from products.models import Brand, Category, Product, ProductVariant, ProductOptionValue, ProductVariantOption


def create_category(name: str, slug: str = "", parent: Category = None, **kwargs) -> Category:
    category = Category(name=name, slug=slug, parent=parent, **kwargs)
    category.save()
    return category


def create_brand(name: str, slug: str = "", **kwargs) -> Brand:
    brand = Brand(name=name, slug=slug, **kwargs)
    brand.save()
    return brand


def increment_product_views(product: Product) -> None:
    """
    Atomically increments the view count for a product in the database without race conditions,
    and updates the in-memory instance without clearing prefetched relations (such as images).
    """
    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
    product.view_count += 1



def mark_product_featured(product: Product, featured: bool = True) -> Product:
    """
    Updates the featured merchandising flag for a product cleanly.
    """
    product.is_featured = featured
    product.save(update_fields=["is_featured", "updated_at"])
    return product


def generate_sku(product: Product, option_values: Optional[List[ProductOptionValue]] = None) -> str:
    """
    Generate a human-readable, deterministic, and unique SKU.
    Format: HOB-<PRODUCT_CODE>-<OPT1>-<OPT2>
    Example: HOB-HOODIE-BLK-XL
    """
    # Derive product prefix (up to 10 chars uppercase letters/numbers)
    slug_parts = product.slug.upper().split("-")
    # Filter out short filler words if possible, or take first meaningful words
    meaningful = [p for p in slug_parts if p not in ("THE", "A", "AN", "OF", "AND", "IN", "ON")]
    prefix = "-".join(meaningful[:2])[:12] if meaningful else product.slug.upper()[:12]
    prefix = "".join(c for c in prefix if c.isalnum() or c == "-").strip("-")
    if not prefix:
        prefix = f"PRD{product.pk or '0'}"

    parts = ["HOB", prefix]

    if option_values:
        # Sort values by option sort order
        sorted_vals = sorted(option_values, key=lambda v: (getattr(v.option, "sort_order", 0), v.display_order, v.id))
        for val in sorted_vals:
            # Create a clean 3-4 char abbreviation of value (e.g. Black -> BLK, Large -> L, Medium -> M)
            v_str = val.value.upper()
            if v_str in ("SMALL", "S"):
                code = "S"
            elif v_str in ("MEDIUM", "M"):
                code = "M"
            elif v_str in ("LARGE", "L"):
                code = "L"
            elif v_str in ("EXTRA LARGE", "XL", "X-LARGE"):
                code = "XL"
            elif v_str in ("XXL", "2XL"):
                code = "XXL"
            elif v_str in ("BLACK", "BLK"):
                code = "BLK"
            elif v_str in ("WHITE", "WHT"):
                code = "WHT"
            else:
                clean_v = "".join(c for c in v_str if c.isalnum())
                code = clean_v[:4] if clean_v else "OPT"
            parts.append(code)

    base_sku = "-".join(parts)
    sku = base_sku
    counter = 1
    while ProductVariant.objects.filter(sku=sku).exists():
        sku = f"{base_sku}-{counter}"
        counter += 1
    return sku


@transaction.atomic
def create_variant(
    product: Product,
    sku: str = "",
    option_values: Optional[List[ProductOptionValue]] = None,
    **kwargs: Any
) -> ProductVariant:
    """
    Create a new ProductVariant for a given product and associate ordered option values.
    If sku is empty or not provided, automatically generates a unique SKU via generate_sku().
    """
    if not sku:
        sku = generate_sku(product, option_values)

    variant = ProductVariant(product=product, sku=sku, **kwargs)
    variant.save()

    if option_values:
        for idx, val in enumerate(option_values):
            ProductVariantOption.objects.create(
                variant=variant,
                option_value=val,
                sort_order=idx
            )
    return variant


@transaction.atomic
def update_variant(
    variant: ProductVariant,
    option_values: Optional[List[ProductOptionValue]] = None,
    **kwargs: Any
) -> ProductVariant:
    """
    Update attributes on an existing ProductVariant and optionally reassign its option value combination.
    """
    for attr, value in kwargs.items():
        setattr(variant, attr, value)
    variant.save()

    if option_values is not None:
        variant.variant_options.all().delete()
        for idx, val in enumerate(option_values):
            ProductVariantOption.objects.create(
                variant=variant,
                option_value=val,
                sort_order=idx
            )
    return variant


def variant_price(variant: ProductVariant) -> Decimal:
    """
    Return authoritative selling price of the variant via pricing engine priority.
    """
    return variant.get_price()


def variant_stock(variant: ProductVariant) -> int:
    """
    Return available inventory unit count for the variant.
    """
    return variant.stock_quantity


def variant_description(variant: ProductVariant) -> str:
    """
    Return human-readable option summary of the variant (e.g. 'Color: Black / Size: Large').
    """
    return variant.get_description()
