from django.core.management.base import BaseCommand

from products.models import ProductVariant

from inventory.models import Inventory


class Command(BaseCommand):
    help = "Create inventory records for existing product variants that do not already have one."

    def handle(self, *args, **options):
        created_count = 0
        for variant in ProductVariant.objects.iterator():
            inventory, created = Inventory.objects.get_or_create(
                product_variant=variant,
                defaults={
                    "available_quantity": variant.stock_quantity or 0,
                    "reorder_level": variant.low_stock_threshold or 0,
                    "reorder_quantity": max(variant.low_stock_threshold or 0, 1),
                },
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f"Backfilled inventory for {created_count} variants."))
