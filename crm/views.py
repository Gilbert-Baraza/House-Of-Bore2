# crm/views.py
"""
crm/views.py
──────────────────────────────────────────────────────────────────────────────
Administrative presentation and action controller for Customer Relationship Management.
Provides staff portals for 360° profile inspection, multi-dimensional customer queue
filtering, interaction logging, private staff notes, and auditable JSON exports.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from dashboard.permissions import has_dashboard_permission
from .forms import CustomerInteractionRecordForm, CustomerStaffNoteForm
from .permissions import (
    CRMPermissionRequiredMixin,
    can_add_staff_note,
    can_change_customer,
    can_export_customer_data,
    can_view_analytics,
)
from .selectors import (
    customer_segments,
    customer_statistics,
    get_customer_detail,
    recent_customers,
    search_customers,
)
from .services import (
    add_staff_note,
    build_customer_profile,
    customer_timeline,
    export_customer_data,
    log_customer_interaction,
)


class CRMDashboardView(CRMPermissionRequiredMixin, TemplateView):
    """
    Primary CRM landing portal providing executive KPIs, behavioral segment distribution,
    and immediate access to recent patron registrations.
    """
    template_name = "dashboard/crm/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "customers",
            "stats": customer_statistics(),
            "segments": customer_segments(),
            "recent_patrons": recent_customers(days=30)[:8],
            "can_view_analytics": can_view_analytics(self.request.user),
            "can_export": can_export_customer_data(self.request.user),
        })
        return context


class CustomerListView(CRMPermissionRequiredMixin, ListView):
    """
    Paginated administrative customer directory (`20`/page) supporting full-text search,
    segment filtering, and multi-metric sorting without N+1 query overhead.
    """
    template_name = "dashboard/crm/customer_list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        query = self.request.GET.get("search", "")
        segment = self.request.GET.get("segment", "all")
        sort_by = self.request.GET.get("sort_by", "registered_desc")
        return search_customers(query=query, segment=segment, sort_by=sort_by)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "customers",
            "search_query": self.request.GET.get("search", ""),
            "segment_filter": self.request.GET.get("segment", "all"),
            "sort_by": self.request.GET.get("sort_by", "registered_desc"),
            "segments": customer_segments(),
            "stats": customer_statistics(),
            "can_change": can_change_customer(self.request.user),
        })
        return context


class CustomerDetailView(CRMPermissionRequiredMixin, TemplateView):
    """
    The 360° Customer Profile Screen.
    Aggregates patron identity, address book, financial ledger, order history,
    wishlist summary, recent reviews, private staff notes, and interaction logs.
    """
    template_name = "dashboard/crm/customer_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]
        customer = get_customer_detail(customer_id)
        if not customer:
            raise Http404(f"Patron account #{customer_id} not found or access restricted.")

        profile_data = build_customer_profile(customer)
        timeline_preview = customer_timeline(customer, limit=15)

        can_note = can_add_staff_note(self.request.user)
        staff_notes = customer.staff_notes.select_related("author").all() if can_note else []
        interactions = customer.interaction_records.select_related("performed_by").all() if can_note else []

        context.update({
            "active_nav": "customers",
            "customer": customer,
            "profile": profile_data,
            "timeline": timeline_preview,
            "staff_notes": staff_notes,
            "interactions": interactions,
            "note_form": CustomerStaffNoteForm(),
            "interaction_form": CustomerInteractionRecordForm(),
            "can_note": can_note,
            "can_change": can_change_customer(self.request.user),
            "can_export": can_export_customer_data(self.request.user),
        })
        return context


class CustomerTimelineView(CRMPermissionRequiredMixin, TemplateView):
    """
    Dedicated full chronological interaction timeline screen for deep audit inspection.
    """
    template_name = "dashboard/crm/timeline.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        customer_id = self.kwargs["pk"]
        customer = get_customer_detail(customer_id)
        if not customer:
            raise Http404(f"Patron #{customer_id} not found.")

        context.update({
            "active_nav": "customers",
            "customer": customer,
            "profile": build_customer_profile(customer),
            "timeline": customer_timeline(customer, limit=100),
        })
        return context


class CustomerStaffNoteCreateView(CRMPermissionRequiredMixin, View):
    """
    POST-only endpoint for adding private administrative notes to a customer profile.
    """
    required_permissions = ["crm.add_staffnote"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        customer = get_customer_detail(pk)
        if not customer:
            raise Http404("Customer not found.")

        form = CustomerStaffNoteForm(request.POST)
        if form.is_valid():
            try:
                add_staff_note(
                    customer=customer,
                    author=request.user,
                    note=form.cleaned_data["note"],
                    category=form.cleaned_data["category"],
                    is_pinned=form.cleaned_data["is_pinned"],
                )
                messages.success(request, f"Private note added to patron {customer.email}.")
            except Exception as exc:
                messages.error(request, f"Could not save staff note: {str(exc)}")
        else:
            for err in form.errors.values():
                messages.error(request, err)

        return redirect("crm:customer_detail", pk=customer.pk)


class CustomerInteractionLogView(CRMPermissionRequiredMixin, View):
    """
    POST-only endpoint for logging offline concierge interactions (phone, email, salon).
    """
    required_permissions = ["crm.add_staffnote"]

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        customer = get_customer_detail(pk)
        if not customer:
            raise Http404("Customer not found.")

        form = CustomerInteractionRecordForm(request.POST)
        if form.is_valid():
            try:
                log_customer_interaction(
                    customer=customer,
                    performed_by=request.user,
                    interaction_type=form.cleaned_data["interaction_type"],
                    summary=form.cleaned_data["summary"],
                    details=form.cleaned_data.get("details", ""),
                    timestamp=form.cleaned_data.get("timestamp"),
                )
                messages.success(request, f"Concierge interaction recorded for {customer.email}.")
            except Exception as exc:
                messages.error(request, f"Failed to log interaction: {str(exc)}")
        else:
            for err in form.errors.values():
                messages.error(request, err)

        return redirect("crm:customer_detail", pk=customer.pk)


class CustomerSegmentsView(CRMPermissionRequiredMixin, TemplateView):
    """
    Detailed analytical view of dynamic customer behavior cohorts.
    """
    required_permissions = ["crm.view_analytics"]
    template_name = "dashboard/crm/customer_segments.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update({
            "active_nav": "customers",
            "segments": customer_segments(),
            "stats": customer_statistics(),
        })
        return context


class CustomerExportView(CRMPermissionRequiredMixin, View):
    """
    Secure endpoint generating an auditable, comprehensive JSON data dump of a patron's
    360° profile, order history, address book, and reviews.
    """
    required_permissions = ["crm.export_customerdata"]

    def get(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> HttpResponse:
        customer = get_customer_detail(pk)
        if not customer:
            raise Http404("Customer not found.")

        try:
            bundle = export_customer_data(user=customer, performed_by=request.user)
            response = JsonResponse(bundle, json_dumps_params={"indent": 2})
            response["Content-Disposition"] = f'attachment; filename="houseofbore_patron_360_{customer.pk}.json"'
            return response
        except Exception as exc:
            messages.error(request, f"Data export failed: {str(exc)}")
            return redirect("crm:customer_detail", pk=customer.pk)
