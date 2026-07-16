# dashboard/product_views.py
"""
dashboard/product_views.py
──────────────────────────────────────────────────────────────────────────────
Administrative views and controllers for the Product Catalog subsystem.
Allows store personnel and supervisors to inspect, create, update, and prune
Products, Variants, Image Galleries, Categories, Brands, and Product Options.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from dashboard.permissions import DashboardPermissionRequiredMixin, has_dashboard_permission
from dashboard.services import create_audit_log
from products.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
)
from products.services import create_variant, update_variant
from .product_forms import (
    StaffBrandForm,
    StaffCategoryForm,
    StaffProductForm,
    StaffProductImageForm,
    StaffProductOptionForm,
    StaffProductOptionValueForm,
    StaffProductVariantForm,
)


# ─── PRODUCT CATALOG DIRECTORY & KPI SUMMARY ──────────────────────────────────
class StaffProductsListView(DashboardPermissionRequiredMixin, ListView):
    """
    Paginated administrative directory of catalog products with filtering across
    category, brand, inventory availability status, and keyword search.
    """
    required_permissions = ["products.view_product"]
    template_name = "dashboard/products/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.all().select_related("category", "brand").prefetch_related(
            "images", "variants"
        ).order_by("-created_at")

        category_filter = self.request.GET.get("category", "all")
        brand_filter = self.request.GET.get("brand", "all")
        status_filter = self.request.GET.get("status", "all")
        visibility_filter = self.request.GET.get("visibility", "all")
        search_query = self.request.GET.get("search", "").strip()

        if category_filter and category_filter != "all":
            qs = qs.filter(Q(category__slug=category_filter) | Q(category_id=category_filter))
        if brand_filter and brand_filter != "all":
            qs = qs.filter(Q(brand__slug=brand_filter) | Q(brand_id=brand_filter))
        if visibility_filter == "active":
            qs = qs.filter(is_active=True)
        elif visibility_filter == "draft":
            qs = qs.filter(is_active=False)

        if status_filter == "in_stock":
            qs = qs.filter(stock_quantity__gt=0)
        elif status_filter == "low_stock":
            qs = qs.filter(stock_quantity__gt=0, stock_quantity__lte=5)
        elif status_filter == "out_of_stock":
            qs = qs.filter(stock_quantity=0)

        if search_query:
            qs = qs.filter(
                Q(name__icontains=search_query)
                | Q(slug__icontains=search_query)
                | Q(short_description__icontains=search_query)
                | Q(variants__sku__icontains=search_query)
            ).distinct()

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        all_products = Product.objects.all()

        stats = {
            "total_products": all_products.count(),
            "active_products": all_products.filter(is_active=True).count(),
            "out_of_stock_count": all_products.filter(stock_quantity=0).count(),
            "low_stock_count": all_products.filter(stock_quantity__gt=0, stock_quantity__lte=5).count(),
            "total_categories": Category.objects.count(),
            "total_brands": Brand.objects.count(),
            "total_variants": ProductVariant.objects.count(),
        }

        context.update({
            "active_nav": "products",
            "stats": stats,
            "categories": Category.objects.filter(is_active=True).order_by("sort_order", "name"),
            "brands": Brand.objects.filter(is_active=True).order_by("name"),
            "category_filter": self.request.GET.get("category", "all"),
            "brand_filter": self.request.GET.get("brand", "all"),
            "status_filter": self.request.GET.get("status", "all"),
            "visibility_filter": self.request.GET.get("visibility", "all"),
            "search_query": self.request.GET.get("search", ""),
            "can_add_product": has_dashboard_permission(self.request.user, "products.add_product"),
            "can_change_product": has_dashboard_permission(self.request.user, "products.change_product"),
            "can_delete_product": has_dashboard_permission(self.request.user, "products.delete_product"),
        })
        return context


# ─── PRODUCT CREATE / UPDATE / DELETE / TOGGLE VIEWS ──────────────────────────
class StaffProductCreateView(DashboardPermissionRequiredMixin, CreateView):
    """
    Administrative view for creating a new product catalog item.
    """
    required_permissions = ["products.add_product"]
    model = Product
    form_class = StaffProductForm
    template_name = "dashboard/products/product_form.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "is_create": True,
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        create_audit_log(
            user=self.request.user,
            action="CREATE_PRODUCT",
            description=f"Created product '{self.object.name}' (ID: {self.object.pk}).",
            model_name="Product",
            object_id=self.object.pk,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        image_error = getattr(form, "image_upload_error", None) or getattr(self.object, "_image_upload_error", None)
        if image_error:
            messages.warning(self.request, f"Product '{self.object.name}' was created successfully, but image upload failed due to storage permissions or configuration: {image_error}")
        else:
            messages.success(self.request, f"Product '{self.object.name}' successfully created! Now you can upload images and configure variants.")
        return redirect("dashboard:product_edit", pk=self.object.pk)


class StaffProductUpdateView(DashboardPermissionRequiredMixin, UpdateView):
    """
    Administrative view for updating a product, along with its image gallery and variants.
    """
    required_permissions = ["products.change_product"]
    model = Product
    form_class = StaffProductForm
    template_name = "dashboard/products/product_form.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "is_create": False,
            "images": self.object.images.all().order_by("-is_primary", "sort_order", "id"),
            "image_form": StaffProductImageForm(),
            "variants": self.object.variants.all().select_related("product").prefetch_related("option_values__option").order_by("sku"),
            "variant_form": StaffProductVariantForm(),
            "can_delete_product": has_dashboard_permission(self.request.user, "products.delete_product"),
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        create_audit_log(
            user=self.request.user,
            action="UPDATE_PRODUCT",
            description=f"Updated product '{self.object.name}' (ID: {self.object.pk}).",
            model_name="Product",
            object_id=self.object.pk,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        image_error = getattr(form, "image_upload_error", None) or getattr(self.object, "_image_upload_error", None)
        if image_error:
            messages.warning(self.request, f"Product '{self.object.name}' updated successfully, but image upload failed due to storage permissions or configuration: {image_error}")
        else:
            messages.success(self.request, f"Product '{self.object.name}' successfully updated.")
        return redirect("dashboard:product_edit", pk=self.object.pk)


class StaffProductDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for permanently deleting a product from the catalog.
    """
    required_permissions = ["products.delete_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        product = get_object_or_404(Product, pk=pk)
        name = product.name
        product_id = product.pk
        product.delete()

        create_audit_log(
            user=request.user,
            action="DELETE_PRODUCT",
            description=f"Deleted product '{name}' (ID: {product_id}).",
            model_name="Product",
            object_id=product_id,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Product '{name}' has been deleted.")
        return redirect("dashboard:products")


class StaffProductToggleActiveView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for toggling the published/draft status (`is_active`) of a product.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        product = get_object_or_404(Product, pk=pk)
        product.is_active = not product.is_active
        product.save(update_fields=["is_active", "updated_at"])

        status_text = "Published" if product.is_active else "Set to Draft"
        create_audit_log(
            user=request.user,
            action="TOGGLE_PRODUCT_STATUS",
            description=f"{status_text} product '{product.name}' (ID: {product.pk}).",
            model_name="Product",
            object_id=product.pk,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Product '{product.name}' is now {status_text.lower()}.")
        
        referer = request.META.get("HTTP_REFERER")
        if referer:
            return redirect(referer)
        return redirect("dashboard:products")


# ─── PRODUCT IMAGE GALLERY MANAGEMENT VIEWS ───────────────────────────────────
class StaffProductImageUploadView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for adding an image to a product's gallery.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        product = get_object_or_404(Product, pk=pk)
        form = StaffProductImageForm(request.POST, request.FILES)
        if form.is_valid():
            img = form.save(commit=False)
            img.product = product
            try:
                img.save()
                create_audit_log(
                    user=request.user,
                    action="UPLOAD_PRODUCT_IMAGE",
                    description=f"Uploaded image ID {img.pk} for product '{product.name}'.",
                    model_name="ProductImage",
                    object_id=img.pk,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, "Image added to product gallery.")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("Failed to upload gallery image for product '%s': %s", product.name, e, exc_info=True)
                messages.error(request, f"Image upload failed due to storage permissions or configuration: {e}")
        else:
            for error in form.errors.values():
                messages.error(request, f"Image upload error: {error}")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': pk})}#gallery")


class StaffProductImageDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for deleting a specific gallery image.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, image_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        img = get_object_or_404(ProductImage, pk=image_id)
        product_id = img.product_id
        img.delete()

        create_audit_log(
            user=request.user,
            action="DELETE_PRODUCT_IMAGE",
            description=f"Deleted image ID {image_id} from product ID {product_id}.",
            model_name="ProductImage",
            object_id=image_id,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Gallery image removed.")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': product_id})}#gallery")


class StaffProductImageMakePrimaryView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for setting an image as the primary thumbnail of its product.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, image_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        img = get_object_or_404(ProductImage, pk=image_id)
        img.is_primary = True
        img.save()  # Model save() method automatically unsets primary on sibling images

        create_audit_log(
            user=request.user,
            action="SET_PRIMARY_IMAGE",
            description=f"Set image ID {image_id} as primary thumbnail for product '{img.product.name}'.",
            model_name="ProductImage",
            object_id=image_id,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, "Primary product thumbnail updated.")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': img.product_id})}#gallery")


# ─── PRODUCT VARIANTS & SKUS MANAGEMENT VIEWS ─────────────────────────────────
class StaffProductVariantCreateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for creating a variant under a specific product.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        product = get_object_or_404(Product, pk=pk)
        form = StaffProductVariantForm(request.POST, request.FILES)
        if form.is_valid():
            cleaned = form.cleaned_data
            option_values = cleaned.pop("option_values", [])
            
            try:
                variant = create_variant(
                    product=product,
                    sku=cleaned.get("sku") or "",
                    option_values=list(option_values),
                    barcode=cleaned.get("barcode") or "",
                    price_override=cleaned.get("price_override"),
                    compare_at_price=cleaned.get("compare_at_price"),
                    cost_price=cleaned.get("cost_price"),
                    stock_quantity=cleaned.get("stock_quantity") or 0,
                    low_stock_threshold=cleaned.get("low_stock_threshold") or 5,
                    weight=cleaned.get("weight"),
                    dimensions=cleaned.get("dimensions") or "",
                    image=cleaned.get("image"),
                    is_active=cleaned.get("is_active", True),
                )
                create_audit_log(
                    user=request.user,
                    action="CREATE_VARIANT",
                    description=f"Created variant '{variant.sku}' for product '{product.name}'.",
                    model_name="ProductVariant",
                    object_id=variant.pk,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, f"Variant '{variant.sku}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error creating variant: {e}")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Variant {field}: {err}")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': pk})}#variants")


class StaffProductVariantUpdateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint or view for editing an existing product variant.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, variant_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        variant = get_object_or_404(ProductVariant, pk=variant_id)
        product_id = variant.product_id
        form = StaffProductVariantForm(request.POST, request.FILES, instance=variant)
        if form.is_valid():
            cleaned = form.cleaned_data
            option_values = cleaned.pop("option_values", None)
            
            try:
                update_variant(
                    variant=variant,
                    option_values=list(option_values) if option_values is not None else None,
                    **cleaned
                )
                create_audit_log(
                    user=request.user,
                    action="UPDATE_VARIANT",
                    description=f"Updated variant '{variant.sku}' (ID: {variant.pk}).",
                    model_name="ProductVariant",
                    object_id=variant.pk,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, f"Variant '{variant.sku}' updated successfully.")
            except Exception as e:
                messages.error(request, f"Error updating variant: {e}")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Variant {field}: {err}")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': product_id})}#variants")


class StaffProductVariantDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for deleting a product variant.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, variant_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        variant = get_object_or_404(ProductVariant, pk=variant_id)
        sku = variant.sku
        product_id = variant.product_id
        variant.delete()

        create_audit_log(
            user=request.user,
            action="DELETE_VARIANT",
            description=f"Deleted variant '{sku}' from product ID {product_id}.",
            model_name="ProductVariant",
            object_id=variant_id,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Variant '{sku}' deleted.")
        return redirect(f"{reverse('dashboard:product_edit', kwargs={'pk': product_id})}#variants")


# ─── CATEGORIES MANAGEMENT VIEWS ──────────────────────────────────────────────
class StaffCategoriesListView(DashboardPermissionRequiredMixin, ListView):
    """
    Administrative directory of all catalog categories with hierarchical hierarchy display.
    """
    required_permissions = ["products.view_product"]
    template_name = "dashboard/products/categories_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return Category.objects.all().annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        ).order_by("sort_order", "name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "active_subnav": "categories",
            "form": StaffCategoryForm(),
            "can_add_category": has_dashboard_permission(self.request.user, "products.change_product"),
            "can_delete_category": has_dashboard_permission(self.request.user, "products.change_product"),
        })
        return context


class StaffCategoryCreateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for creating a new catalog category.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = StaffCategoryForm(request.POST, request.FILES)
        if form.is_valid():
            cat = form.save()
            create_audit_log(
                user=request.user,
                action="CREATE_CATEGORY",
                description=f"Created category '{cat.name}' (ID: {cat.pk}).",
                model_name="Category",
                object_id=cat.pk,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Category '{cat.name}' created.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Category {field}: {err}")
        return redirect("dashboard:categories")


class StaffCategoryUpdateView(DashboardPermissionRequiredMixin, UpdateView):
    """
    Administrative view for updating an existing category.
    """
    required_permissions = ["products.change_product"]
    model = Category
    form_class = StaffCategoryForm
    template_name = "dashboard/products/category_form.html"
    success_url = reverse_lazy("dashboard:categories")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "active_subnav": "categories",
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        create_audit_log(
            user=self.request.user,
            action="UPDATE_CATEGORY",
            description=f"Updated category '{self.object.name}' (ID: {self.object.pk}).",
            model_name="Category",
            object_id=self.object.pk,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        messages.success(self.request, f"Category '{self.object.name}' updated successfully.")
        return response


class StaffCategoryDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for deleting a category with safety check for active products.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        cat = get_object_or_404(Category, pk=pk)
        if cat.products.exists() or cat.children.exists():
            messages.error(request, f"Cannot delete category '{cat.name}' because it contains products or subcategories. Reassign them first.")
            return redirect("dashboard:categories")

        name = cat.name
        cat.delete()
        create_audit_log(
            user=request.user,
            action="DELETE_CATEGORY",
            description=f"Deleted category '{name}' (ID: {pk}).",
            model_name="Category",
            object_id=pk,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Category '{name}' deleted.")
        return redirect("dashboard:categories")


# ─── BRANDS MANAGEMENT VIEWS ──────────────────────────────────────────────────
class StaffBrandsListView(DashboardPermissionRequiredMixin, ListView):
    """
    Administrative directory of brand houses and manufacturers.
    """
    required_permissions = ["products.view_product"]
    template_name = "dashboard/products/brands_list.html"
    context_object_name = "brands"

    def get_queryset(self):
        return Brand.objects.all().annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        ).order_by("name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "active_subnav": "brands",
            "form": StaffBrandForm(),
            "can_add_brand": has_dashboard_permission(self.request.user, "products.change_product"),
            "can_delete_brand": has_dashboard_permission(self.request.user, "products.change_product"),
        })
        return context


class StaffBrandCreateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for creating a new brand.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = StaffBrandForm(request.POST, request.FILES)
        if form.is_valid():
            brand = form.save()
            create_audit_log(
                user=request.user,
                action="CREATE_BRAND",
                description=f"Created brand '{brand.name}' (ID: {brand.pk}).",
                model_name="Brand",
                object_id=brand.pk,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Brand '{brand.name}' created.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Brand {field}: {err}")
        return redirect("dashboard:brands")


class StaffBrandUpdateView(DashboardPermissionRequiredMixin, UpdateView):
    """
    Administrative view for updating an existing brand.
    """
    required_permissions = ["products.change_product"]
    model = Brand
    form_class = StaffBrandForm
    template_name = "dashboard/products/brand_form.html"
    success_url = reverse_lazy("dashboard:brands")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "active_subnav": "brands",
        })
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        create_audit_log(
            user=self.request.user,
            action="UPDATE_BRAND",
            description=f"Updated brand '{self.object.name}' (ID: {self.object.pk}).",
            model_name="Brand",
            object_id=self.object.pk,
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        messages.success(self.request, f"Brand '{self.object.name}' updated successfully.")
        return response


class StaffBrandDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for deleting a brand with safety check for active products.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        brand = get_object_or_404(Brand, pk=pk)
        if brand.products.exists():
            messages.error(request, f"Cannot delete brand '{brand.name}' because products are currently assigned to it. Reassign them first.")
            return redirect("dashboard:brands")

        name = brand.name
        brand.delete()
        create_audit_log(
            user=request.user,
            action="DELETE_BRAND",
            description=f"Deleted brand '{name}' (ID: {pk}).",
            model_name="Brand",
            object_id=pk,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        messages.success(request, f"Brand '{name}' deleted.")
        return redirect("dashboard:brands")


# ─── PRODUCT OPTIONS & VALUES MANAGEMENT VIEWS ────────────────────────────────
class StaffOptionsListView(DashboardPermissionRequiredMixin, ListView):
    """
    Administrative directory of Product Option groups and their selectable values.
    """
    required_permissions = ["products.view_product"]
    template_name = "dashboard/products/options_list.html"
    context_object_name = "options"

    def get_queryset(self):
        return ProductOption.objects.all().prefetch_related("values").order_by("sort_order", "name")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "products",
            "active_subnav": "options",
            "option_form": StaffProductOptionForm(),
            "value_form": StaffProductOptionValueForm(),
        })
        return context


class StaffOptionCreateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for creating a new product option group (e.g., Color, Size).
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = StaffProductOptionForm(request.POST)
        if form.is_valid():
            opt = form.save()
            create_audit_log(
                user=request.user,
                action="CREATE_OPTION",
                description=f"Created option group '{opt.name}' (ID: {opt.pk}).",
                model_name="ProductOption",
                object_id=opt.pk,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Option group '{opt.name}' added.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Option {field}: {err}")
        return redirect("dashboard:options")


class StaffOptionValueCreateView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for adding a new value to an existing option group.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, option_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        opt = get_object_or_404(ProductOption, pk=option_id)
        form = StaffProductOptionValueForm(request.POST)
        if form.is_valid():
            val = form.save(commit=False)
            val.option = opt
            val.save()
            create_audit_log(
                user=request.user,
                action="CREATE_OPTION_VALUE",
                description=f"Added value '{val.value}' to option group '{opt.name}'.",
                model_name="ProductOptionValue",
                object_id=val.pk,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, f"Value '{val.value}' added to {opt.display_name or opt.name}.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"Value {field}: {err}")
        return redirect("dashboard:options")


class StaffOptionValueDeleteView(DashboardPermissionRequiredMixin, View):
    """
    POST endpoint for deleting an option value.
    """
    required_permissions = ["products.change_product"]

    def post(self, request: HttpRequest, value_id: int, *args: Any, **kwargs: Any) -> HttpResponse:
        val = get_object_or_404(ProductOptionValue, pk=value_id)
        val_name = val.value
        val.delete()
        messages.success(request, f"Option value '{val_name}' deleted.")
        return redirect("dashboard:options")
