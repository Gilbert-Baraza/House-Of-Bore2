# reviews/admin.py
"""
reviews/admin.py
──────────────────────────────────────────────────────────────────────────────
Django Admin configuration for product reviews and ratings.

Features:
- Clickable links to Product and Author change pages.
- Visual star rating display.
- Bulk moderation actions (Approve / Reject) with automatic cache invalidation.
- Comprehensive search and filtering.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import admin, messages
from django.core.cache import cache
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_select_related = ["product", "user"]
    list_display = [
        "id",
        "product_link",
        "user_link",
        "rating_display",
        "title",
        "is_approved",
        "created_at",
    ]
    list_filter = ["is_approved", "rating", "created_at"]
    search_fields = [
        "product__name",
        "user__email",
        "user__first_name",
        "user__last_name",
        "title",
        "comment",
    ]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["approve_reviews", "reject_reviews"]
    list_per_page = 25
    ordering = ["-created_at"]

    fieldsets = (
        (
            _("Review Information"),
            {
                "fields": ("product", "user", "rating", "title", "comment", "is_approved"),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("Product"), ordering="product__name")
    def product_link(self, obj: Review) -> str:
        url = reverse("admin:products_product_change", args=[obj.product.pk])
        return format_html('<a href="{}" style="font-weight: 600;">{}</a>', url, obj.product.name)

    @admin.display(description=_("Author"), ordering="user__email")
    def user_link(self, obj: Review) -> str:
        url = reverse("admin:accounts_user_change", args=[obj.user.pk])
        author_name = obj.user.get_full_name() or obj.user.email
        return format_html('<a href="{}">{}</a>', url, author_name)

    @admin.display(description=_("Rating"), ordering="rating")
    def rating_display(self, obj: Review) -> str:
        filled = "★" * obj.rating
        empty = "☆" * (5 - obj.rating)
        color = "#d97706" if obj.rating >= 4 else ("#ca8a04" if obj.rating == 3 else "#dc2626")
        return format_html(
            '<span style="color: {}; font-size: 1.1em; letter-spacing: 1px;">{}{}</span> '
            '<span style="color: #6b7280; font-size: 0.85em;">({}/5)</span>',
            color,
            filled,
            empty,
            obj.rating,
        )

    @admin.action(description=_("Approve selected reviews (make public)"))
    def approve_reviews(self, request, queryset):
        product_ids = set(queryset.values_list("product_id", flat=True))
        updated = queryset.update(is_approved=True)
        for pid in product_ids:
            cache.delete(f"product_review_summary_{pid}")
        self.message_user(
            request,
            f"Successfully approved {updated} review(s).",
            messages.SUCCESS,
        )

    @admin.action(description=_("Reject selected reviews (hide from public)"))
    def reject_reviews(self, request, queryset):
        product_ids = set(queryset.values_list("product_id", flat=True))
        updated = queryset.update(is_approved=False)
        for pid in product_ids:
            cache.delete(f"product_review_summary_{pid}")
        self.message_user(
            request,
            f"Successfully rejected/hidden {updated} review(s).",
            messages.SUCCESS,
        )
