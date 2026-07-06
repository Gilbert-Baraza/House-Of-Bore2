# products/services.py
"""
Service layer for catalog domain logic.
Encapsulates operations that modify database state or trigger side effects.
"""

from django.db.models import F
from products.models import Brand, Category, Product


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
