# reviews/forms.py
"""
reviews/forms.py
──────────────────────────────────────────────────────────────────────────────
Form handling for product reviews and ratings.

Includes:
- Custom widgets and styling for interactive star ratings and clean inputs.
- Duplicate review prevention in clean().
- Automatic assignment of product and author upon saving.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from reviews.models import Review


class ReviewForm(forms.ModelForm):
    """
    ModelForm for submitting and editing product reviews.
    """

    RATING_CHOICES = [
        (5, _("5 Stars - Excellent")),
        (4, _("4 Stars - Good")),
        (3, _("3 Stars - Average")),
        (2, _("2 Stars - Fair")),
        (1, _("1 Star - Poor")),
    ]

    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "sr-only peer"}),
        label=_("Overall Rating"),
        error_messages={"required": _("Please select a star rating from 1 to 5.")},
    )

    class Meta:
        model = Review
        fields = ["rating", "title", "comment"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": (
                        "w-full px-3.5 py-2.5 text-sm bg-white border border-neutral-300 "
                        "rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none "
                        "focus:ring-2 focus:ring-accent-500 focus:border-accent-500 transition-colors"
                    ),
                    "placeholder": _("Summarize your experience (e.g., Exceptional craftsmanship)..."),
                }
            ),
            "comment": forms.Textarea(
                attrs={
                    "class": (
                        "w-full px-3.5 py-2.5 text-sm bg-white border border-neutral-300 "
                        "rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none "
                        "focus:ring-2 focus:ring-accent-500 focus:border-accent-500 transition-colors"
                    ),
                    "placeholder": _("Share your thoughts on fit, fabric, comfort, and durability..."),
                    "rows": 4,
                }
            ),
        }
        labels = {
            "title": _("Review Title"),
            "comment": _("Detailed Review"),
        }

    def __init__(self, *args, **kwargs):
        self.product = kwargs.pop("product", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        try:
            val = int(rating)
            if not (1 <= val <= 5):
                raise forms.ValidationError(_("Rating must be between 1 and 5 stars."))
            return val
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Please select a valid star rating."))

    def clean(self):
        cleaned_data = super().clean()
        # If creating a new review, verify the user has not already reviewed this product
        if not self.instance.pk and self.product and self.user:
            if Review.objects.filter(product=self.product, user=self.user).exists():
                raise forms.ValidationError(
                    _("You have already submitted a review for this product. You can edit your existing review below.")
                )
        return cleaned_data

    def save(self, commit=True):
        review = super().save(commit=False)
        if self.product:
            review.product = self.product
        if self.user:
            review.user = self.user
        if commit:
            review.save()
        return review
