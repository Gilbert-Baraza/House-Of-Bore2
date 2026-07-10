# products/comparison.py
"""
products/comparison.py
──────────────────────────────────────────────────────────────────────────────
Product comparison service layer.
Manages a session-backed comparison list (`request.session['compare_list']`)
with a hard limit of 4 products to ensure clean side-by-side matrix UX.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import List, Tuple
from django.http import HttpRequest
from django.utils.translation import gettext as _
from products.models import Product


def get_comparison_ids(request: HttpRequest) -> List[int]:
    """Return the list of product IDs currently in the user's comparison list."""
    session_obj = getattr(request, "session", None)
    if not session_obj:
        return []
    return session_obj.get("compare_list", [])


def toggle_comparison_product(request: HttpRequest, product_id: int) -> Tuple[bool, str, int]:
    """
    Toggle a product inside the session comparison list.
    Returns (is_now_in_list: bool, message: str, total_count: int).
    Enforces a maximum of 4 products.
    """
    session_obj = getattr(request, "session", None)
    if not session_obj:
        return False, _("Session unavailable."), 0

    compare_list: List[int] = session_obj.get("compare_list", [])

    if product_id in compare_list:
        compare_list.remove(product_id)
        session_obj["compare_list"] = compare_list
        session_obj.modified = True
        return False, _("Removed from comparison list."), len(compare_list)

    if len(compare_list) >= 4:
        return False, _("Comparison list is full (maximum 4 products). Remove an item to add more."), len(compare_list)

    # Verify product exists and is active
    if not Product.objects.filter(pk=product_id, is_active=True).exists():
        return False, _("Product not available for comparison."), len(compare_list)

    compare_list.append(product_id)
    session_obj["compare_list"] = compare_list
    session_obj.modified = True
    return True, _("Added to comparison list."), len(compare_list)


def clear_comparison_list(request: HttpRequest) -> None:
    """Clear all products from the comparison list."""
    session_obj = getattr(request, "session", None)
    if session_obj and "compare_list" in session_obj:
        del session_obj["compare_list"]
        session_obj.modified = True


def get_comparison_products(request: HttpRequest):
    """
    Retrieve prefetched Product instances matching the session comparison IDs.
    Returns a list preserving the exact addition order.
    """
    ids = get_comparison_ids(request)
    if not ids:
        return []

    products_by_id = {
        p.pk: p for p in Product.objects.filter(pk__in=ids, is_active=True).select_related(
            "category", "brand"
        ).prefetch_related("images")
    }

    return [products_by_id[pid] for pid in ids if pid in products_by_id]
