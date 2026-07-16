# dashboard/product_forms.py
"""
dashboard/product_forms.py
──────────────────────────────────────────────────────────────────────────────
Administrative forms for managing catalog products, variants, images, categories,
brands, and product options.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django import forms
from django.utils.text import slugify
from products.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
)


class StaffProductForm(forms.ModelForm):
    """
    Comprehensive administrative form for creating and editing catalog products.
    """
    image = forms.ImageField(
        required=False,
        help_text="Upload an initial primary image for this garment.",
        widget=forms.FileInput(
            attrs={
                "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer",
            }
        ),
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "short_description",
            "description",
            "category",
            "brand",
            "price",
            "compare_at_price",
            "stock_quantity",
            "low_stock_threshold",
            "is_active",
            "is_featured",
            "is_new_arrival",
            "meta_title",
            "meta_description",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., The Weatherproof Trench Coat",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-neutral-50 px-3.5 py-2 text-sm text-neutral-600 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "weatherproof-trench-coat (leave blank to auto-generate)",
                }
            ),
            "short_description": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "Concise summary for product cards and previews...",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "rows": 5,
                    "placeholder": "Detailed description of materials, fit, craftsmanship, and specifications...",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                }
            ),
            "brand": forms.Select(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                }
            ),
            "price": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "compare_at_price": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "0.00 (optional original price)",
                }
            ),
            "stock_quantity": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
            "low_stock_threshold": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "is_featured": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "is_new_arrival": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "meta_title": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "Custom SEO title (defaults to product name)",
                }
            ),
            "meta_description": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm text-neutral-900 shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "Custom SEO description (defaults to short description)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["compare_at_price"].required = False
        self.fields["brand"].required = False
        self.fields["meta_title"].required = False
        self.fields["meta_description"].required = False

        # Order categories cleanly with hierarchy
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("sort_order", "name")
        self.fields["brand"].queryset = Brand.objects.filter(is_active=True).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get("price")
        compare_at_price = cleaned_data.get("compare_at_price")

        if compare_at_price and price and compare_at_price <= price:
            self.add_error(
                "compare_at_price",
                "Compare-at price must be strictly greater than the selling price."
            )
        return cleaned_data

    def save(self, commit=True):
        product = super().save(commit=commit)
        image_file = self.cleaned_data.get("image")
        if image_file:
            if commit:
                try:
                    is_primary = not product.images.filter(is_primary=True).exists()
                    ProductImage.objects.create(
                        product=product,
                        image=image_file,
                        alt_text=product.name,
                        is_primary=is_primary,
                    )
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error("Failed to upload primary image for product '%s': %s", product.name, e, exc_info=True)
                    self.image_upload_error = str(e)
                    product._image_upload_error = str(e)
            else:
                old_save_m2m = getattr(self, "save_m2m", lambda: None)
                def new_save_m2m():
                    if callable(old_save_m2m):
                        old_save_m2m()
                    try:
                        is_primary = not product.images.filter(is_primary=True).exists()
                        ProductImage.objects.create(
                            product=product,
                            image=image_file,
                            alt_text=product.name,
                            is_primary=is_primary,
                        )
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error("Failed to upload primary image for product '%s' in save_m2m: %s", product.name, e, exc_info=True)
                        self.image_upload_error = str(e)
                        product._image_upload_error = str(e)
                self.save_m2m = new_save_m2m
        return product


class StaffProductImageForm(forms.ModelForm):
    """
    Form for uploading images to a product's gallery.
    """
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "is_primary", "sort_order"]
        widgets = {
            "image": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer",
                }
            ),
            "alt_text": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "Descriptive alt text for accessibility",
                }
            ),
            "is_primary": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "class": "block w-24 rounded-lg border-neutral-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["alt_text"].required = False


class StaffProductVariantForm(forms.ModelForm):
    """
    Form for adding or updating a product variant.
    Allows selection of ProductOptionValues for exact combination definition.
    """
    option_values = forms.ModelMultipleChoiceField(
        queryset=ProductOptionValue.objects.select_related("option").order_by("option__sort_order", "display_order"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "block w-full rounded-lg border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600 min-h-[120px]",
            }
        ),
        help_text="Select one value for each relevant option (e.g., Color: Black + Size: Large). Hold Ctrl/Cmd to select multiple.",
    )

    class Meta:
        model = ProductVariant
        fields = [
            "sku",
            "barcode",
            "price_override",
            "compare_at_price",
            "cost_price",
            "stock_quantity",
            "low_stock_threshold",
            "weight",
            "dimensions",
            "image",
            "is_active",
            "option_values",
        ]
        widgets = {
            "sku": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600 font-mono",
                    "placeholder": "e.g., HOB-TRENCH-BLK-L (leave blank to auto-generate)",
                }
            ),
            "barcode": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "UPC / EAN / Barcode",
                }
            ),
            "price_override": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "Leave blank to use base product price",
                }
            ),
            "compare_at_price": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "Leave blank to use base compare price",
                }
            ),
            "cost_price": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "Wholesale / Manufacturing cost",
                }
            ),
            "stock_quantity": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
            "low_stock_threshold": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
            "weight": forms.NumberInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "step": "0.01",
                    "placeholder": "Weight in kg",
                }
            ),
            "dimensions": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., 30x20x5 cm",
                }
            ),
            "image": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        self.fields["barcode"].required = False
        self.fields["price_override"].required = False
        self.fields["compare_at_price"].required = False
        self.fields["cost_price"].required = False
        self.fields["weight"].required = False
        self.fields["dimensions"].required = False
        self.fields["image"].required = False

        if self.instance and self.instance.pk:
            self.fields["option_values"].initial = self.instance.option_values.all()

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get("price_override")
        compare = cleaned_data.get("compare_at_price")
        if price and compare and compare <= price:
            self.add_error("compare_at_price", "Variant compare-at price must be greater than the override price.")
        return cleaned_data


class StaffCategoryForm(forms.ModelForm):
    """
    Form for creating and editing hierarchical catalog categories.
    """
    class Meta:
        model = Category
        fields = ["name", "slug", "parent", "description", "image", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., Men's Outerwear",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-neutral-50 px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "mens-outerwear (leave blank to auto-generate)",
                }
            ),
            "parent": forms.Select(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "rows": 3,
                    "placeholder": "Editorial category story...",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "class": "block w-24 rounded-lg border-neutral-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["parent"].required = False
        self.fields["description"].required = False

        # Prevent a category from being its own parent on edit
        qs = Category.objects.order_by("sort_order", "name")
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs


class StaffBrandForm(forms.ModelForm):
    """
    Form for creating and editing brand houses and manufacturers.
    """
    class Meta:
        model = Brand
        fields = ["name", "slug", "description", "logo", "website", "is_featured", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., Loro Piana / House of Bore Atelier",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-neutral-50 px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "loro-piana (leave blank to auto-generate)",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "rows": 3,
                    "placeholder": "Heritage story & luxury atelier overview...",
                }
            ),
            "logo": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer",
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "https://www.brandwebsite.com",
                }
            ),
            "is_featured": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["description"].required = False
        self.fields["logo"].required = False
        self.fields["website"].required = False


class StaffProductOptionForm(forms.ModelForm):
    """
    Form for creating/editing product option groups (e.g., Color, Size, Material).
    """
    class Meta:
        model = ProductOption
        fields = ["name", "display_name", "sort_order", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., Color, Size, Material",
                }
            ),
            "display_name": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "Customer-facing label (e.g., Select Color)",
                }
            ),
            "sort_order": forms.NumberInput(
                attrs={
                    "class": "block w-24 rounded-lg border-neutral-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-600"}
            ),
        }


class StaffProductOptionValueForm(forms.ModelForm):
    """
    Form for adding values to a product option group (e.g., Black, White for Color).
    """
    class Meta:
        model = ProductOptionValue
        fields = ["value", "display_order"]
        widgets = {
            "value": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-lg border-neutral-300 bg-white px-3.5 py-2 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "placeholder": "e.g., Black, Medium, 100% Cashmere",
                }
            ),
            "display_order": forms.NumberInput(
                attrs={
                    "class": "block w-24 rounded-lg border-neutral-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600",
                    "min": "0",
                }
            ),
        }
