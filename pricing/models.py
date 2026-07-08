# pricing/models.py
"""
pricing/models.py
──────────────────────────────────────────────────────────────────────────────
Database models for coupons and promotional discounts.
Acts as the authoritative schema for validity windows, usage caps, discount
types (fixed/percentage), and product/category scoping.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from typing import Any, Tuple, Dict
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    """
    Discount coupon code applicable at cart or checkout level.
    
    Supports percentage-based or fixed monetary discounts, minimum order thresholds,
    maximum discount caps, validity windows, and total usage limits.
    """
    DISCOUNT_TYPE_CHOICES = [
        ("percentage", "Percentage"),
        ("fixed", "Fixed Amount"),
    ]

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique promo code (case-insensitive in validation)."
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Internal or customer-facing description of the coupon."
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default="percentage",
        help_text="Percentage off (0-100) or fixed amount off ($)."
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Numerical discount amount or percentage rate."
    )
    minimum_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Minimum cart subtotal required to apply this coupon."
    )
    maximum_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum monetary discount allowed (useful for capping percentage discounts)."
    )
    active = models.BooleanField(
        default=True,
        help_text="Master switch to enable or disable this coupon."
    )
    starts_at = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time when the coupon becomes valid."
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time when the coupon expires (null for no expiration)."
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of times this coupon can be applied across the platform."
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text="Current number of times this coupon has been applied/completed."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "discount coupon"
        verbose_name_plural = "discount coupons"

    def __str__(self) -> str:
        return f"Coupon [{self.code.upper()}] — {self.get_discount_type_display()}: {self.discount_value}"

    def clean(self) -> None:
        """
        Validate monetary and date rules.
        """
        super().clean()
        if self.discount_value is not None and self.discount_value < Decimal("0.00"):
            raise ValidationError({"discount_value": "Discount value cannot be negative."})
        if self.discount_type == "percentage" and self.discount_value is not None and self.discount_value > Decimal("100.00"):
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100%."})
        if self.minimum_order_amount is not None and self.minimum_order_amount < Decimal("0.00"):
            raise ValidationError({"minimum_order_amount": "Minimum order amount cannot be negative."})
        if self.maximum_discount_amount is not None and self.maximum_discount_amount < Decimal("0.00"):
            raise ValidationError({"maximum_discount_amount": "Maximum discount amount cannot be negative."})
        if self.starts_at and self.expires_at and self.expires_at < self.starts_at:
            raise ValidationError({"expires_at": "Expiration timestamp must be after start timestamp."})

    def is_valid_now(self) -> bool:
        """
        Check whether the coupon is active, within its validity window, and within usage limits.
        """
        if not self.active:
            return False
        now = timezone.now()
        if now < self.starts_at:
            return False
        if self.expires_at and now > self.expires_at:
            return False
        if self.usage_limit is not None and self.usage_count >= self.usage_limit:
            return False
        return True

    def is_valid_for_subtotal(self, subtotal: Decimal) -> bool:
        """
        Check whether the coupon is currently valid and meets the minimum order subtotal requirement.
        """
        if not self.is_valid_now():
            return False
        if subtotal < self.minimum_order_amount:
            return False
        return True

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete("pricing:active_coupons")
        if self.code:
            cache.delete(f"pricing:coupon:{self.code.upper()}")

    def delete(self, *args: Any, **kwargs: Any) -> Tuple[int, Dict[str, int]]:
        from django.core.cache import cache
        cache.delete("pricing:active_coupons")
        if self.code:
            cache.delete(f"pricing:coupon:{self.code.upper()}")
        return super().delete(*args, **kwargs)


class Promotion(models.Model):
    """
    Automated promotional rule applicable across store-wide items, specific categories,
    specific products, or future buy-x-get-y strategies.
    
    Higher priority numbers are evaluated first when rules interact.
    """
    PROMOTION_TYPE_CHOICES = [
        ("store_wide", "Store-Wide Sale"),
        ("category", "Category Discount"),
        ("product", "Product Discount"),
        ("buy_x_get_y", "Buy X Get Y (Prepared Architecture)"),
    ]
    DISCOUNT_TYPE_CHOICES = [
        ("percentage", "Percentage"),
        ("fixed", "Fixed Amount"),
    ]

    name = models.CharField(
        max_length=150,
        help_text="Public or internal promotion title (e.g., Summer Luxury Sale)."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Detailed rules or customer-facing description."
    )
    promotion_type = models.CharField(
        max_length=30,
        choices=PROMOTION_TYPE_CHOICES,
        default="store_wide",
        help_text="Strategy type governing how items match this promotion."
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default="percentage",
        help_text="Percentage off or fixed monetary reduction per applicable unit."
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Numerical discount value."
    )
    active = models.BooleanField(
        default=True,
        help_text="Master switch to activate or deactivate this promotion."
    )
    starts_at = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time when the promotion begins."
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time when the promotion ends (null for ongoing)."
    )
    priority = models.PositiveIntegerField(
        default=10,
        help_text="Evaluation priority (higher number evaluated/applied first)."
    )
    categories = models.ManyToManyField(
        "products.Category",
        blank=True,
        related_name="promotions",
        help_text="Categories eligible for this promotion (if Category Discount)."
    )
    products = models.ManyToManyField(
        "products.Product",
        blank=True,
        related_name="promotions",
        help_text="Specific products eligible for this promotion (if Product Discount)."
    )
    rules_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Flexible JSON schema for advanced rules (e.g., Buy X Get Y thresholds)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "-created_at"]
        verbose_name = "promotion"
        verbose_name_plural = "promotions"

    def __str__(self) -> str:
        return f"Promo [{self.name}] ({self.get_promotion_type_display()}) — {self.discount_value}"

    def clean(self) -> None:
        """
        Validate promotional rules.
        """
        super().clean()
        if self.discount_value is not None and self.discount_value < Decimal("0.00"):
            raise ValidationError({"discount_value": "Discount value cannot be negative."})
        if self.discount_type == "percentage" and self.discount_value is not None and self.discount_value > Decimal("100.00"):
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100%."})
        if self.starts_at and self.expires_at and self.expires_at < self.starts_at:
            raise ValidationError({"expires_at": "Expiration timestamp must be after start timestamp."})

    def is_valid_now(self) -> bool:
        """
        Check whether the promotion is active and within its validity timeframe.
        """
        if not self.active:
            return False
        now = timezone.now()
        if now < self.starts_at:
            return False
        if self.expires_at and now > self.expires_at:
            return False
        return True

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete("pricing:active_promotions")

    def delete(self, *args: Any, **kwargs: Any) -> Tuple[int, Dict[str, int]]:
        from django.core.cache import cache
        cache.delete("pricing:active_promotions")
        return super().delete(*args, **kwargs)


class CouponUsageLog(models.Model):
    """
    Immutable audit log recording every successful coupon redemption upon order creation.
    Provides complete financial traceability and usage history.
    """
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.CASCADE,
        related_name="usage_logs",
        help_text="Coupon redeemed in this transaction."
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
        help_text="Customer account that redeemed the coupon (or None for guest checkout)."
    )
    order_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Order ID/number generated at checkout completion."
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Exact monetary discount granted by this coupon on the order."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the coupon redemption was logged."
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "coupon usage log"
        verbose_name_plural = "coupon usage logs"

    def __str__(self) -> str:
        return f"Log [{self.coupon.code}] order {self.order_id or 'N/A'} (-${self.discount_amount})"

