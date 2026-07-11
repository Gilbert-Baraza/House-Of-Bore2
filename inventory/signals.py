from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from products.models import ProductVariant

from .models import Inventory
from .permissions import ensure_inventory_permissions as inventory_permission_codes


@receiver(post_save, sender=ProductVariant)
def ensure_inventory_for_variant(sender, instance, created, **kwargs):
    if created:
        Inventory.objects.get_or_create(
            product_variant=instance,
            defaults={
                "available_quantity": instance.stock_quantity or 0,
                "reorder_level": instance.low_stock_threshold or 0,
                "reorder_quantity": max(instance.low_stock_threshold or 0, 1),
            },
        )


@receiver(post_migrate)
def ensure_inventory_permissions(sender, **kwargs):
    if sender.name != "inventory":
        return

    content_type, _ = ContentType.objects.get_or_create(app_label="inventory", model="inventory")
    for codename in inventory_permission_codes():
        Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": codename.replace("_", " ").title()},
        )


@receiver(post_migrate)
def backfill_inventory_for_existing_variants(sender, **kwargs):
    if sender.name != "inventory":
        return

    for variant in ProductVariant.objects.iterator():
        Inventory.objects.get_or_create(
            product_variant=variant,
            defaults={
                "available_quantity": variant.stock_quantity or 0,
                "reorder_level": variant.low_stock_threshold or 0,
                "reorder_quantity": max(variant.low_stock_threshold or 0, 1),
            },
        )
