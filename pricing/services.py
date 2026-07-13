# pricing/services.py
"""
pricing/services.py
──────────────────────────────────────────────────────────────────────────────
Centralized pricing engine and calculation operations.
Acts as the authoritative single source of truth for all monetary formulas
across products, shopping bag, discount promotions, coupons, shipping, and taxes.

All calculations use Python Decimal with ROUND_HALF_UP quantization to 2 places.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, Tuple, List, Iterable
from django.core.exceptions import ValidationError
from django.db import transaction
from pricing.models import Coupon, Promotion, CouponUsageLog
from pricing.selectors import get_applicable_promotions, coupon_by_code
from settings.selectors import get_shipping_settings, get_currency_settings


def quantize_money(amount: Decimal) -> Decimal:
    """
    Ensure all monetary computations maintain exactly two decimal places using standard
    financial rounding (`ROUND_HALF_UP`).
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_subtotal(cart: Optional[Any]) -> Decimal:
    """
    Calculate the total monetary subtotal of all items currently inside the shopping bag.
    Can accept a Cart instance or None.
    """
    if not cart:
        return Decimal("0.00")
    
    total = Decimal("0.00")
    # If cart has items manager or iterable
    items = getattr(cart, "items", None)
    if items is not None and hasattr(items, "all"):
        for item in items.all():
            qty = Decimal(str(item.quantity))
            price = Decimal(str(item.unit_price))
            total += qty * price
    return quantize_money(total)


def calculate_discount(
    subtotal: Decimal,
    cart: Optional[Any] = None,
    promotions: Optional[Iterable[Promotion]] = None
) -> Tuple[Decimal, List[str]]:
    """
    Evaluate active promotions against the cart subtotal and individual items.
    Returns the total promotional discount (Decimal) and a list of applied promotion titles.
    """
    if subtotal <= Decimal("0.00"):
        return Decimal("0.00"), []

    if promotions is None:
        promotions = get_applicable_promotions()

    total_discount = Decimal("0.00")
    applied_descriptions: List[str] = []

    # Get cart items pre-loaded or list if cart provided
    items = []
    if cart and hasattr(cart, "items") and hasattr(cart.items, "all"):
        items = list(cart.items.all())

    for prom in promotions:
        promo_discount = Decimal("0.00")

        if prom.promotion_type == "store_wide":
            if prom.discount_type == "percentage":
                promo_discount = subtotal * (prom.discount_value / Decimal("100.00"))
            elif prom.discount_type == "fixed":
                promo_discount = min(subtotal - total_discount, prom.discount_value)

        elif prom.promotion_type == "category" and items:
            # Check matching categories
            eligible_categories = set(prom.categories.values_list("id", flat=True))
            for item in items:
                if hasattr(item, "product") and item.product.category_id in eligible_categories:
                    item_subtotal = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
                    if prom.discount_type == "percentage":
                        promo_discount += item_subtotal * (prom.discount_value / Decimal("100.00"))
                    elif prom.discount_type == "fixed":
                        promo_discount += min(item_subtotal, prom.discount_value * Decimal(str(item.quantity)))

        elif prom.promotion_type == "product" and items:
            # Check matching products
            eligible_products = set(prom.products.values_list("id", flat=True))
            for item in items:
                if hasattr(item, "product") and item.product_id in eligible_products:
                    item_subtotal = Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
                    if prom.discount_type == "percentage":
                        promo_discount += item_subtotal * (prom.discount_value / Decimal("100.00"))
                    elif prom.discount_type == "fixed":
                        promo_discount += min(item_subtotal, prom.discount_value * Decimal(str(item.quantity)))

        elif prom.promotion_type == "buy_x_get_y" and items and prom.rules_config:
            # Prepared architecture: check buy_qty / get_qty rules
            buy_qty = prom.rules_config.get("buy_qty", 0)
            get_qty = prom.rules_config.get("get_qty", 0)
            pct = Decimal(str(prom.rules_config.get("discount_pct", 100))) / Decimal("100.00")
            if buy_qty > 0 and get_qty > 0:
                eligible_products = set(prom.products.values_list("id", flat=True)) if prom.products.exists() else None
                for item in items:
                    if eligible_products is None or (hasattr(item, "product") and item.product_id in eligible_products):
                        total_item_qty = item.quantity
                        group_size = buy_qty + get_qty
                        groups = total_item_qty // group_size
                        if groups > 0:
                            free_units = Decimal(str(groups * get_qty))
                            promo_discount += free_units * Decimal(str(item.unit_price)) * pct

        # Quantize and cap at remaining subtotal
        promo_discount = quantize_money(promo_discount)
        if promo_discount > Decimal("0.00"):
            available = max(Decimal("0.00"), subtotal - total_discount)
            promo_discount = min(promo_discount, available)
            if promo_discount > Decimal("0.00"):
                total_discount += promo_discount
                applied_descriptions.append(f"{prom.name} (-${promo_discount:.2f})")

        if total_discount >= subtotal:
            total_discount = subtotal
            break

    return quantize_money(total_discount), applied_descriptions


def calculate_coupon(subtotal_after_discount: Decimal, coupon: Optional[Coupon]) -> Decimal:
    """
    Calculate the monetary discount granted by an applied coupon against the remaining subtotal.
    Ensures minimum threshold checks and maximum discount caps.
    """
    if not coupon or subtotal_after_discount <= Decimal("0.00"):
        return Decimal("0.00")

    if not coupon.is_valid_for_subtotal(subtotal_after_discount):
        return Decimal("0.00")

    discount = Decimal("0.00")
    if coupon.discount_type == "percentage":
        discount = subtotal_after_discount * (coupon.discount_value / Decimal("100.00"))
        if coupon.maximum_discount_amount is not None:
            discount = min(discount, coupon.maximum_discount_amount)
    elif coupon.discount_type == "fixed":
        discount = min(subtotal_after_discount, coupon.discount_value)

    return quantize_money(discount)


def calculate_shipping(
    subtotal_after_discounts: Decimal,
    shipping_address: Optional[Any] = None,
    shipping_method: str = "standard"
) -> Decimal:
    """
    Calculate estimated shipping charges based on order subtotal after discounts,
    selected shipping strategy/method, and store configuration settings.
    """
    if subtotal_after_discounts <= Decimal("0.00"):
        return Decimal("0.00")

    shipping_cfg = get_shipping_settings()
    free_threshold = Decimal(str(shipping_cfg.get("free_shipping_threshold", "50000.00")))
    flat_rate = Decimal(str(shipping_cfg.get("flat_shipping_rate", "1500.00")))

    if subtotal_after_discounts >= free_threshold or shipping_method == "complimentary":
        return Decimal("0.00")

    if shipping_method == "express":
        return quantize_money(flat_rate * Decimal("1.5"))

    return quantize_money(flat_rate)


def calculate_tax(taxable_amount: Decimal, shipping_address: Optional[Any] = None) -> Decimal:
    """
    Calculate estimated sales tax or VAT based on store configuration settings
    and destination rules.
    """
    if taxable_amount <= Decimal("0.00"):
        return Decimal("0.00")

    currency_cfg = get_currency_settings()
    if not currency_cfg.get("tax_enabled", True):
        return Decimal("0.00")

    tax_pct = Decimal(str(currency_cfg.get("tax_percentage", "16.00")))
    rate = tax_pct / Decimal("100.00")

    tax = taxable_amount * rate
    return quantize_money(tax)


def calculate_total(
    subtotal: Decimal,
    discount: Decimal,
    coupon_discount: Decimal,
    shipping: Decimal,
    tax: Decimal
) -> Decimal:
    """
    Calculate final payable grand total across all pricing tiers.
    Enforces that grand total cannot drop below zero.
    """
    total = subtotal - discount - coupon_discount + shipping + tax
    if total < Decimal("0.00"):
        total = Decimal("0.00")
    return quantize_money(total)


def pricing_breakdown(
    cart: Optional[Any] = None,
    shipping_address: Optional[Any] = None,
    shipping_method: str = "standard"
) -> Dict[str, Any]:
    """
    Orchestrate the complete pricing calculation pipeline.
    Returns a structured dictionary with every monetary metric, applied promo codes, and item counts.
    Utilizes request-lifecycle caching on cart (`_cached_breakdown`) when evaluated for standard shipping without specific address overrides.
    """
    if cart and shipping_address is None and shipping_method == "standard":
        cached = getattr(cart, "_cached_breakdown", None)
        if cached is not None:
            return cached

    subtotal = calculate_subtotal(cart)
    discount, promotions_applied = calculate_discount(subtotal, cart)
    
    subtotal_after_promo = max(Decimal("0.00"), subtotal - discount)
    
    coupon_obj = getattr(cart, "coupon", None) if cart else None
    coupon_discount = calculate_coupon(subtotal_after_promo, coupon_obj)
    
    subtotal_after_all_discounts = max(Decimal("0.00"), subtotal_after_promo - coupon_discount)
    
    shipping = calculate_shipping(subtotal_after_all_discounts, shipping_address, shipping_method)
    tax = calculate_tax(subtotal_after_all_discounts, shipping_address)
    grand_total = calculate_total(subtotal, discount, coupon_discount, shipping, tax)

    item_count = cart.item_count() if (cart and hasattr(cart, "item_count")) else 0
    is_empty = (item_count == 0)

    # Check if coupon was actually applied / valid
    applied_coupon = coupon_obj if (coupon_obj and coupon_discount > Decimal("0.00")) else None

    # Free shipping progress metrics
    shipping_cfg = get_shipping_settings()
    free_shipping_threshold = Decimal(str(shipping_cfg.get("free_shipping_threshold", "50000.00")))
    free_shipping_remaining = max(Decimal("0.00"), free_shipping_threshold - subtotal_after_all_discounts)
    if subtotal_after_all_discounts >= free_shipping_threshold or is_empty:
        free_shipping_progress_pct = 100 if not is_empty else 0
    else:
        free_shipping_progress_pct = int((subtotal_after_all_discounts / free_shipping_threshold) * 100)

    result = {
        "subtotal": subtotal,
        "discount": discount,
        "coupon_discount": coupon_discount,
        "shipping": shipping,
        "tax": tax,
        "grand_total": grand_total,
        "coupon": applied_coupon,
        "coupon_code": applied_coupon.code if applied_coupon else None,
        "promotions_applied": promotions_applied,
        "item_count": item_count,
        "is_empty": is_empty,
        "free_shipping_threshold": free_shipping_threshold,
        "free_shipping_remaining": free_shipping_remaining,
        "free_shipping_progress_pct": free_shipping_progress_pct,
    }

    if cart and shipping_address is None and shipping_method == "standard":
        setattr(cart, "_cached_breakdown", result)

    return result


@transaction.atomic
def apply_coupon_to_cart(cart: Any, code: str) -> Coupon:
    """
    Validate and attach a coupon promo code to an active shopping cart.
    Raises ValidationError if the coupon is invalid, expired, or subtotal is too low.
    """
    if not cart:
        raise ValidationError("No active shopping bag found.")

    if hasattr(cart, "_cached_breakdown"):
        delattr(cart, "_cached_breakdown")

    coupon = coupon_by_code(code)
    if not coupon:
        raise ValidationError("The promotional code entered is invalid.")

    if not coupon.is_valid_now():
        raise ValidationError(f"The coupon '{coupon.code}' has expired or is no longer active.")

    subtotal = calculate_subtotal(cart)
    discount, _ = calculate_discount(subtotal, cart)
    subtotal_after_promo = max(Decimal("0.00"), subtotal - discount)

    if not coupon.is_valid_for_subtotal(subtotal_after_promo):
        raise ValidationError(
            f"The coupon '{coupon.code}' requires a minimum order subtotal of ${coupon.minimum_order_amount:.2f}."
        )

    cart.coupon = coupon
    cart.save()
    return coupon


@transaction.atomic
def remove_coupon_from_cart(cart: Any) -> None:
    """
    Remove any currently attached coupon from the shopping cart.
    """
    if hasattr(cart, "_cached_breakdown"):
        delattr(cart, "_cached_breakdown")
    if cart and getattr(cart, "coupon", None):
        cart.coupon = None
        cart.save()


@transaction.atomic
def record_and_increment_coupon_usage(
    coupon_code: str,
    user: Optional[Any] = None,
    order_id: str = "",
    discount_amount: Decimal = Decimal("0.00")
) -> Coupon:
    """
    Atomically verify and increment coupon usage upon order placement (Phase 4.4).
    Uses select_for_update() to acquire an exclusive row lock, preventing race conditions
    under concurrent checkout attempts.
    Creates an immutable CouponUsageLog record.
    """
    if not coupon_code:
        raise ValidationError("No coupon code provided for usage logging.")

    clean_code = coupon_code.strip().upper()
    coupon = Coupon.objects.select_for_update().filter(code__iexact=clean_code).first()
    if not coupon:
        raise ValidationError(f"Coupon '{clean_code}' not found.")

    if not coupon.is_valid_now():
        raise ValidationError(f"The coupon '{coupon.code}' is expired or no longer active.")

    if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
        raise ValidationError(f"The usage limit for coupon '{coupon.code}' has been reached.")

    coupon.usage_count += 1
    coupon.save()

    CouponUsageLog.objects.create(
        coupon=coupon,
        user=user if (user and hasattr(user, "is_authenticated") and user.is_authenticated) else None,
        order_id=order_id,
        discount_amount=quantize_money(discount_amount)
    )
    return coupon
