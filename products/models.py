# products/models.py
"""
Catalog foundation models: Category, Brand, Product, and ProductImage.
Designed for high scalability, clean merchandising control, and robust business rule enforcement.
"""

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """
    Hierarchical catalog category model.
    Supports nested subcategories via a self-referencing ForeignKey.
    """
    name = models.CharField(
        max_length=100,
        help_text="Display name of the category (e.g., Men's Collection)."
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        help_text="Unique URL identifier generated from the name."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional editorial description for category header."
    )
    image = models.ImageField(
        upload_to="categories/",
        null=True,
        blank=True,
        help_text="Optional category promotional banner or thumbnail."
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Parent category for hierarchical nesting. Leave blank for root categories."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Designates whether this category is visible in the store catalog."
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "category"
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        if self.parent:
            return f"{self.parent} > {self.name}"
        return self.name

    def clean(self) -> None:
        """
        Validates model data, specifically preventing circular category hierarchies.
        """
        super().clean()
        if self.parent:
            if self.parent == self or (self.pk and self.parent.pk == self.pk):
                raise ValidationError({"parent": "A category cannot be its own parent."})

            parent_node = self.parent
            while parent_node is not None:
                if parent_node == self or (self.pk and parent_node.pk == self.pk):
                    raise ValidationError({
                        "parent": "A category cannot be its own ancestor (circular relationship detected)."
                    })
                parent_node = parent_node.parent

    def save(self, *args, **kwargs) -> None:
        """
        Auto-generates unique slug if not provided and enforces circular reference checks.
        """
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        self.clean()
        super().save(*args, **kwargs)

    def get_ancestors(self) -> list["Category"]:
        """
        Returns an ordered list of ancestor categories from root down to immediate parent.
        """
        ancestors = []
        parent_node = self.parent
        while parent_node is not None:
            if parent_node in ancestors:
                break
            ancestors.insert(0, parent_node)
            parent_node = parent_node.parent
        return ancestors

    def get_descendants(self, include_self: bool = False) -> list["Category"]:
        """
        Returns a flat list of all active descendant subcategories.
        """
        descendants = []
        if include_self:
            descendants.append(self)
        for child in self.children.filter(is_active=True).order_by("sort_order", "name"):
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants


class Brand(models.Model):
    """
    Independent brand house or manufacturer model.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Brand or manufacturer name."
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        help_text="Unique URL identifier for brand showcases."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Editorial brand story or heritage overview."
    )
    logo = models.ImageField(
        upload_to="brands/",
        null=True,
        blank=True,
        help_text="Brand logo or crest image."
    )
    website = models.URLField(
        blank=True,
        default="",
        help_text="Optional official brand website URL."
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Designates whether this brand is highlighted on the homepage or showcases."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Designates whether this brand is active and visible in the store."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "brand"
        verbose_name_plural = "brands"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    """
    Custom QuerySet for Product model providing domain-specific filters.
    """

    def active(self) -> "ProductQuerySet":
        return self.filter(is_active=True)

    def featured(self) -> "ProductQuerySet":
        return self.filter(is_active=True, is_featured=True)

    def new_arrivals(self) -> "ProductQuerySet":
        return self.filter(is_active=True, is_new_arrival=True)

    def in_stock(self) -> "ProductQuerySet":
        return self.filter(is_active=True, stock_quantity__gt=0)

    def on_sale(self) -> "ProductQuerySet":
        return self.filter(
            is_active=True,
            compare_at_price__isnull=False,
            compare_at_price__gt=models.F("price")
        )


class Product(models.Model):
    """
    Core Product catalog model.
    Represents an individual sellable item or garment in the House of Bore catalog.
    """
    # Basic Information
    name = models.CharField(
        max_length=200,
        help_text="Product title (e.g., The Weatherproof Trench Coat)."
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        help_text="Unique URL slug generated from product name."
    )
    short_description = models.CharField(
        max_length=300,
        help_text="Concise summary for product cards and previews."
    )
    description = models.TextField(
        help_text="Full detailed description of materials, fit, and craftsmanship."
    )

    # Relationships
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        help_text="Primary collection or category."
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
        help_text="Associated brand house or atelier."
    )

    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Current selling price."
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original retail price before discount (optional)."
    )

    # Inventory
    stock_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Current available inventory units."
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Threshold quantity triggering low stock alerts."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Designates whether this product is published and visible in the store."
    )

    # Merchandising
    is_featured = models.BooleanField(
        default=False,
        help_text="Highlight on homepage and curated showcases."
    )
    is_new_arrival = models.BooleanField(
        default=False,
        help_text="Highlight in new season arrivals."
    )

    # SEO
    meta_title = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Custom SEO title (defaults to product name if empty)."
    )
    meta_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom SEO description (defaults to short description if empty)."
    )

    # Statistics
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of times this product page has been viewed."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "name"]
        verbose_name = "product"
        verbose_name_plural = "products"
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["is_active", "price"]),
            models.Index(fields=["is_active", "is_featured"]),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """
        Validates business rules for pricing and inventory.
        """
        super().clean()
        if self.price is not None and self.price < Decimal("0.00"):
            raise ValidationError({"price": "Selling price cannot be negative."})

        if self.compare_at_price is not None:
            if self.compare_at_price < Decimal("0.00"):
                raise ValidationError({"compare_at_price": "Compare at price cannot be negative."})
            if self.price is not None and self.compare_at_price <= self.price:
                raise ValidationError({
                    "compare_at_price": "Compare at price must be strictly greater than the selling price."
                })

    def save(self, *args, **kwargs) -> None:
        """
        Auto-generates unique slug, populates SEO defaults, and enforces validation.
        """
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if not self.meta_title:
            self.meta_title = self.name[:150]
        if not self.meta_description:
            self.meta_description = self.short_description[:255]

        self.clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        """
        Returns the canonical URL for this product's detail page.
        """
        from django.urls import reverse
        return reverse("products:product_detail", kwargs={"slug": self.slug})

    def get_primary_image(self) -> "ProductImage | None":
        """
        Returns the primary image for this product, or the first available image if none marked primary.
        """
        primary = self.images.filter(is_primary=True).first()
        if primary:
            return primary
        return self.images.order_by("sort_order", "id").first()

    def is_available(self) -> bool:
        """
        Returns True if the product is published and currently in stock.
        """
        return self.is_active and self.stock_quantity > 0

    def in_stock(self) -> bool:
        """
        Returns True if stock quantity is greater than zero.
        """
        return self.stock_quantity > 0

    def low_stock(self) -> bool:
        """
        Returns True if stock is positive but at or below the low stock threshold.
        """
        return 0 < self.stock_quantity <= self.low_stock_threshold

    def is_on_sale(self) -> bool:
        """
        Returns True if compare_at_price is set and strictly greater than selling price.
        """
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    def discount_percentage(self) -> int:
        """
        Calculates the integer percentage discount if on sale.
        """
        if not self.is_on_sale():
            return 0
        discount = ((self.compare_at_price - self.price) / self.compare_at_price) * Decimal("100")
        return int(round(discount))


class ProductImage(models.Model):
    """
    Product image gallery model.
    One product may have multiple images, with exactly one marked as primary.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        help_text="Associated product."
    )
    image = models.ImageField(
        upload_to="products/",
        help_text="High-resolution garment or product image."
    )
    alt_text = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Accessible alternative text describing the image."
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Designates this image as the primary thumbnail across showcases."
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Gallery display order (lower numbers appear first)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "product image"
        verbose_name_plural = "product images"

    def __str__(self) -> str:
        return f"Image for {self.product.name} (Primary: {self.is_primary})"

    def save(self, *args, **kwargs) -> None:
        """
        Enforces that exactly one image per product is marked as primary.
        If this image is marked primary, unsets primary flag on all other images for this product.
        If this is the first image added to a product, automatically marks it primary.
        """
        if not self.pk and not ProductImage.objects.filter(product=self.product).exists():
            self.is_primary = True

        super().save(*args, **kwargs)

        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)


# ─── Cache Invalidation Signals ──────────────────────────────────────────────
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Brand)
def invalidate_catalog_cache(sender, **kwargs) -> None:
    """
    Automatically clears cached catalog filter options when any Product,
    Category, or Brand is created, updated, or deleted.
    """
    cache.delete("catalog_filter_options")

