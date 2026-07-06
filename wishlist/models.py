# wishlist/models.py
"""
wishlist/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for user wishlists and saved products.

Enforces business rules:
- One wishlist per user (OneToOneField).
- A product can appear only once in a wishlist (UniqueConstraint).
- Deleting a wishlist removes all items (CASCADE).
- Deleting a product removes it from wishlists (CASCADE).
- Automatic cache invalidation via signals when items are added or removed.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from products.models import Product


class WishlistQuerySet(models.QuerySet):
    """
    Custom QuerySet for Wishlist model providing optimized querying methods.
    """

    def with_products(self) -> "WishlistQuerySet":
        """
        Prefetches related WishlistItems and their associated Products, categories,
        brands, and images to eliminate N+1 query bottlenecks.
        """
        return self.prefetch_related(
            "items__product__category",
            "items__product__brand",
            "items__product__images",
        )

    def for_user(self, user: Any) -> "WishlistQuerySet":
        """
        Filters wishlists for a specific user.
        """
        if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
            return self.none()
        return self.filter(user=user)


class WishlistManager(models.Manager):
    """
    Custom Manager for Wishlist model exposing optimized QuerySet methods.
    """

    def get_queryset(self) -> WishlistQuerySet:
        return WishlistQuerySet(self.model, using=self._db)

    def with_products(self) -> WishlistQuerySet:
        return self.get_queryset().with_products()

    def for_user(self, user: Any) -> WishlistQuerySet:
        return self.get_queryset().for_user(user)


class Wishlist(models.Model):
    """
    User wishlist containing saved products for future purchase consideration.
    
    Attributes:
        user: The authenticated customer who owns this wishlist.
        created_at: Timestamp when the wishlist was created.
        updated_at: Timestamp when the wishlist was last modified.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        verbose_name=_("User"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
    )

    objects = WishlistManager()

    class Meta:
        verbose_name = _("Wishlist")
        verbose_name_plural = _("Wishlists")

    def __str__(self) -> str:
        return f"Wishlist for {self.user}"

    # ─── Helper Business Methods ──────────────────────────────────────────────
    def add_product(self, product: Product) -> "WishlistItem":
        """
        Adds a product to this wishlist or returns the existing item if already saved.
        """
        item, created = self.items.get_or_create(product=product)
        if created:
            self.save(update_fields=["updated_at"])
        return item

    def remove_product(self, product: Product) -> bool:
        """
        Removes a product from this wishlist. Returns True if an item was deleted.
        """
        deleted_count, _ = self.items.filter(product=product).delete()
        if deleted_count > 0:
            self.save(update_fields=["updated_at"])
            return True
        return False

    def contains(self, product: Product) -> bool:
        """
        Returns True if the specified product is in this wishlist.
        """
        if not product or not product.pk:
            return False
        return self.items.filter(product=product).exists()

    def item_count(self) -> int:
        """
        Returns the total number of products saved in this wishlist.
        """
        return self.items.count()

    def clear(self) -> int:
        """
        Removes all products from this wishlist and returns the count deleted.
        """
        deleted_count, _ = self.items.all().delete()
        if deleted_count > 0:
            self.save(update_fields=["updated_at"])
        return deleted_count


class WishlistItem(models.Model):
    """
    An individual product saved inside a customer's wishlist.
    
    Attributes:
        wishlist: The parent wishlist.
        product: The product saved.
        added_at: Timestamp when this item was added.
    """

    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Wishlist"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
        verbose_name=_("Product"),
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Added At"),
    )

    class Meta:
        verbose_name = _("Wishlist Item")
        verbose_name_plural = _("Wishlist Items")
        ordering = ["-added_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wishlist", "product"],
                name="unique_wishlist_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} in {self.wishlist}"


# ─── Cache Invalidation Signals ──────────────────────────────────────────────
@receiver([post_save, post_delete], sender=WishlistItem)
def invalidate_wishlist_cache_on_item(sender, instance: WishlistItem, **kwargs) -> None:
    """
    Clears cached wishlist product IDs when an item is added or deleted.
    """
    cache.delete(f"user_wishlist_ids_{instance.wishlist.user_id}")


@receiver(post_delete, sender=Wishlist)
def invalidate_wishlist_cache_on_wishlist(sender, instance: Wishlist, **kwargs) -> None:
    """
    Clears cached wishlist product IDs when a wishlist is deleted.
    """
    cache.delete(f"user_wishlist_ids_{instance.user_id}")
