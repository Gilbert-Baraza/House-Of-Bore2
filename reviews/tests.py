# reviews/tests.py
"""
reviews/tests.py
──────────────────────────────────────────────────────────────────────────────
Comprehensive automated test suite for product reviews and ratings.

Covers:
1. Model integrity (UniqueConstraint, CheckConstraint, validators).
2. Selectors & single-query aggregations (get_review_summary, caching/invalidation).
3. Forms & duplicate review prevention in clean().
4. Views & strict permissions (LoginRequiredMixin, UserPassesTestMixin).
5. Django Admin bulk moderation actions (approve / reject).
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Brand, Category, Product
from reviews.forms import ReviewForm
from reviews.models import Review
from reviews.selectors import get_product_reviews, get_review_summary, get_user_review

User = get_user_model()


class ReviewBaseTestCase(TestCase):
    """
    Shared setup creating test users, categories, brands, and products.
    """
    def setUp(self):
        cache.clear()
        self.user1 = User.objects.create_user(
            email="alice@example.com",
            password="testpassword123",
            first_name="Alice",
            last_name="Smith",
        )
        self.user2 = User.objects.create_user(
            email="bob@example.com",
            password="testpassword123",
            first_name="Bob",
            last_name="Jones",
        )
        self.staff_user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpassword123",
            first_name="Admin",
            last_name="User",
        )

        self.category = Category.objects.create(
            name="Outerwear",
            slug="outerwear",
            is_active=True,
        )
        self.brand = Brand.objects.create(
            name="House of Bore",
            slug="house-of-bore",
            is_active=True,
        )
        self.product = Product.objects.create(
            category=self.category,
            brand=self.brand,
            name="Bespoke Wool Trench Coat",
            slug="bespoke-wool-trench-coat",
            short_description="A tailored wool coat.",
            description="Detailed description of the bespoke coat.",
            price=Decimal("1250.00"),
            stock_quantity=10,
            is_active=True,
        )


class ReviewModelTests(ReviewBaseTestCase):
    """
    Tests for Review model constraints, string representation, and URLs.
    """
    def test_create_valid_review(self):
        review = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="Exceptional Craftsmanship",
            comment="The wool is incredible and the fit is perfect.",
        )
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.is_approved)
        self.assertIn("5★ review by", str(review))
        self.assertEqual(review.get_absolute_url(), f"{self.product.get_absolute_url()}#reviews")

    def test_unique_constraint_one_review_per_user_per_product(self):
        Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="First Review",
            comment="Great coat.",
        )
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                product=self.product,
                user=self.user1,
                rating=4,
                title="Second Review",
                comment="Still good.",
            )

    def test_check_constraint_rating_range(self):
        # Test rating < 1
        with self.assertRaises((IntegrityError, ValidationError)):
            review = Review(
                product=self.product,
                user=self.user1,
                rating=0,
                title="Bad Rating",
                comment="Zero stars.",
            )
            review.full_clean()
            review.save()

        # Test rating > 5
        with self.assertRaises((IntegrityError, ValidationError)):
            review = Review(
                product=self.product,
                user=self.user2,
                rating=6,
                title="Too High",
                comment="Six stars.",
            )
            review.full_clean()
            review.save()


class ReviewSelectorTests(ReviewBaseTestCase):
    """
    Tests for database selectors and single-query aggregations.
    """
    def setUp(self):
        super().setUp()
        self.rev1 = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="Amazing",
            comment="5 star quality.",
            is_approved=True,
        )
        self.rev2 = Review.objects.create(
            product=self.product,
            user=self.user2,
            rating=3,
            title="Average",
            comment="3 star quality.",
            is_approved=True,
        )

    def test_get_product_reviews_approved_only(self):
        # Create an unapproved review by staff
        Review.objects.create(
            product=self.product,
            user=self.staff_user,
            rating=1,
            title="Hidden",
            comment="Unapproved comment.",
            is_approved=False,
        )
        approved_qs = get_product_reviews(self.product, approved_only=True)
        self.assertEqual(approved_qs.count(), 2)

        all_qs = get_product_reviews(self.product, approved_only=False)
        self.assertEqual(all_qs.count(), 3)

    def test_get_review_summary_single_query_aggregation(self):
        summary = get_review_summary(self.product)
        self.assertEqual(summary["review_count"], 2)
        # Avg of 5 and 3 is 4.0
        self.assertEqual(summary["average_rating"], Decimal("4.0"))
        self.assertEqual(summary["five_star_count"], 1)
        self.assertEqual(summary["three_star_count"], 1)
        self.assertEqual(summary["rating_breakdown"][5]["percentage"], 50)
        self.assertEqual(summary["rating_breakdown"][3]["percentage"], 50)

    def test_cache_invalidation_on_review_save_and_delete(self):
        # Prime cache
        summary_before = get_review_summary(self.product)
        self.assertEqual(summary_before["review_count"], 2)

        # Add new review
        Review.objects.create(
            product=self.product,
            user=self.staff_user,
            rating=4,
            title="Good",
            comment="4 star quality.",
            is_approved=True,
        )
        # Fetch summary again; cache should be invalidated by signal
        summary_after_add = get_review_summary(self.product)
        self.assertEqual(summary_after_add["review_count"], 3)
        # Avg of 5, 3, 4 is 4.0
        self.assertEqual(summary_after_add["average_rating"], Decimal("4.0"))

        # Delete review
        self.rev2.delete()
        summary_after_delete = get_review_summary(self.product)
        self.assertEqual(summary_after_delete["review_count"], 2)
        # Avg of 5 and 4 is 4.5
        self.assertEqual(summary_after_delete["average_rating"], Decimal("4.5"))

    def test_get_user_review(self):
        rev = get_user_review(self.product, self.user1)
        self.assertEqual(rev, self.rev1)

        rev_none = get_user_review(self.product, self.staff_user)
        self.assertIsNone(rev_none)


class ReviewFormTests(ReviewBaseTestCase):
    """
    Tests for ReviewForm validation and duplicate checking.
    """
    def test_valid_form(self):
        form = ReviewForm(data={
            "rating": "5",
            "title": "Superb coat",
            "comment": "Exceeded all expectations.",
        })
        self.assertTrue(form.is_valid())

    def test_invalid_rating(self):
        form = ReviewForm(data={
            "rating": "6",
            "title": "Invalid",
            "comment": "Out of range.",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("rating", form.errors)

    def test_duplicate_review_check_in_clean(self):
        # Alice creates first review
        Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="First",
            comment="First review.",
        )
        # Alice tries submitting another via form
        form = ReviewForm(
            data={
                "rating": "4",
                "title": "Second",
                "comment": "Second review.",
            },
            product=self.product,
            user=self.user1,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("You have already submitted a review for this product.", str(form.errors))


class ReviewViewTests(ReviewBaseTestCase):
    """
    Tests for review creation, updating, deletion, and strict permissions.
    """
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_create_review_unauthenticated_redirects_to_login(self):
        url = reverse("reviews:create_review", args=[self.product.slug])
        response = self.client.post(url, {
            "rating": "5",
            "title": "Great",
            "comment": "Awesome coat.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_create_review_authenticated_success(self):
        self.client.login(email="alice@example.com", password="testpassword123")
        url = reverse("reviews:create_review", args=[self.product.slug])
        response = self.client.post(url, {
            "rating": "5",
            "title": "Masterpiece",
            "comment": "The finest trench coat I have ever owned.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.first()
        self.assertEqual(review.user, self.user1)
        self.assertEqual(review.product, self.product)
        self.assertEqual(response.url, review.get_absolute_url())

    def test_create_review_duplicate_redirects_to_update_view(self):
        rev = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="Existing",
            comment="Existing comment.",
        )
        self.client.login(email="alice@example.com", password="testpassword123")
        url = reverse("reviews:create_review", args=[self.product.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("reviews:update_review", args=[rev.pk]))

    def test_update_review_permission(self):
        rev = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=4,
            title="Good",
            comment="Initial comment.",
        )
        # Bob tries to edit Alice's review -> 403 Forbidden
        self.client.login(email="bob@example.com", password="testpassword123")
        url = reverse("reviews:update_review", args=[rev.pk])
        response = self.client.post(url, {
            "rating": "1",
            "title": "Hacked",
            "comment": "Hacked comment.",
        })
        self.assertEqual(response.status_code, 403)
        rev.refresh_from_db()
        self.assertEqual(rev.title, "Good")

        # Alice edits her own review -> Success
        self.client.login(email="alice@example.com", password="testpassword123")
        response = self.client.post(url, {
            "rating": "5",
            "title": "Updated to 5 stars",
            "comment": "Even better after wearing it.",
        })
        self.assertEqual(response.status_code, 302)
        rev.refresh_from_db()
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.title, "Updated to 5 stars")

    def test_delete_review_permission(self):
        rev = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=4,
            title="Good",
            comment="To be deleted.",
        )
        # Bob tries to delete Alice's review -> 403 Forbidden
        self.client.login(email="bob@example.com", password="testpassword123")
        url = reverse("reviews:delete_review", args=[rev.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Review.objects.count(), 1)

        # Alice deletes her own review -> Success
        self.client.login(email="alice@example.com", password="testpassword123")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.count(), 0)


class ReviewAdminTests(ReviewBaseTestCase):
    """
    Tests for Django Admin bulk moderation actions and cache invalidation.
    """
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(email="admin@example.com", password="adminpassword123")
        self.rev = Review.objects.create(
            product=self.product,
            user=self.user1,
            rating=5,
            title="Pending Review",
            comment="Awaiting moderation.",
            is_approved=False,
        )

    def test_admin_bulk_approve_and_cache_invalidation(self):
        # Check initial summary (no approved reviews)
        summary_before = get_review_summary(self.product)
        self.assertEqual(summary_before["review_count"], 0)

        # Trigger admin action
        url = reverse("admin:reviews_review_changelist")
        response = self.client.post(url, {
            "action": "approve_reviews",
            "_selected_action": [str(self.rev.pk)],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.rev.refresh_from_db()
        self.assertTrue(self.rev.is_approved)

        # Check summary cache was cleared and updated
        summary_after = get_review_summary(self.product)
        self.assertEqual(summary_after["review_count"], 1)

    def test_admin_bulk_reject_and_cache_invalidation(self):
        self.rev.is_approved = True
        self.rev.save()
        summary_before = get_review_summary(self.product)
        self.assertEqual(summary_before["review_count"], 1)

        # Trigger admin action to reject
        url = reverse("admin:reviews_review_changelist")
        response = self.client.post(url, {
            "action": "reject_reviews",
            "_selected_action": [str(self.rev.pk)],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.rev.refresh_from_db()
        self.assertFalse(self.rev.is_approved)

        # Check summary cache was cleared and updated
        summary_after = get_review_summary(self.product)
        self.assertEqual(summary_after["review_count"], 0)
