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
        Utilizes prefetched images cache if available to prevent N+1 database queries.
        """
        # If prefetched, run the filter in Python memory to avoid querying the DB
        if hasattr(self, "_prefetched_objects_cache") and "images" in self._prefetched_objects_cache:
            images = list(self.images.all())
            primary = next((img for img in images if img.is_primary), None)
            if primary:
                return primary
            if images:
                return sorted(images, key=lambda img: (img.sort_order, img.id))[0]
            return None

        # Fallback to DB query if not prefetched
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

    def get_price_range(self) -> tuple[Decimal, Decimal]:
        """
        Returns (min_price, max_price) across active variants or product base price.
        """
        if hasattr(self, "_prefetched_objects_cache") and "variants" in self._prefetched_objects_cache:
            active_vars = [v for v in self.variants.all() if v.is_active]
        else:
            active_vars = list(self.variants.filter(is_active=True))
        if active_vars:
            prices = [v.get_price() for v in active_vars]
            return min(prices), max(prices)
        return self.price, self.price

    def has_multiple_prices(self) -> bool:
        """
        Returns True if product has variants with differing selling prices.
        """
        min_p, max_p = self.get_price_range()
        return min_p < max_p

    def get_starting_price(self) -> Decimal:
        """
        Returns the lowest selling price among active variants or base product price.
        """
        min_p, _ = self.get_price_range()
        return min_p


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


class ProductOption(models.Model):
    """
    Normalized option group attribute for variants (e.g., Color, Size, Material).
    Can be shared across products or tailored.
    """
    name = models.CharField(
        max_length=100,
        help_text="Internal option name (e.g., Color, Size, Material)."
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Customer-facing label on product pages (e.g., Color, Size)."
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display priority (lower numbers appear first)."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Designates whether this option group is active and selectable."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "product option"
        verbose_name_plural = "product options"

    def __str__(self) -> str:
        return self.display_name or self.name


class ProductOptionValue(models.Model):
    """
    Individual value within a ProductOption group (e.g., Black, White for Color; S, M, L for Size).
    """
    option = models.ForeignKey(
        ProductOption,
        on_delete=models.CASCADE,
        related_name="values",
        help_text="Parent option group."
    )
    value = models.CharField(
        max_length=100,
        help_text="Specific option value (e.g., Black, Medium)."
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Sorting order within the option group."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["option__sort_order", "display_order", "id"]
        verbose_name = "product option value"
        verbose_name_plural = "product option values"
        constraints = [
            models.UniqueConstraint(fields=["option", "value"], name="unique_option_value")
        ]

    def __str__(self) -> str:
        return f"{self.option.name}: {self.value}"


class ProductVariant(models.Model):
    """
    Purchasable variant of a Product consisting of specific ProductOptionValues.
    Enforces distinct SKU, independent stock level, optional pricing overrides, and images.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        help_text="Associated parent catalog product."
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique, human-readable Stock Keeping Unit (e.g., HOB-TSHIRT-BLK-L)."
    )
    barcode = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Optional barcode, UPC, or EAN number."
    )
    price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional selling price specifically for this variant (overrides product base price)."
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional original retail price before discount for this variant."
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional internal wholesale or manufacturing cost."
    )
    stock_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Available inventory units specifically for this variant."
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Threshold quantity triggering low stock alerts."
    )
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Shipping weight in kg or lbs."
    )
    dimensions = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Package dimensions (e.g., 20x15x5 cm)."
    )
    image = models.ImageField(
        upload_to="variants/",
        null=True,
        blank=True,
        help_text="Optional variant-specific image (falls back to product primary image if empty)."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Designates whether this variant is active and purchasable in the store."
    )
    option_values = models.ManyToManyField(
        ProductOptionValue,
        through="ProductVariantOption",
        related_name="variants",
        help_text="Associated option values defining this exact combination."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "sku"]
        verbose_name = "product variant"
        verbose_name_plural = "product variants"
        indexes = [
            models.Index(fields=["is_active", "stock_quantity"]),
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["product", "is_active", "stock_quantity"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} ({self.get_options_summary()})"

    def clean(self) -> None:
        """
        Validate pricing override rules and SKU uniqueness across variants.
        """
        super().clean()
        if self.sku:
            if ProductVariant.objects.filter(sku=self.sku).exclude(pk=self.pk).exists():
                raise ValidationError({"sku": f"SKU '{self.sku}' already exists on another ProductVariant."})
        if self.price_override is not None and self.price_override < Decimal("0.00"):
            raise ValidationError({"price_override": "Variant price override cannot be negative."})
        if self.compare_at_price is not None:
            if self.compare_at_price < Decimal("0.00"):
                raise ValidationError({"compare_at_price": "Compare at price cannot be negative."})
            if self.price_override is not None and self.compare_at_price <= self.price_override:
                raise ValidationError({
                    "compare_at_price": "Compare at price must be strictly greater than the price override."
                })

    def save(self, *args, **kwargs) -> None:
        """
        Enforces validation and saves the variant. SKU generation is handled via service layer if blank.
        """
        self.clean()
        super().save(*args, **kwargs)

    def get_price(self) -> Decimal:
        """
        Returns authoritative selling price: price override if set, otherwise product base price.
        """
        if self.price_override is not None:
            return self.price_override
        return self.product.price

    def get_compare_at_price(self) -> Decimal | None:
        """
        Returns authoritative compare-at price: compare_at_price if set on variant, otherwise product compare_at_price.
        """
        if self.compare_at_price is not None:
            return self.compare_at_price
        return self.product.compare_at_price

    def is_on_sale(self) -> bool:
        """
        Returns True if variant has a compare-at price strictly higher than its selling price.
        """
        cmp = self.get_compare_at_price()
        price = self.get_price()
        return bool(cmp is not None and cmp > price)

    def discount_percentage(self) -> int:
        """
        Calculates the integer percentage discount for this variant if on sale.
        """
        if not self.is_on_sale():
            return 0
        cmp = self.get_compare_at_price()
        price = self.get_price()
        if not cmp or cmp <= Decimal("0.00"):
            return 0
        discount = ((cmp - price) / cmp) * Decimal("100")
        return int(round(discount))

    def in_stock(self) -> bool:
        """
        Returns True if variant stock quantity is greater than zero.
        """
        return self.stock_quantity > 0

    def low_stock(self) -> bool:
        """
        Returns True if variant is in stock but at or below low stock threshold.
        """
        return 0 < self.stock_quantity <= self.low_stock_threshold

    def is_available(self) -> bool:
        """
        Returns True if variant is active, product is active, and stock > 0.
        """
        return self.is_active and self.stock_quantity > 0 and self.product.is_active

    def get_image_url(self) -> str:
        """
        Returns URL of variant-specific image if present, otherwise falls back to product primary image URL.
        """
        if self.image and hasattr(self.image, "url"):
            return self.image.url
        primary = self.product.get_primary_image()
        if primary and primary.image and hasattr(primary.image, "url"):
            return primary.image.url
        return ""

    def get_description(self) -> str:
        """
        Returns human-readable option combination string (e.g., 'Color: Black / Size: Large').
        Utilizes prefetched option_values cache if available.
        """
        if hasattr(self, "_prefetched_objects_cache") and "option_values" in self._prefetched_objects_cache:
            vals = sorted(self.option_values.all(), key=lambda v: (getattr(v.option, "sort_order", 0), v.display_order, v.id))
        else:
            vals = self.option_values.select_related("option").order_by("option__sort_order", "display_order", "id")
        parts = [f"{v.option.display_name or v.option.name}: {v.value}" for v in vals]
        return " / ".join(parts) if parts else self.sku

    def get_options_summary(self) -> str:
        """
        Returns concise value combination (e.g., 'Black / Large').
        """
        if hasattr(self, "_prefetched_objects_cache") and "option_values" in self._prefetched_objects_cache:
            vals = sorted(self.option_values.all(), key=lambda v: (getattr(v.option, "sort_order", 0), v.display_order, v.id))
        else:
            vals = self.option_values.order_by("option__sort_order", "display_order", "id")
        parts = [v.value for v in vals]
        return " / ".join(parts) if parts else self.sku


class ProductVariantOption(models.Model):
    """
    Explicit junction model connecting ProductVariant to ProductOptionValue while preserving display order.
    """
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="variant_options",
        help_text="Parent product variant."
    )
    option_value = models.ForeignKey(
        ProductOptionValue,
        on_delete=models.RESTRICT,
        related_name="variant_options",
        help_text="Assigned option value."
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Ordering priority for this option within the variant."
    )

    class Meta:
        ordering = ["sort_order", "option_value__option__sort_order", "id"]
        verbose_name = "variant option"
        verbose_name_plural = "variant options"
        constraints = [
            models.UniqueConstraint(fields=["variant", "option_value"], name="unique_variant_option_value")
        ]

    def __str__(self) -> str:
        return f"{self.variant.sku} -> {self.option_value.value}"


# ─── Cache Invalidation Signals ──────────────────────────────────────────────
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Category)
@receiver([post_save, post_delete], sender=Brand)
@receiver([post_save, post_delete], sender=ProductVariant)
@receiver([post_save, post_delete], sender=ProductOption)
@receiver([post_save, post_delete], sender=ProductOptionValue)
def invalidate_catalog_cache(sender, **kwargs) -> None:
    """
    Automatically clears cached catalog filter options when any Product,
    Category, Brand, Variant, or Option is created, updated, or deleted.
    """
    cache.delete("catalog_filter_options")

