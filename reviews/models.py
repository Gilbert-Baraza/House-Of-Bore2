# reviews/models.py
"""
reviews/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for product reviews and ratings.

Enforces critical business rules at the database level:
- One review per user per product (UniqueConstraint).
- Rating must be an integer between 1 and 5 (CheckConstraint & Validators).
- Moderation support via is_approved flag.
──────────────────────────────────────────────────────────────────────────────
"""

from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from products.models import Product


class Review(models.Model):
    """
    Customer review and rating for a specific product.
    
    Attributes:
        product: The product being reviewed.
        user: The authenticated user who authored the review.
        rating: Score from 1 to 5 stars.
        title: Short summary headline of the review.
        comment: Detailed feedback text.
        is_approved: Moderation flag (default=True for immediate feedback,
                     can be rejected by staff in Admin).
        created_at: Timestamp when review was first posted.
        updated_at: Timestamp when review was last edited.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("Product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("Author"),
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name=_("Rating (1-5 Stars)"),
        help_text=_("Select a rating from 1 to 5 stars."),
    )
    title = models.CharField(
        max_length=150,
        verbose_name=_("Review Title"),
        help_text=_("Short summary headline for your review."),
    )
    comment = models.TextField(
        verbose_name=_("Detailed Review"),
        help_text=_("Share your experience regarding fabric, fit, and craftsmanship."),
    )
    is_approved = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Approved"),
        help_text=_("Designates whether this review is publicly visible on the product page."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
    )

    class Meta:
        verbose_name = _("Product Review")
        verbose_name_plural = _("Product Reviews")
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["product", "is_approved", "-created_at"],
                name="rev_prod_appr_created_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="unique_user_product_review",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="valid_rating_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ review by {self.user} on {self.product.name}"

    @property
    def is_verified_buyer(self) -> bool:
        """
        Returns whether the author has a verified purchase order for this product.
        TODO (Phase 3+): Connect to Order and OrderItem models once implemented.
        Currently defaults to True for demonstration purposes.
        """
        return True

    def get_absolute_url(self) -> str:
        """Redirects back to the product detail page anchored to the review section."""
        return f"{self.product.get_absolute_url()}#reviews"


# ─── Cache Invalidation Signals ──────────────────────────────────────────────
@receiver([post_save, post_delete], sender=Review)
def invalidate_review_summary_cache(sender, instance, **kwargs) -> None:
    """
    Clears cached review statistics for the product whenever a review is
    created, edited, moderated, or deleted.
    """
    cache.delete(f"product_review_summary_{instance.product_id}")
