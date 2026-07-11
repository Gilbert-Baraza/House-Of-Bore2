# fulfillment/permissions.py
"""
fulfillment/permissions.py
──────────────────────────────────────────────────────────────────────────────
RBAC authorization integration for the Fulfillment & Shipping Operations engine.
Registers granular fulfillment permissions (`view_fulfillment`, `assign_orders`,
`pick_orders`, `pack_orders`, `dispatch_orders`, `confirm_delivery`, etc.) and
backfills `store_manager`, `inventory_manager`, and `fulfillment_manager` roles.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import List
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from dashboard.models import StaffRole
from .models import FulfillmentOrder


FULFILLMENT_PERMISSIONS = [
    ("view_fulfillment", "Can view fulfillment dashboard, order queues, and timelines"),
    ("assign_orders", "Can assign fulfillment leads, pickers, and packers to orders"),
    ("pick_orders", "Can start picking and submit picked quantity verifications"),
    ("pack_orders", "Can start packing and confirm package completion"),
    ("dispatch_orders", "Can generate shipping labels and confirm courier handoff/dispatch"),
    ("confirm_delivery", "Can confirm final customer delivery or exception resolution"),
    ("manage_returns", "Can inspect and process returns, RMA approvals, and exchanges"),
    ("view_shipment_reports", "Can export and view carrier shipping cost reports"),
]


def ensure_fulfillment_permissions() -> List[str]:
    """
    Ensure all application-level fulfillment permissions exist in Django auth_permission table
    and attach them to default operational roles.
    """
    try:
        content_type = ContentType.objects.get_for_model(FulfillmentOrder)
    except Exception:
        return [f"fulfillment.{codename}" for codename, _ in FULFILLMENT_PERMISSIONS]

    permission_codes = []
    for codename, name in FULFILLMENT_PERMISSIONS:
        Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permission_codes.append(f"fulfillment.{codename}")

    # Update store_manager and inventory_manager roles if they exist
    store_mgr = StaffRole.objects.filter(code="store_manager").first()
    if store_mgr:
        current_perms = set(store_mgr.permissions)
        current_perms.update(permission_codes)
        store_mgr.permissions = sorted(list(current_perms))
        store_mgr.save(update_fields=["permissions", "updated_at"])

    inv_mgr = StaffRole.objects.filter(code="inventory_manager").first()
    if inv_mgr:
        inv_perms = set(inv_mgr.permissions)
        inv_perms.update([
            "fulfillment.view_fulfillment",
            "fulfillment.pick_orders",
            "fulfillment.pack_orders",
            "fulfillment.manage_returns",
        ])
        inv_mgr.permissions = sorted(list(inv_perms))
        inv_mgr.save(update_fields=["permissions", "updated_at"])

    # Ensure dedicated fulfillment_manager role exists
    FulfillmentRole, _ = StaffRole.objects.get_or_create(
        code="fulfillment_manager",
        defaults={
            "name": "Fulfillment & Logistics Manager",
            "description": "Supervises warehouse picking, packing, shipping dispatch, and courier tracking.",
            "permissions": permission_codes,
        },
    )
    if not _ and set(FulfillmentRole.permissions) != set(permission_codes):
        FulfillmentRole.permissions = permission_codes
        FulfillmentRole.save(update_fields=["permissions", "updated_at"])

    return permission_codes
