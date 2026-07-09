# cart/models.py
"""
cart/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for the hybrid shopping cart system.

Supports both guest users (session-based) and authenticated customers (user-based).
Enforces uniqueness rules, stock integrity, and immutable price snapshots.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Cart(models.Model):
    """
    Shopping cart container model.
    
    Can belong to an authenticated customer (user) or an anonymous guest (session_key).
    Enforces that an authenticated user has at most one active cart, and a guest session
    has at most one active cart.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
        help_text="Associated customer account for persistent carts."
    )
    session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text="Django session key for anonymous guest carts."
    )
    coupon = models.ForeignKey(
        "pricing.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carts",
        help_text="Applied discount coupon."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "shopping cart"
        verbose_name_plural = "shopping carts"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(user__isnull=False),
                name="unique_user_cart"
            ),
            models.UniqueConstraint(
                fields=["session_key"],
                condition=Q(session_key__isnull=False),
                name="unique_session_cart"
            ),
        ]

    def __str__(self) -> str:
        if self.user:
            return f"Cart #{self.pk} — User: {self.user.email}"
        return f"Cart #{self.pk} — Guest: {str(self.session_key)[:8]}"

    def clean(self) -> None:
        """
        Validate that the cart is associated with at least a user or a session key.
        """
        super().clean()
        if not self.user and not self.session_key:
            raise ValidationError(
                "A shopping cart must be associated with either an authenticated user or a guest session key."
            )

    def subtotal(self) -> Decimal:
        """
        Calculate the total monetary value of all items in the cart via pricing engine.
        """
        from pricing.services import calculate_subtotal
        return calculate_subtotal(self)

    def item_count(self) -> int:
        """
        Calculate the total number of physical units across all line items.
        """
        return sum(item.quantity for item in self.items.all())

    def save(self, *args: Any, **kwargs: Any) -> None:
        if hasattr(self, "_cached_breakdown"):
            delattr(self, "_cached_breakdown")
        super().save(*args, **kwargs)


class CartItem(models.Model):
    """
    Individual line item within a shopping cart.
    
    References a Product, stores the requested quantity, and retains an immutable
    snapshot of the product's selling price at the time of addition/modification.
    """
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Parent shopping cart."
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        help_text="Selected catalog product."
    )
    product_variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart_items",
        help_text="Selected product variant."
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of units requested."
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Snapshot of the unit selling price at the time of addition or update."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "cart item"
        verbose_name_plural = "cart items"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "product_variant"],
                condition=Q(product_variant__isnull=False),
                name="unique_cart_product_variant"
            ),
            models.UniqueConstraint(
                fields=["cart", "product"],
                condition=Q(product_variant__isnull=True),
                name="unique_cart_product_no_variant"
            )
        ]

    def __str__(self) -> str:
        name = self.product.name
        if self.product_variant:
            name += f" ({self.product_variant.get_options_summary()})"
        return f"{self.quantity}x {name} in Cart #{self.cart_id}"

    def clean(self) -> None:
        """
        Validate quantity, price integrity, and variant ownership.
        """
        super().clean()
        if self.quantity < 1:
            raise ValidationError({"quantity": "Cart item quantity must be at least 1."})
        if self.unit_price is not None and self.unit_price < Decimal("0.00"):
            raise ValidationError({"unit_price": "Unit price cannot be negative."})
        if self.product_variant is not None and getattr(self.product_variant, "product_id", None) != self.product_id:
            raise ValidationError({"product_variant": "Selected variant does not belong to the selected product."})

    def subtotal(self) -> Decimal:
        """
        Calculate the monetary subtotal for this specific line item.
        """
        return Decimal(self.quantity) * self.unit_price

    def save(self, *args: Any, **kwargs: Any) -> None:
        if hasattr(self.cart, "_cached_breakdown"):
            delattr(self.cart, "_cached_breakdown")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        if hasattr(self.cart, "_cached_breakdown"):
            delattr(self.cart, "_cached_breakdown")
        return super().delete(*args, **kwargs)
