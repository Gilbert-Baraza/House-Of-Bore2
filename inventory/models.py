from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MovementType(models.TextChoices):
    INITIAL_STOCK = "initial_stock", "Initial Stock"
    PURCHASE = "purchase", "Purchase"
    SALE = "sale", "Sale"
    RESERVATION = "reservation", "Reservation"
    RESERVATION_RELEASED = "reservation_released", "Reservation Released"
    RETURN = "return", "Return"
    REFUND_RESTOCK = "refund_restock", "Refund Restock"
    DAMAGE = "damage", "Damage"
    MANUAL_INCREASE = "manual_increase", "Manual Increase"
    MANUAL_DECREASE = "manual_decrease", "Manual Decrease"
    INVENTORY_CORRECTION = "inventory_correction", "Inventory Correction"


class Inventory(models.Model):
    """Single source of truth for stock visibility and adjustments for a variant."""

    product_variant = models.OneToOneField(
        "products.ProductVariant",
        on_delete=models.CASCADE,
        related_name="inventory",
        help_text="Associated variant whose stock this record controls.",
    )
    available_quantity = models.PositiveIntegerField(default=0, help_text="Current sellable stock available to customers.")
    reserved_quantity = models.PositiveIntegerField(default=0, help_text="Quantity reserved for pending orders.")
    damaged_quantity = models.PositiveIntegerField(default=0, help_text="Quantity currently marked as damaged or unusable.")
    reorder_level = models.PositiveIntegerField(default=0, help_text="Threshold below which reorder attention is required.")
    reorder_quantity = models.PositiveIntegerField(default=0, help_text="Suggested replenishment quantity.")
    last_stock_check = models.DateTimeField(null=True, blank=True, help_text="Most recent stock count or audit timestamp.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "inventory"
        verbose_name_plural = "inventory"
        ordering = ["product_variant__product__name", "product_variant__sku"]
        indexes = [
            models.Index(fields=["available_quantity", "reserved_quantity"]),
            models.Index(fields=["reorder_level", "available_quantity"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_variant} inventory"

    def clean(self) -> None:
        super().clean()
        if self.available_quantity < 0:
            raise ValidationError({"available_quantity": "Available stock cannot be negative."})
        if self.reserved_quantity < 0:
            raise ValidationError({"reserved_quantity": "Reserved stock cannot be negative."})
        if self.damaged_quantity < 0:
            raise ValidationError({"damaged_quantity": "Damaged stock cannot be negative."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def add_stock(self, quantity: int, performed_by=None, notes: str = "", movement_type: str = MovementType.PURCHASE, reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import add_stock

        return add_stock(
            self,
            quantity=quantity,
            performed_by=performed_by,
            notes=notes,
            movement_type=movement_type,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def remove_stock(self, quantity: int, performed_by=None, notes: str = "", movement_type: str = MovementType.SALE, reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import remove_stock

        return remove_stock(
            self,
            quantity=quantity,
            performed_by=performed_by,
            notes=notes,
            movement_type=movement_type,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def reserve_stock(self, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import reserve_stock

        return reserve_stock(self, quantity, performed_by=performed_by, notes=notes, reference_type=reference_type, reference_id=reference_id)

    def release_stock(self, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import release_stock

        return release_stock(self, quantity, performed_by=performed_by, notes=notes, reference_type=reference_type, reference_id=reference_id)

    def adjust_stock(self, quantity: int, performed_by=None, reason: str = "", notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import adjust_stock

        return adjust_stock(
            self,
            quantity=quantity,
            performed_by=performed_by,
            reason=reason,
            notes=notes,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def transfer_stock(self, quantity: int, performed_by=None, notes: str = "") -> "Inventory":
        from .services import transfer_stock

        return transfer_stock(self, quantity=quantity, performed_by=performed_by, notes=notes)

    def process_return(self, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import process_return

        return process_return(self, quantity=quantity, performed_by=performed_by, notes=notes, reference_type=reference_type, reference_id=reference_id)

    def mark_damaged(self, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> "Inventory":
        from .services import mark_damaged

        return mark_damaged(self, quantity=quantity, performed_by=performed_by, notes=notes, reference_type=reference_type, reference_id=reference_id)

    def snapshot(self) -> dict[str, Any]:
        from .services import inventory_snapshot

        return inventory_snapshot(self)

    def valuation(self) -> Decimal:
        from .services import inventory_valuation

        return inventory_valuation(self)

    @property
    def is_low_stock(self) -> bool:
        return self.available_quantity > 0 and self.available_quantity <= max(self.reorder_level, self.product_variant.low_stock_threshold)

    @property
    def is_out_of_stock(self) -> bool:
        return self.available_quantity == 0


class InventoryMovement(models.Model):
    """Immutable ledger entry capturing every inventory mutation."""

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=40, choices=MovementType.choices)
    quantity = models.IntegerField(help_text="Signed delta applied to stock.")
    previous_quantity = models.IntegerField(help_text="Inventory level before the change.")
    new_quantity = models.IntegerField(help_text="Inventory level after the change.")
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.CharField(max_length=255, blank=True, default="")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "inventory movement"
        verbose_name_plural = "inventory movements"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.inventory} {self.get_movement_type_display()}"

    def clean(self) -> None:
        super().clean()
        if self.pk:
            raise ValidationError("Inventory movements are immutable once created.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        raise ValidationError("Inventory movements cannot be deleted after creation.")
