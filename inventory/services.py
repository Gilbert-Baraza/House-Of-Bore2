from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Inventory, InventoryMovement, MovementType


@transaction.atomic
def add_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", movement_type: str = MovementType.PURCHASE, reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Stock additions cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    previous_quantity = inventory_db.available_quantity
    inventory_db.available_quantity = previous_quantity + quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=movement_type,
        quantity=quantity,
        previous_quantity=previous_quantity,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def remove_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", movement_type: str = MovementType.SALE, reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Stock removals cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory_db.available_quantity < quantity:
        raise ValidationError("Insufficient available stock for this operation.")
    previous_quantity = inventory_db.available_quantity
    inventory_db.available_quantity = previous_quantity - quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=movement_type,
        quantity=-quantity,
        previous_quantity=previous_quantity,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def reserve_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Reservation quantity cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory_db.available_quantity - inventory_db.reserved_quantity < quantity:
        raise ValidationError("Cannot reserve more stock than is currently available.")
    previous_reserved = inventory_db.reserved_quantity
    inventory_db.reserved_quantity = previous_reserved + quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["reserved_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=MovementType.RESERVATION,
        quantity=quantity,
        previous_quantity=previous_reserved,
        new_quantity=inventory_db.reserved_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.reserved_quantity = inventory_db.reserved_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def release_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Release quantity cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory_db.reserved_quantity < quantity:
        raise ValidationError("Cannot release more stock than is currently reserved.")
    previous_reserved = inventory_db.reserved_quantity
    inventory_db.reserved_quantity = previous_reserved - quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["reserved_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=MovementType.RESERVATION_RELEASED,
        quantity=-quantity,
        previous_quantity=previous_reserved,
        new_quantity=inventory_db.reserved_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.reserved_quantity = inventory_db.reserved_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def adjust_stock(inventory: Inventory, quantity: int, performed_by=None, reason: str = "", notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if not reason.strip():
        raise ValidationError("An adjustment reason is required.")
    if quantity == 0:
        raise ValidationError("Adjustment quantity must be non-zero.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    previous_quantity = inventory_db.available_quantity
    new_quantity = previous_quantity + quantity
    if new_quantity < 0:
        raise ValidationError("Negative adjustment attempts are not allowed.")
    inventory_db.available_quantity = new_quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "last_stock_check", "updated_at"])
    movement_type = MovementType.MANUAL_INCREASE if quantity > 0 else MovementType.MANUAL_DECREASE
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=movement_type,
        quantity=quantity,
        previous_quantity=previous_quantity,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=f"{reason}: {notes}".strip(),
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def transfer_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "") -> Inventory:
    return inventory


@transaction.atomic
def fulfill_reserved_stock(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Fulfillment quantity cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory_db.reserved_quantity < quantity:
        raise ValidationError("Cannot fulfill more stock than is currently reserved.")
    previous_available = inventory_db.available_quantity
    previous_reserved = inventory_db.reserved_quantity
    inventory_db.available_quantity = previous_available - quantity
    inventory_db.reserved_quantity = previous_reserved - quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "reserved_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=MovementType.SALE,
        quantity=-quantity,
        previous_quantity=previous_available,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.reserved_quantity = inventory_db.reserved_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def process_return(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Returned quantity cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    previous_quantity = inventory_db.available_quantity
    inventory_db.available_quantity = previous_quantity + quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=MovementType.RETURN,
        quantity=quantity,
        previous_quantity=previous_quantity,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def mark_damaged(inventory: Inventory, quantity: int, performed_by=None, notes: str = "", reference_type: str | None = None, reference_id: str | None = None) -> Inventory:
    if quantity < 0:
        raise ValidationError("Damaged quantity cannot be negative.")
    inventory_db = Inventory.objects.select_for_update().get(pk=inventory.pk)
    if inventory_db.available_quantity < quantity:
        raise ValidationError("Cannot mark more stock as damaged than is currently available.")
    previous_available = inventory_db.available_quantity
    previous_damaged = inventory_db.damaged_quantity
    inventory_db.available_quantity = previous_available - quantity
    inventory_db.damaged_quantity = previous_damaged + quantity
    inventory_db.last_stock_check = timezone.now()
    inventory_db.save(update_fields=["available_quantity", "damaged_quantity", "last_stock_check", "updated_at"])
    InventoryMovement.objects.create(
        inventory=inventory_db,
        movement_type=MovementType.DAMAGE,
        quantity=-quantity,
        previous_quantity=previous_available,
        new_quantity=inventory_db.available_quantity,
        reference_type=reference_type or "",
        reference_id=reference_id or "",
        performed_by=performed_by,
        notes=notes,
    )
    inventory.available_quantity = inventory_db.available_quantity
    inventory.damaged_quantity = inventory_db.damaged_quantity
    inventory.last_stock_check = inventory_db.last_stock_check
    inventory.updated_at = inventory_db.updated_at
    return inventory_db


@transaction.atomic
def inventory_snapshot(inventory: Inventory) -> dict[str, Any]:
    return {
        "available_quantity": inventory.available_quantity,
        "reserved_quantity": inventory.reserved_quantity,
        "damaged_quantity": inventory.damaged_quantity,
        "reorder_level": inventory.reorder_level,
        "reorder_quantity": inventory.reorder_quantity,
        "is_low_stock": inventory.is_low_stock,
        "is_out_of_stock": inventory.is_out_of_stock,
    }


@transaction.atomic
def inventory_valuation(inventory: Inventory) -> Decimal:
    cost_price = inventory.product_variant.cost_price or Decimal("0.00")
    return cost_price * Decimal(inventory.available_quantity)
