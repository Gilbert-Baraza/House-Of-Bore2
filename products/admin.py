# products/admin.py
"""
Django Admin interface configuration for catalog Category, Brand, Product, and ProductImage models.
Optimized for merchandising staff and content managers.
"""

from django.contrib import admin
from django.utils.html import format_html
from products.models import Brand, Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "indented_name",
        "slug",
        "parent",
        "sort_order",
        "is_active",
        "image_preview",
        "updated_at",
    )
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "image_preview_large")
    ordering = ("sort_order", "name")
    list_per_page = 50

    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "parent", "description", "is_active", "sort_order")
        }),
        ("Media", {
            "fields": ("image", "image_preview_large")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(description="Category Hierarchy", ordering="name")
    def indented_name(self, obj: Category) -> str:
        depth = len(obj.get_ancestors())
        if depth > 0:
            indent = "&nbsp;" * (depth * 4)
            return format_html('<span style="color: #666;">{}&rsaquo;&nbsp;</span><strong>{}</strong>', indent, obj.name)
        return format_html('<strong>{}</strong>', obj.name)

    @admin.display(description="Thumbnail")
    def image_preview(self, obj: Category) -> str:
        if obj.image and hasattr(obj.image, "url"):
            return format_html(
                '<img src="{}" style="height: 32px; width: auto; max-width: 64px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;" />',
                obj.image.url
            )
        return format_html('<span style="color: #999; font-size: 11px;">None</span>')

    @admin.display(description="Banner Preview")
    def image_preview_large(self, obj: Category) -> str:
        if obj.image and hasattr(obj.image, "url"):
            return format_html(
                '<img src="{}" style="max-height: 160px; max-w-100%; border-radius: 6px; border: 1px solid #ccc;" />',
                obj.image.url
            )
        return format_html('<span style="color: #999;">No image uploaded</span>')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "is_featured",
        "is_active",
        "logo_preview",
        "website_link",
        "updated_at",
    )
    list_editable = ("is_featured", "is_active")
    list_filter = ("is_featured", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "logo_preview_large")
    ordering = ("name",)
    list_per_page = 50

    fieldsets = (
        ("Brand Overview", {
            "fields": ("name", "slug", "description", "website", "is_featured", "is_active")
        }),
        ("Branding Media", {
            "fields": ("logo", "logo_preview_large")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(description="Logo")
    def logo_preview(self, obj: Brand) -> str:
        if obj.logo and hasattr(obj.logo, "url"):
            return format_html(
                '<img src="{}" style="height: 32px; width: auto; max-width: 64px; object-fit: contain; background: #f8fafc; padding: 2px; border-radius: 4px; border: 1px solid #ddd;" />',
                obj.logo.url
            )
        return format_html('<span style="color: #999; font-size: 11px;">None</span>')

    @admin.display(description="Logo Preview")
    def logo_preview_large(self, obj: Brand) -> str:
        if obj.logo and hasattr(obj.logo, "url"):
            return format_html(
                '<img src="{}" style="max-height: 120px; max-w-100%; object-fit: contain; background: #f8fafc; padding: 8px; border-radius: 6px; border: 1px solid #ccc;" />',
                obj.logo.url
            )
        return format_html('<span style="color: #999;">No logo uploaded</span>')

    @admin.display(description="Website")
    def website_link(self, obj: Brand) -> str:
        if obj.website:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" style="color: #0284c7; text-decoration: underline;">Visit Site &nearr;</a>',
                obj.website
            )
        return format_html('<span style="color: #999;">&mdash;</span>')


class ProductImageInline(admin.TabularInline):
    """
    Inline image gallery management for products.
    """
    model = ProductImage
    extra = 1
    fields = ("image", "image_preview", "alt_text", "is_primary", "sort_order")
    readonly_fields = ("image_preview",)
    ordering = ("sort_order", "id")

    @admin.display(description="Preview")
    def image_preview(self, obj: ProductImage) -> str:
        if obj.image and hasattr(obj.image, "url"):
            return format_html(
                '<img src="{}" style="height: 48px; width: 48px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;" />',
                obj.image.url
            )
        return format_html('<span style="color: #999; font-size: 11px;">No image</span>')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Professional administration interface for products.
    Includes filtering, merchandising toggles, stock status indicators, and image galleries.
    """
    list_display = (
        "name",
        "category",
        "brand",
        "price_display",
        "stock_status_badge",
        "is_active",
        "is_featured",
        "is_new_arrival",
        "updated_at",
    )
    list_editable = ("is_active", "is_featured", "is_new_arrival")
    list_filter = ("is_active", "is_featured", "is_new_arrival", "category", "brand")
    search_fields = ("name", "slug", "short_description", "description", "brand__name", "category__name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "view_count", "primary_image_preview")
    ordering = ("-created_at", "name")
    list_per_page = 30
    inlines = [ProductImageInline]

    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "short_description", "description", "primary_image_preview")
        }),
        ("Categorization", {
            "fields": ("category", "brand")
        }),
        ("Pricing & Inventory", {
            "fields": ("price", "compare_at_price", "stock_quantity", "low_stock_threshold", "is_active")
        }),
        ("Merchandising & Analytics", {
            "fields": ("is_featured", "is_new_arrival", "view_count")
        }),
        ("Search Engine Optimization (SEO)", {
            "fields": ("meta_title", "meta_description"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(description="Price", ordering="price")
    def price_display(self, obj: Product) -> str:
        if obj.is_on_sale():
            return format_html(
                '<span style="color: #b91c1c; font-weight: 600;">${}</span> <del style="color: #999; font-size: 11px;">${}</del>',
                obj.price, obj.compare_at_price
            )
        return format_html('<strong>${}</strong>', obj.price)

    @admin.display(description="Stock Status", ordering="stock_quantity")
    def stock_status_badge(self, obj: Product) -> str:
        if obj.stock_quantity == 0:
            return format_html('<span style="color: #dc2626; font-weight: bold; background: #fee2e2; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Out of Stock</span>')
        if obj.low_stock():
            return format_html('<span style="color: #d97706; font-weight: bold; background: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Low ({})</span>', obj.stock_quantity)
        return format_html('<span style="color: #16a34a; font-weight: 500; background: #dcfce7; padding: 2px 6px; border-radius: 4px; font-size: 11px;">In Stock ({})</span>', obj.stock_quantity)

    @admin.display(description="Primary Image Preview")
    def primary_image_preview(self, obj: Product) -> str:
        primary = obj.get_primary_image()
        if primary and primary.image and hasattr(primary.image, "url"):
            return format_html(
                '<img src="{}" style="max-height: 140px; max-w-100%; object-fit: cover; border-radius: 6px; border: 1px solid #ccc;" />',
                primary.image.url
            )
        return format_html('<span style="color: #999;">No image gallery assigned</span>')
