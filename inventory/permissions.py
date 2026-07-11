from django.contrib.auth.models import Permission

VIEW_INVENTORY = "view_inventory"
ADJUST_INVENTORY = "adjust_inventory"
APPROVE_ADJUSTMENTS = "approve_adjustments"
PROCESS_RETURNS = "process_returns"
VIEW_VALUATION = "view_valuation"
MANAGE_REORDER_LEVELS = "manage_reorder_levels"


def ensure_inventory_permissions():
    return [
        VIEW_INVENTORY,
        ADJUST_INVENTORY,
        APPROVE_ADJUSTMENTS,
        PROCESS_RETURNS,
        VIEW_VALUATION,
        MANAGE_REORDER_LEVELS,
    ]
