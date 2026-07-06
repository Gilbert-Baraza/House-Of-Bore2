# reviews/views.py
"""
reviews/views.py
──────────────────────────────────────────────────────────────────────────────
Class-based views for managing product reviews and ratings.

Security & Permissions:
- Only authenticated users can submit reviews (LoginRequiredMixin).
- Only the author of a review can edit or delete it (UserPassesTestMixin).
- Enforces one review per user per product.
──────────────────────────────────────────────────────────────────────────────
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, UpdateView

from products.models import Product
from reviews.forms import ReviewForm
from reviews.models import Review


class CreateReviewView(LoginRequiredMixin, CreateView):
    """
    Handles submission of a new product review.
    
    If an authenticated user has already reviewed the product, redirects them
    to edit their existing review.
    """
    model = Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.product = get_object_or_404(
            Product,
            slug=self.kwargs["product_slug"],
            is_active=True,
        )

    def dispatch(self, request, *args, **kwargs):
        # Check if user already reviewed this product
        if request.user.is_authenticated:
            existing_review = Review.objects.filter(product=self.product, user=request.user).first()
            if existing_review:
                messages.info(
                    request,
                    _("You have already reviewed this product. You can edit your review below."),
                )
                return redirect("reviews:update_review", pk=existing_review.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.product
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.product
        context["is_create"] = True
        return context

    def form_valid(self, form):
        review = form.save()
        messages.success(
            self.request,
            _("Thank you! Your review has been published."),
        )
        return redirect(review.get_absolute_url())

    def form_invalid(self, form):
        messages.error(
            self.request,
            _("Please correct the errors below to submit your review."),
        )
        return super().form_invalid(form)


class UpdateReviewView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Allows a customer to edit their existing review.
    
    Guarded by UserPassesTestMixin to ensure only the author can update.
    """
    model = Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"
    context_object_name = "review"

    def test_func(self):
        review = self.get_object()
        return review.user == self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["product"] = self.object.product
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.object.product
        context["is_create"] = False
        return context

    def form_valid(self, form):
        review = form.save()
        messages.success(
            self.request,
            _("Your review has been successfully updated."),
        )
        return redirect(review.get_absolute_url())


class DeleteReviewView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Allows a customer to delete their own review.
    
    Guarded by UserPassesTestMixin to ensure only the author can delete.
    """
    model = Review
    template_name = "reviews/review_confirm_delete.html"
    context_object_name = "review"

    def test_func(self):
        review = self.get_object()
        return review.user == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = self.object.product
        return context

    def get_success_url(self):
        messages.success(
            self.request,
            _("Your review has been removed."),
        )
        return f"{self.object.product.get_absolute_url()}#reviews"
