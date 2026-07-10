# products/tests.py
"""
Comprehensive automated test suite for the public product catalog.
Tests models, managers, selectors, views, URL routing, pagination, sorting,
template rendering, image relationships, and admin registration.
"""

from decimal import Decimal
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import resolve, reverse
from products.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
    RecentlyViewedProduct,
)
from products.selectors import (
    DEFAULT_SORT,
    SORT_OPTIONS,
    filter_products,
    get_active_brands,
    get_active_categories,
    get_active_products,
    get_brand_by_slug,
    get_brands_with_product_counts,
    get_categories_with_product_counts,
    get_category_by_slug,
    get_category_tree,
    get_featured_brands,
    get_featured_products,
    get_filter_options,
    get_latest_products,
    get_low_stock_products,
    get_new_arrivals,
    get_product_by_slug,
    get_products_by_brand,
    get_products_by_category,
    get_related_products,
    get_root_categories,
    search_products,
    sort_products,
)
from products.services import increment_product_views, mark_product_featured
from products.views import (
    BrandDetailView,
    BrandListView,
    CategoryDetailView,
    CategoryListView,
    ProductDetailView,
    ProductListView,
)


# ─── Model Tests ─────────────────────────────────────────────────────────────

class CategoryModelTests(TestCase):
    def test_category_creation_and_auto_slug(self):
        cat = Category.objects.create(name="Men's Tailoring")
        self.assertEqual(cat.slug, "mens-tailoring")
        self.assertEqual(str(cat), "Men's Tailoring")
        self.assertTrue(cat.is_active)
        self.assertEqual(cat.sort_order, 0)

    def test_nested_category_string_representation(self):
        root = Category.objects.create(name="Apparel", slug="apparel")
        child = Category.objects.create(name="Outerwear", slug="outerwear", parent=root)
        self.assertEqual(str(child), "Apparel > Outerwear")
        self.assertEqual(child.get_ancestors(), [root])
        self.assertIn(child, root.get_descendants())

    def test_circular_reference_self_parent(self):
        cat = Category.objects.create(name="Footwear", slug="footwear")
        cat.parent = cat
        with self.assertRaises(ValidationError) as cm:
            cat.save()
        self.assertIn("parent", cm.exception.message_dict)

    def test_circular_reference_ancestor_loop(self):
        root = Category.objects.create(name="Root", slug="root")
        child = Category.objects.create(name="Child", slug="child", parent=root)
        grandchild = Category.objects.create(name="Grandchild", slug="grandchild", parent=child)

        root.parent = grandchild
        with self.assertRaises(ValidationError) as cm:
            root.save()
        self.assertIn("parent", cm.exception.message_dict)

    def test_category_ordering(self):
        cat2 = Category.objects.create(name="Zebra", sort_order=10)
        cat1 = Category.objects.create(name="Alpha", sort_order=5)
        cat3 = Category.objects.create(name="Beta", sort_order=5)

        categories = list(Category.objects.all())
        self.assertEqual(categories, [cat1, cat3, cat2])


class BrandModelTests(TestCase):
    def test_brand_creation_and_auto_slug(self):
        brand = Brand.objects.create(name="House Of Bore")
        self.assertEqual(brand.slug, "house-of-bore")
        self.assertEqual(str(brand), "House Of Bore")
        self.assertTrue(brand.is_active)
        self.assertFalse(brand.is_featured)

    def test_brand_ordering(self):
        brand2 = Brand.objects.create(name="Urban Edge")
        brand1 = Brand.objects.create(name="Apex Wear")
        self.assertEqual(list(Brand.objects.all()), [brand1, brand2])


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Outerwear")
        self.brand = Brand.objects.create(name="House Of Bore")

    def test_product_creation_and_auto_slug(self):
        product = Product.objects.create(
            name="The Weatherproof Trench Coat",
            short_description="Organic gabardine trench.",
            description="Detailed craftsmanship description.",
            category=self.category,
            brand=self.brand,
            price=Decimal("680.00"),
            stock_quantity=10,
        )
        self.assertEqual(product.slug, "the-weatherproof-trench-coat")
        self.assertEqual(str(product), "The Weatherproof Trench Coat")
        self.assertEqual(product.meta_title, "The Weatherproof Trench Coat")
        self.assertEqual(product.meta_description, "Organic gabardine trench.")
        self.assertTrue(product.is_available())
        self.assertTrue(product.in_stock())
        self.assertFalse(product.low_stock())
        self.assertFalse(product.is_on_sale())
        self.assertEqual(product.discount_percentage(), 0)

    def test_slug_collision_prevention(self):
        p1 = Product.objects.create(
            name="Classic Trench Coat",
            short_description="Short desc",
            description="Desc",
            category=self.category,
            price=Decimal("500.00")
        )
        p2 = Product.objects.create(
            name="Classic Trench Coat",
            short_description="Short desc",
            description="Desc",
            category=self.category,
            price=Decimal("550.00")
        )
        self.assertEqual(p1.slug, "classic-trench-coat")
        self.assertEqual(p2.slug, "classic-trench-coat-1")

    def test_pricing_and_discount_calculations(self):
        product = Product.objects.create(
            name="Sale Trench Coat",
            short_description="Short desc",
            description="Desc",
            category=self.category,
            price=Decimal("400.00"),
            compare_at_price=Decimal("500.00"),
            stock_quantity=5,
            low_stock_threshold=5
        )
        self.assertTrue(product.is_on_sale())
        self.assertEqual(product.discount_percentage(), 20)
        self.assertTrue(product.low_stock())

    def test_negative_price_validation(self):
        product = Product(
            name="Invalid Price Item",
            short_description="Short",
            description="Desc",
            category=self.category,
            price=Decimal("-10.00")
        )
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        self.assertIn("price", cm.exception.message_dict)

    def test_compare_at_price_validation(self):
        product = Product(
            name="Invalid Discount Item",
            short_description="Short",
            description="Desc",
            category=self.category,
            price=Decimal("500.00"),
            compare_at_price=Decimal("400.00")
        )
        with self.assertRaises(ValidationError) as cm:
            product.clean()
        self.assertIn("compare_at_price", cm.exception.message_dict)

    def test_get_absolute_url(self):
        product = Product.objects.create(
            name="URL Test Product",
            short_description="Short",
            description="Desc",
            category=self.category,
            price=Decimal("100.00")
        )
        self.assertEqual(product.get_absolute_url(), f"/products/{product.slug}/")


class ProductImageModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Shoes")
        self.product = Product.objects.create(
            name="Leather Chelsea Boots",
            short_description="Boots",
            description="Full desc",
            category=self.category,
            price=Decimal("480.00")
        )

    def test_first_image_automatically_marked_primary(self):
        img1 = ProductImage.objects.create(product=self.product, image="products/boot1.jpg")
        self.assertTrue(img1.is_primary)
        self.assertEqual(self.product.get_primary_image(), img1)

    def test_setting_new_primary_image_unsets_previous(self):
        img1 = ProductImage.objects.create(product=self.product, image="products/boot1.jpg", is_primary=True)
        img2 = ProductImage.objects.create(product=self.product, image="products/boot2.jpg", is_primary=True)
        img1.refresh_from_db()
        img2.refresh_from_db()
        self.assertFalse(img1.is_primary)
        self.assertTrue(img2.is_primary)
        self.assertEqual(self.product.get_primary_image(), img2)


# ─── QuerySet Manager Tests ──────────────────────────────────────────────────

class ProductQuerySetTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Knitwear")
        self.brand = Brand.objects.create(name="North Trail")

        self.p_active_featured = Product.objects.create(
            name="Active Featured",
            short_description="Short",
            description="Desc",
            category=self.category,
            brand=self.brand,
            price=Decimal("300.00"),
            stock_quantity=10,
            is_active=True,
            is_featured=True,
            is_new_arrival=False
        )
        self.p_active_new = Product.objects.create(
            name="Active New Arrival",
            short_description="Short",
            description="Desc",
            category=self.category,
            brand=self.brand,
            price=Decimal("250.00"),
            stock_quantity=2,
            low_stock_threshold=5,
            is_active=True,
            is_featured=False,
            is_new_arrival=True
        )
        self.p_inactive = Product.objects.create(
            name="Inactive Product",
            short_description="Short",
            description="Desc",
            category=self.category,
            price=Decimal("100.00"),
            is_active=False
        )

    def test_queryset_active(self):
        self.assertCountEqual(
            list(Product.objects.active()),
            [self.p_active_featured, self.p_active_new]
        )

    def test_queryset_featured(self):
        self.assertEqual(list(Product.objects.featured()), [self.p_active_featured])

    def test_queryset_new_arrivals(self):
        self.assertEqual(list(Product.objects.new_arrivals()), [self.p_active_new])

    def test_queryset_in_stock(self):
        self.assertCountEqual(
            list(Product.objects.in_stock()),
            [self.p_active_featured, self.p_active_new]
        )

    def test_queryset_excludes_inactive(self):
        self.assertNotIn(self.p_inactive, Product.objects.active())


# ─── Selector Tests ──────────────────────────────────────────────────────────

class CategorySelectorTests(TestCase):
    def setUp(self):
        self.root = Category.objects.create(name="Men's Clothing", slug="mens-clothing")
        self.child = Category.objects.create(name="Suiting", slug="suiting", parent=self.root)
        self.inactive = Category.objects.create(name="Archived", slug="archived", is_active=False)

    def test_get_active_categories(self):
        cats = get_active_categories()
        self.assertIn(self.root, cats)
        self.assertIn(self.child, cats)
        self.assertNotIn(self.inactive, cats)

    def test_get_root_categories(self):
        roots = get_root_categories()
        self.assertIn(self.root, roots)
        self.assertNotIn(self.child, roots)

    def test_get_category_tree(self):
        tree = get_category_tree()
        self.assertIn(self.root, tree)
        self.assertNotIn(self.child, tree)  # child is prefetched, not in root QS

    def test_get_category_by_slug(self):
        found = get_category_by_slug("mens-clothing")
        self.assertEqual(found, self.root)

    def test_get_category_by_slug_raises_for_inactive(self):
        with self.assertRaises(Category.DoesNotExist):
            get_category_by_slug("archived")

    def test_get_categories_with_product_counts(self):
        Product.objects.create(
            name="Test Suit",
            short_description="S",
            description="D",
            category=self.root,
            price=Decimal("500.00"),
            is_active=True
        )
        cats = get_categories_with_product_counts()
        root_cat = [c for c in cats if c.slug == "mens-clothing"][0]
        self.assertEqual(root_cat.product_count, 1)


class BrandSelectorTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name="House Of Bore", slug="house-of-bore", is_featured=True)
        self.inactive_brand = Brand.objects.create(name="Defunct", slug="defunct", is_active=False)

    def test_get_active_brands(self):
        brands = get_active_brands()
        self.assertIn(self.brand, brands)
        self.assertNotIn(self.inactive_brand, brands)

    def test_get_featured_brands(self):
        self.assertIn(self.brand, get_featured_brands())

    def test_get_brand_by_slug(self):
        found = get_brand_by_slug("house-of-bore")
        self.assertEqual(found, self.brand)

    def test_get_brand_by_slug_raises_for_inactive(self):
        with self.assertRaises(Brand.DoesNotExist):
            get_brand_by_slug("defunct")

    def test_get_brands_with_product_counts(self):
        cat = Category.objects.create(name="Shoes")
        Product.objects.create(
            name="Test Shoe",
            short_description="S",
            description="D",
            category=cat,
            brand=self.brand,
            price=Decimal("300.00"),
            is_active=True
        )
        brands = get_brands_with_product_counts()
        b = [x for x in brands if x.slug == "house-of-bore"][0]
        self.assertEqual(b.product_count, 1)


class ProductSelectorTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Outerwear", slug="outerwear")
        self.brand = Brand.objects.create(name="Urban Edge", slug="urban-edge")
        self.product = Product.objects.create(
            name="Technical Parka",
            slug="technical-parka",
            short_description="Waterproof parka",
            description="Full desc",
            category=self.category,
            brand=self.brand,
            price=Decimal("790.00"),
            stock_quantity=10,
            is_active=True,
            is_featured=True,
            is_new_arrival=True
        )

    def test_get_active_products(self):
        products = get_active_products()
        self.assertIn(self.product, products)

    def test_get_featured_products(self):
        self.assertIn(self.product, get_featured_products())

    def test_get_new_arrivals(self):
        self.assertIn(self.product, get_new_arrivals())

    def test_get_latest_products(self):
        latest = get_latest_products(limit=5)
        self.assertIn(self.product, latest)

    def test_get_products_by_category(self):
        products = get_products_by_category(self.category)
        self.assertIn(self.product, products)

    def test_get_products_by_brand(self):
        products = get_products_by_brand(self.brand)
        self.assertIn(self.product, products)

    def test_get_product_by_slug(self):
        found = get_product_by_slug("technical-parka")
        self.assertEqual(found, self.product)

    def test_get_product_by_slug_raises_for_missing(self):
        with self.assertRaises(Product.DoesNotExist):
            get_product_by_slug("nonexistent-slug")

    def test_get_low_stock_products(self):
        low = Product.objects.create(
            name="Low Stock Item",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("100.00"),
            stock_quantity=2,
            low_stock_threshold=5,
            is_active=True
        )
        self.assertIn(low, get_low_stock_products())
        self.assertNotIn(self.product, get_low_stock_products())

    def test_get_related_products(self):
        rel1 = Product.objects.create(
            name="Related 1",
            slug="rel-1",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("100.00"),
            is_active=True
        )
        rel2 = Product.objects.create(
            name="Related 2",
            slug="rel-2",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("200.00"),
            is_active=True
        )
        inactive_rel = Product.objects.create(
            name="Inactive Related",
            slug="inactive-rel",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("300.00"),
            is_active=False
        )
        related = get_related_products(self.product, limit=4)
        self.assertIn(rel1, related)
        self.assertIn(rel2, related)
        self.assertNotIn(self.product, related)
        self.assertNotIn(inactive_rel, related)


# ─── Sorting Tests ────────────────────────────────────────────────────────────

class SortingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="All")
        self.cheap = Product.objects.create(
            name="Cheap Item",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("50.00"),
            stock_quantity=10,
            is_active=True
        )
        self.expensive = Product.objects.create(
            name="Expensive Item",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("999.00"),
            stock_quantity=10,
            is_active=True,
            is_featured=True
        )

    def test_sort_price_asc(self):
        products = list(get_active_products(sort="price_asc"))
        self.assertEqual(products[0], self.cheap)
        self.assertEqual(products[1], self.expensive)

    def test_sort_price_desc(self):
        products = list(get_active_products(sort="price_desc"))
        self.assertEqual(products[0], self.expensive)
        self.assertEqual(products[1], self.cheap)

    def test_sort_invalid_key_defaults_to_newest(self):
        products_default = list(get_active_products(sort="invalid_key"))
        products_newest = list(get_active_products(sort="newest"))
        self.assertEqual(products_default, products_newest)


# ─── Services Tests ──────────────────────────────────────────────────────────

class ProductServicesTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Accessories")
        self.product = Product.objects.create(
            name="Leather Wallet",
            short_description="Wallet",
            description="Desc",
            category=self.category,
            price=Decimal("150.00"),
            view_count=10,
            is_featured=False
        )

    def test_increment_product_views(self):
        increment_product_views(self.product)
        self.assertEqual(self.product.view_count, 11)

    def test_mark_product_featured(self):
        mark_product_featured(self.product, featured=True)
        self.assertTrue(self.product.is_featured)


# ─── Admin Registration Tests ────────────────────────────────────────────────

class AdminRegistrationTests(TestCase):
    def test_models_registered_in_admin(self):
        self.assertIn(Category, admin.site._registry)
        self.assertIn(Brand, admin.site._registry)
        self.assertIn(Product, admin.site._registry)


# ─── URL Routing Tests ───────────────────────────────────────────────────────

class URLRoutingTests(TestCase):
    def test_product_list_url(self):
        url = reverse("products:product_list")
        self.assertEqual(url, "/products/")
        self.assertEqual(resolve(url).func.view_class, ProductListView)

    def test_product_detail_url(self):
        url = reverse("products:product_detail", kwargs={"slug": "test-product"})
        self.assertEqual(url, "/products/test-product/")
        self.assertEqual(resolve(url).func.view_class, ProductDetailView)

    def test_category_list_url(self):
        url = reverse("products:category_list")
        self.assertEqual(url, "/categories/")
        self.assertEqual(resolve(url).func.view_class, CategoryListView)

    def test_category_detail_url(self):
        url = reverse("products:category_detail", kwargs={"slug": "mens-clothing"})
        self.assertEqual(url, "/category/mens-clothing/")
        self.assertEqual(resolve(url).func.view_class, CategoryDetailView)

    def test_brand_list_url(self):
        url = reverse("products:brand_list")
        self.assertEqual(url, "/brands/")
        self.assertEqual(resolve(url).func.view_class, BrandListView)

    def test_brand_detail_url(self):
        url = reverse("products:brand_detail", kwargs={"slug": "house-of-bore"})
        self.assertEqual(url, "/brand/house-of-bore/")
        self.assertEqual(resolve(url).func.view_class, BrandDetailView)


# ─── View Tests ──────────────────────────────────────────────────────────────

class ProductListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Outerwear", slug="outerwear")
        self.brand = Brand.objects.create(name="House Of Bore", slug="house-of-bore")
        self.product = Product.objects.create(
            name="Trench Coat",
            short_description="Premium trench",
            description="Full description",
            category=self.category,
            brand=self.brand,
            price=Decimal("680.00"),
            stock_quantity=10,
            is_active=True
        )

    def test_product_list_returns_200(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertEqual(response.status_code, 200)

    def test_product_list_uses_correct_template(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertTemplateUsed(response, "products/product_list.html")
        self.assertTemplateUsed(response, "base.html")

    def test_product_list_contains_product(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertContains(response, "Trench Coat")
        self.assertContains(response, "$680.00")

    def test_product_list_sorting_price_asc(self):
        Product.objects.create(
            name="Cheap Item",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("50.00"),
            stock_quantity=5,
            is_active=True
        )
        response = self.client.get(reverse("products:product_list") + "?sort=price_asc")
        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        self.assertLessEqual(products[0].price, products[1].price)

    def test_product_list_has_breadcrumbs(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertEqual(response.context["breadcrumbs"][-1]["label"], "Products")

    def test_product_list_excludes_inactive(self):
        inactive = Product.objects.create(
            name="Inactive Product",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("100.00"),
            is_active=False
        )
        response = self.client.get(reverse("products:product_list"))
        self.assertNotContains(response, "Inactive Product")


class ProductDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Shoes", slug="shoes")
        self.brand = Brand.objects.create(name="Modern Essentials", slug="modern-essentials")
        self.product = Product.objects.create(
            name="Chelsea Boots",
            slug="chelsea-boots",
            short_description="Goodyear welt",
            description="Full craftsmanship desc",
            category=self.category,
            brand=self.brand,
            price=Decimal("480.00"),
            compare_at_price=Decimal("520.00"),
            stock_quantity=18,
            is_active=True
        )

    def test_product_detail_returns_200(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.assertEqual(response.status_code, 200)

    def test_product_detail_uses_correct_template(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.assertTemplateUsed(response, "products/product_detail.html")

    def test_product_detail_contains_product_info(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.assertContains(response, "Chelsea Boots")
        self.assertContains(response, "$480.00")
        self.assertContains(response, "Modern Essentials")

    def test_product_detail_shows_sale_badge(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.assertContains(response, "Off")  # "-X% Off" badge

    def test_product_detail_returns_404_for_missing(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "nonexistent"}))
        self.assertEqual(response.status_code, 404)

    def test_product_detail_has_breadcrumbs(self):
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        breadcrumbs = response.context["breadcrumbs"]
        self.assertEqual(breadcrumbs[-1]["label"], "Chelsea Boots")
        self.assertIsNone(breadcrumbs[-1]["url"])

    def test_product_detail_returns_404_for_inactive_product(self):
        inactive = Product.objects.create(
            name="Inactive Boot",
            slug="inactive-boot",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("300.00"),
            is_active=False
        )
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "inactive-boot"}))
        self.assertEqual(response.status_code, 404)

    def test_product_detail_increments_view_count(self):
        initial_count = self.product.view_count
        self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.product.refresh_from_db()
        self.assertEqual(self.product.view_count, initial_count + 1)

    def test_product_detail_renders_new_sections(self):
        p2 = Product.objects.create(
            name="Oxford Shoes",
            slug="oxford-shoes",
            short_description="S",
            description="D",
            category=self.category,
            price=Decimal("450.00"),
            is_active=True
        )
        session = self.client.session
        session["recently_viewed"] = [p2.pk]
        session.save()
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "chelsea-boots"}))
        self.assertContains(response, "Product Specifications")
        self.assertContains(response, "Select Quantity")
        self.assertContains(response, "Secure Payments")
        self.assertContains(response, "Shipping &amp; Returns Policy")
        self.assertContains(response, "Recently Viewed")
        self.assertContains(response, "Add to Bag")



class CategoryListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Men's Collection", slug="mens-collection")

    def test_category_list_returns_200(self):
        response = self.client.get(reverse("products:category_list"))
        self.assertEqual(response.status_code, 200)

    def test_category_list_uses_correct_template(self):
        response = self.client.get(reverse("products:category_list"))
        self.assertTemplateUsed(response, "products/category_list.html")

    def test_category_list_contains_category(self):
        response = self.client.get(reverse("products:category_list"))
        self.assertContains(response, "Men&#x27;s Collection")


class CategoryDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.root = Category.objects.create(name="Men's Clothing", slug="mens-clothing")
        self.child = Category.objects.create(name="Suiting", slug="suiting", parent=self.root)
        self.product = Product.objects.create(
            name="Navy Suit",
            short_description="Tailored suit",
            description="Full desc",
            category=self.root,
            price=Decimal("600.00"),
            stock_quantity=5,
            is_active=True
        )

    def test_category_detail_returns_200(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "mens-clothing"}))
        self.assertEqual(response.status_code, 200)

    def test_category_detail_uses_correct_template(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "mens-clothing"}))
        self.assertTemplateUsed(response, "products/category_detail.html")

    def test_category_detail_contains_product(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "mens-clothing"}))
        self.assertContains(response, "Navy Suit")

    def test_category_detail_shows_child_categories(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "mens-clothing"}))
        self.assertIn(self.child, response.context["child_categories"])

    def test_category_detail_has_breadcrumbs(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "mens-clothing"}))
        breadcrumbs = response.context["breadcrumbs"]
        self.assertEqual(breadcrumbs[-1]["label"], "Men's Clothing")

    def test_category_detail_sorting(self):
        Product.objects.create(
            name="Cheap Shirt",
            short_description="S",
            description="D",
            category=self.root,
            price=Decimal("50.00"),
            stock_quantity=5,
            is_active=True
        )
        response = self.client.get(
            reverse("products:category_detail", kwargs={"slug": "mens-clothing"}) + "?sort=price_asc"
        )
        products = list(response.context["products"])
        self.assertLessEqual(products[0].price, products[1].price)

    def test_category_detail_returns_404_for_missing(self):
        response = self.client.get(reverse("products:category_detail", kwargs={"slug": "nonexistent"}))
        self.assertEqual(response.status_code, 404)


class BrandListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.brand = Brand.objects.create(name="House Of Bore", slug="house-of-bore", is_featured=True)

    def test_brand_list_returns_200(self):
        response = self.client.get(reverse("products:brand_list"))
        self.assertEqual(response.status_code, 200)

    def test_brand_list_uses_correct_template(self):
        response = self.client.get(reverse("products:brand_list"))
        self.assertTemplateUsed(response, "products/brand_list.html")

    def test_brand_list_contains_brand(self):
        response = self.client.get(reverse("products:brand_list"))
        self.assertContains(response, "House Of Bore")


class BrandDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Shoes", slug="shoes")
        self.brand = Brand.objects.create(
            name="Modern Essentials",
            slug="modern-essentials",
            description="Florentine footwear.",
            is_featured=True
        )
        self.product = Product.objects.create(
            name="Suede Loafers",
            short_description="Unlined loafers",
            description="Full desc",
            category=self.category,
            brand=self.brand,
            price=Decimal("390.00"),
            stock_quantity=16,
            is_active=True
        )

    def test_brand_detail_returns_200(self):
        response = self.client.get(reverse("products:brand_detail", kwargs={"slug": "modern-essentials"}))
        self.assertEqual(response.status_code, 200)

    def test_brand_detail_uses_correct_template(self):
        response = self.client.get(reverse("products:brand_detail", kwargs={"slug": "modern-essentials"}))
        self.assertTemplateUsed(response, "products/brand_detail.html")

    def test_brand_detail_contains_product(self):
        response = self.client.get(reverse("products:brand_detail", kwargs={"slug": "modern-essentials"}))
        self.assertContains(response, "Suede Loafers")
        self.assertContains(response, "Modern Essentials")

    def test_brand_detail_has_breadcrumbs(self):
        response = self.client.get(reverse("products:brand_detail", kwargs={"slug": "modern-essentials"}))
        breadcrumbs = response.context["breadcrumbs"]
        self.assertEqual(breadcrumbs[-1]["label"], "Modern Essentials")

    def test_brand_detail_sorting(self):
        Product.objects.create(
            name="Expensive Boot",
            short_description="S",
            description="D",
            category=self.category,
            brand=self.brand,
            price=Decimal("900.00"),
            stock_quantity=5,
            is_active=True
        )
        response = self.client.get(
            reverse("products:brand_detail", kwargs={"slug": "modern-essentials"}) + "?sort=price_desc"
        )
        products = list(response.context["products"])
        self.assertGreaterEqual(products[0].price, products[1].price)

    def test_brand_detail_returns_404_for_missing(self):
        response = self.client.get(reverse("products:brand_detail", kwargs={"slug": "nonexistent"}))
        self.assertEqual(response.status_code, 404)


# ─── Pagination Tests ────────────────────────────────────────────────────────

class PaginationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="All Products", slug="all")
        # Create 15 products to trigger pagination (paginate_by = 12)
        for i in range(15):
            Product.objects.create(
                name=f"Product {i:02d}",
                short_description="Short",
                description="Desc",
                category=self.category,
                price=Decimal("100.00") + Decimal(str(i)),
                stock_quantity=10,
                is_active=True
            )

    def test_first_page_has_12_products(self):
        response = self.client.get(reverse("products:product_list"))
        self.assertEqual(len(response.context["products"]), 12)

    def test_second_page_has_remaining_products(self):
        response = self.client.get(reverse("products:product_list") + "?page=2")
        self.assertEqual(len(response.context["products"]), 3)

    def test_invalid_page_returns_404(self):
        response = self.client.get(reverse("products:product_list") + "?page=999")
        self.assertEqual(response.status_code, 404)

    def test_pagination_preserves_sort(self):
        response = self.client.get(reverse("products:product_list") + "?sort=price_asc&page=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "price_asc")


# ─── Search, Filtering & Discovery Tests ─────────────────────────────────────

class CatalogDiscoveryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.root_cat = Category.objects.create(name="Apparel", slug="apparel")
        self.child_cat = Category.objects.create(name="Jackets", slug="jackets", parent=self.root_cat)
        self.brand = Brand.objects.create(name="North Trail", slug="north-trail")
        self.other_brand = Brand.objects.create(name="Urban Edge", slug="urban-edge")

        self.p1 = Product.objects.create(
            name="Weatherproof Parka Jacket",
            short_description="Heavy winter parka.",
            description="Crafted from waterproof nylon with down insulation.",
            category=self.child_cat,
            brand=self.brand,
            price=Decimal("450.00"),
            compare_at_price=Decimal("550.00"),  # On sale
            stock_quantity=10,
            is_active=True,
            is_featured=True,
            is_new_arrival=True,
            view_count=100
        )
        self.p2 = Product.objects.create(
            name="Lightweight Windbreaker",
            short_description="Summer windbreaker jacket.",
            description="Breathable polyester windbreaker.",
            category=self.child_cat,
            brand=self.other_brand,
            price=Decimal("150.00"),
            stock_quantity=0,  # Out of stock
            is_active=True,
            is_featured=False,
            is_new_arrival=False,
            view_count=50
        )
        self.p3 = Product.objects.create(
            name="Classic Cotton T-Shirt",
            short_description="Basic tee.",
            description="100% organic cotton jersey.",
            category=self.root_cat,
            brand=self.brand,
            price=Decimal("50.00"),
            stock_quantity=25,
            is_active=True,
            is_featured=False,
            is_new_arrival=True,
            view_count=200
        )

    def test_search_products_name_and_description(self):
        # Search by name
        res = search_products("parka")
        self.assertEqual(list(res), [self.p1])

        # Search by short description
        res = search_products("winter")
        self.assertEqual(list(res), [self.p1])

        # Search by description
        res = search_products("polyester")
        self.assertEqual(list(res), [self.p2])

        # Case insensitive partial match
        res = search_products("JACKET")
        self.assertEqual(set(res), {self.p1, self.p2})

    def test_search_products_empty_query(self):
        res = search_products("")
        self.assertEqual(len(res), 3)
        res = search_products(None)
        self.assertEqual(len(res), 3)

    def test_filter_products_by_category_hierarchy(self):
        # Filtering by root category "apparel" should return both root and child category products
        res = filter_products(category_slug="apparel")
        self.assertEqual(set(res), {self.p1, self.p2, self.p3})

        # Filtering by child category "jackets" should only return jackets
        res = filter_products(category_slug="jackets")
        self.assertEqual(set(res), {self.p1, self.p2})

    def test_filter_products_by_brand(self):
        res = filter_products(brand_slug="north-trail")
        self.assertEqual(set(res), {self.p1, self.p3})

        # Invalid brand slug
        res = filter_products(brand_slug="invalid-brand")
        self.assertEqual(len(res), 0)

    def test_filter_products_by_price_range(self):
        res = filter_products(min_price="100", max_price="300")
        self.assertEqual(list(res), [self.p2])

        res = filter_products(min_price="400")
        self.assertEqual(list(res), [self.p1])

        res = filter_products(max_price="60")
        self.assertEqual(list(res), [self.p3])

    def test_filter_products_by_availability(self):
        res = filter_products(availability="in-stock")
        self.assertEqual(set(res), {self.p1, self.p3})

        res = filter_products(availability="out-of-stock")
        self.assertEqual(list(res), [self.p2])

    def test_filter_products_toggles(self):
        res = filter_products(sale="true")
        self.assertEqual(list(res), [self.p1])

        res = filter_products(new="true")
        self.assertEqual(set(res), {self.p1, self.p3})

        res = filter_products(featured="true")
        self.assertEqual(list(res), [self.p1])

    def test_sort_products(self):
        res = sort_products(sort_key="price_asc")
        self.assertEqual(list(res), [self.p3, self.p2, self.p1])

        res = sort_products(sort_key="price_desc")
        self.assertEqual(list(res), [self.p1, self.p2, self.p3])

        res = sort_products(sort_key="popular")
        self.assertEqual(list(res), [self.p3, self.p1, self.p2])

    def test_combined_filtering_and_sorting(self):
        # Brand: North Trail, In Stock, sorted by price ascending
        res = filter_products(brand_slug="north-trail", availability="in-stock")
        res = sort_products(queryset=res, sort_key="price_asc")
        self.assertEqual(list(res), [self.p3, self.p1])

    def test_product_list_view_with_filters_and_seo(self):
        response = self.client.get(reverse("products:product_list") + "?q=jacket&brand=north-trail")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["products"]), [self.p1])
        self.assertTrue(response.context["is_filtered"])
        self.assertEqual(response.context["active_filter_count"], 2)
        self.assertEqual(response.context["page_title"], "Search results for 'jacket'")

        # Test category SEO title
        response = self.client.get(reverse("products:product_list") + "?category=jackets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_title"], "Jackets")

        # Test sale SEO title
        response = self.client.get(reverse("products:product_list") + "?sale=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_title"], "Products on Sale")

    def test_malformed_price_filtering(self):
        """Verify that malformed price strings are ignored without causing 500 errors."""
        response = self.client.get(reverse("products:product_list") + "?min_price=invalid&max_price=$-500")
        self.assertEqual(response.status_code, 200)
        # All 3 active products should be returned since invalid prices are gracefully ignored
        self.assertEqual(len(response.context["products"]), 3)

    def test_inverted_price_filtering(self):
        """Verify that inverted price ranges (min > max) return an empty queryset cleanly."""
        response = self.client.get(reverse("products:product_list") + "?min_price=500&max_price=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 0)

    def test_xss_search_query_handling(self):
        """Verify that XSS payloads in search queries are handled safely without breaking context."""
        xss_payload = "<script>alert(1)</script>"
        response = self.client.get(reverse("products:product_list"), {"q": xss_payload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_q"], xss_payload)
        self.assertEqual(response.context["page_title"], f"Search results for '{xss_payload}'")

    def test_search_query_truncation(self):
        """Verify that oversized search strings (>100 chars) are safely truncated to prevent DoS."""
        long_query = "a" * 500
        response = self.client.get(reverse("products:product_list"), {"q": long_query})
        self.assertEqual(response.status_code, 200)
        # Verify it didn't crash and performed search
        self.assertIn("products", response.context)

    def test_filter_options_caching_and_invalidation(self):
        """Verify that get_filter_options is cached and cleared when catalog data changes."""
        from django.core.cache import cache
        from products.selectors import get_filter_options

        cache.clear()
        self.assertIsNone(cache.get("catalog_filter_options"))

        # First call populates cache
        options1 = get_filter_options()
        self.assertIsNotNone(cache.get("catalog_filter_options"))

        # Modifying a product should trigger invalidate_catalog_cache signal
        self.p1.name = "Updated Parka Name"
        self.p1.save()
        self.assertIsNone(cache.get("catalog_filter_options"))


class ProductVariantTests(TestCase):
    """
    Test suite for Phase 4.3.6: Product Variant & Inventory Foundation.
    Covers options, option values, variants, pricing rules, stock validations, and selectors.
    """
    def setUp(self):
        self.brand = Brand.objects.create(name="Atelier Brand", slug="atelier-brand", is_active=True)
        self.category = Category.objects.create(name="Suits", slug="suits", is_active=True)
        self.product = Product.objects.create(
            name="Tailored Wool Suit",
            slug="tailored-wool-suit",
            brand=self.brand,
            category=self.category,
            price=Decimal("450.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.opt_size = ProductOption.objects.create(name="Size", display_name="Size", sort_order=1)
        self.opt_color = ProductOption.objects.create(name="Color", display_name="Color", sort_order=2)
        
        self.val_40r = ProductOptionValue.objects.create(option=self.opt_size, value="40R", display_order=1)
        self.val_42r = ProductOptionValue.objects.create(option=self.opt_size, value="42R", display_order=2)
        self.val_navy = ProductOptionValue.objects.create(option=self.opt_color, value="Navy", display_order=1)
        self.val_charcoal = ProductOptionValue.objects.create(option=self.opt_color, value="Charcoal", display_order=2)

    def test_variant_creation_and_helpers(self):
        """Verify variant creation, pricing computation, and stock helpers."""
        variant = ProductVariant.objects.create(
            product=self.product,
            sku="TWS-40R-NVY",
            price_override=Decimal("475.00"),
            compare_at_price=Decimal("520.00"),
            stock_quantity=10,
            is_active=True
        )
        ProductVariantOption.objects.create(variant=variant, option_value=self.val_40r)
        ProductVariantOption.objects.create(variant=variant, option_value=self.val_navy)

        self.assertEqual(variant.get_price(), Decimal("475.00"))
        self.assertEqual(variant.get_compare_at_price(), Decimal("520.00"))
        self.assertTrue(variant.is_on_sale())
        self.assertTrue(variant.in_stock())
        self.assertFalse(variant.low_stock())
        self.assertEqual(variant.get_options_summary(), "40R / Navy")

    def test_variant_fallback_pricing(self):
        """Verify variant falls back to parent product pricing when no override set."""
        variant = ProductVariant.objects.create(
            product=self.product,
            sku="TWS-42R-NVY",
            stock_quantity=2,
            is_active=True
        )
        self.assertEqual(variant.get_price(), self.product.price)
        self.assertIsNone(variant.get_compare_at_price())
        self.assertFalse(variant.is_on_sale())
        self.assertTrue(variant.low_stock())

    def test_product_pricing_range_helpers(self):
        """Verify Product.get_price_range and has_multiple_prices when variants exist."""
        v1 = ProductVariant.objects.create(product=self.product, sku="V1", price_override=Decimal("400.00"), is_active=True)
        v2 = ProductVariant.objects.create(product=self.product, sku="V2", price_override=Decimal("550.00"), is_active=True)
        
        self.assertTrue(self.product.has_multiple_prices())
        self.assertEqual(self.product.get_starting_price(), Decimal("400.00"))
        self.assertEqual(self.product.get_price_range(), (Decimal("400.00"), Decimal("550.00")))

    def test_variant_sku_uniqueness_validation(self):
        """Verify SKU uniqueness check across both Product and ProductVariant tables."""
        ProductVariant.objects.create(product=self.product, sku="DUPLICATE-SKU", is_active=True)
        
        # Another variant trying same SKU
        dup_var = ProductVariant(product=self.product, sku="DUPLICATE-SKU", is_active=True)
        with self.assertRaises(ValidationError):
            dup_var.clean()

    def test_variant_selectors(self):
        """Verify selectors correctly fetch variants and validate options."""
        from products.selectors import get_product_variants, get_variant, get_variant_by_options, variant_inventory
        
        v1 = ProductVariant.objects.create(product=self.product, sku="V-40R-NVY", stock_quantity=4, is_active=True)
        ProductVariantOption.objects.create(variant=v1, option_value=self.val_40r)
        ProductVariantOption.objects.create(variant=v1, option_value=self.val_navy)

        # get_product_variants
        variants = get_product_variants(self.product)
        self.assertEqual(list(variants), [v1])

        # get_variant
        self.assertEqual(get_variant(v1.id), v1)

        # get_variant_by_options
        matched = get_variant_by_options(self.product, [self.val_40r.id, self.val_navy.id])
        self.assertEqual(matched, v1)

        # variant_inventory
        self.assertEqual(variant_inventory(v1)["stock_quantity"], 4)


class RecentlyViewedTests(TestCase):
    """Test RecentlyViewedProduct model and tracking service."""
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Shoes", slug="shoes")
        self.p1 = Product.objects.create(name="Boot 1", slug="boot-1", price=Decimal("100"), category=self.category, is_active=True)
        self.p2 = Product.objects.create(name="Boot 2", slug="boot-2", price=Decimal("200"), category=self.category, is_active=True)

    def test_track_and_get_recently_viewed_session(self):
        from products.recently_viewed import track_recently_viewed, get_recently_viewed
        # Simulate request
        response = self.client.get(reverse("products:product_detail", kwargs={"slug": "boot-1"}))
        request = response.wsgi_request
        track_recently_viewed(request, self.p1)
        track_recently_viewed(request, self.p2)

        items = get_recently_viewed(request)
        self.assertEqual(len(items), 2)
        # Most recently tracked item (p2) should be first
        self.assertEqual(items[0], self.p2)
        self.assertEqual(items[1], self.p1)


class RecommendationTests(TestCase):
    """Test heuristic recommendation services."""
    def setUp(self):
        self.category = Category.objects.create(name="Outerwear", slug="outerwear")
        self.brand = Brand.objects.create(name="Atelier", slug="atelier")
        self.p1 = Product.objects.create(name="Coat 1", slug="coat-1", price=Decimal("500"), category=self.category, brand=self.brand, is_active=True)
        self.p2 = Product.objects.create(name="Coat 2", slug="coat-2", price=Decimal("600"), category=self.category, brand=self.brand, is_active=True)
        self.p3 = Product.objects.create(name="Coat 3", slug="coat-3", price=Decimal("700"), category=self.category, is_active=True)

    def test_customers_also_viewed_heuristics(self):
        from products.recommendations import customers_also_viewed, related_products
        recs = customers_also_viewed(self.p1, limit=4)
        self.assertIn(self.p2, recs)
        self.assertNotIn(self.p1, recs)

        related = related_products(self.p1, limit=4)
        self.assertIn(self.p2, related)
        self.assertNotIn(self.p1, related)


class ComparisonTests(TestCase):
    """Test product comparison session service and matrix views."""
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Accessories", slug="accessories")
        self.p1 = Product.objects.create(name="Belt 1", slug="belt-1", price=Decimal("150"), category=self.category, is_active=True)
        self.p2 = Product.objects.create(name="Belt 2", slug="belt-2", price=Decimal("180"), category=self.category, is_active=True)

    def test_toggle_comparison(self):
        # Add to comparison
        url1 = reverse("products:toggle_comparison", kwargs={"product_id": self.p1.id})
        response = self.client.post(url1)
        self.assertRedirects(response, reverse("products:comparison_matrix"))
        self.assertEqual(self.client.session.get("compare_list"), [self.p1.id])

        # Toggle again removes it
        response = self.client.post(url1)
        self.assertEqual(self.client.session.get("compare_list"), [])

    def test_comparison_matrix_view(self):
        # Add two products
        self.client.post(reverse("products:toggle_comparison", kwargs={"product_id": self.p1.id}))
        self.client.post(reverse("products:toggle_comparison", kwargs={"product_id": self.p2.id}))

        response = self.client.get(reverse("products:comparison_matrix"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Belt 1")
        self.assertContains(response, "Belt 2")

    def test_clear_comparison(self):
        self.client.post(reverse("products:toggle_comparison", kwargs={"product_id": self.p1.id}))
        self.client.post(reverse("products:clear_comparison"))
        self.assertEqual(self.client.session.get("compare_list", []), [])




