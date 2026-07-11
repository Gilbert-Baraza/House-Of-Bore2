# fulfillment/forms.py
"""
fulfillment/forms.py
──────────────────────────────────────────────────────────────────────────────
Forms for staff interactions across the order fulfillment lifecycle:
1. StaffAssignmentForm: Assign fulfillment leads, pickers, or packers.
2. PickingVerificationForm: Record picked and missing item quantities.
3. PackingCompletionForm: Confirm package readiness and add packing notes.
4. ShipmentCreationForm: Generate shipping labels, tracking numbers, and dimensions.
5. ReturnInspectionForm: Process warehouse RMA receipt and stock reintegration.
──────────────────────────────────────────────────────────────────────────────
"""

from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model

from .models import FulfillmentPriority

User = get_user_model()


class StaffAssignmentForm(forms.Form):
    role = forms.ChoiceField(
        choices=[("general", "Fulfillment Lead"), ("picker", "Warehouse Picker"), ("packer", "Warehouse Packer")],
        label="Assignment Role",
        required=True
    )
    staff_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True).order_by("email"),
        required=False,
        label="Staff Member",
        empty_label="-- Unassigned --"
    )


class PickingItemVerificationForm(forms.Form):
    item_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    picked_quantity = forms.IntegerField(min_value=0, required=True, label="Picked Qty")
    missing_quantity = forms.IntegerField(min_value=0, required=False, initial=0, label="Missing Qty")
    notes = forms.CharField(required=False, max_length=255, label="Notes / Substitution Info")


class PackingCompletionForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Enter packing verification notes, box sizes, or Fragile flags..."}),
        required=False,
        label="Packing Checklist Notes"
    )


class ShipmentCreationForm(forms.Form):
    courier = forms.ChoiceField(
        choices=[
            ("FedEx Ground", "FedEx Ground"),
            ("FedEx Express", "FedEx Express (Overnight/2-Day)"),
            ("UPS Ground", "UPS Ground"),
            ("UPS Next Day Air", "UPS Next Day Air"),
            ("USPS Priority Mail", "USPS Priority Mail"),
            ("DHL Express", "DHL Express International"),
            ("Custom Courier", "Custom / Local Courier"),
        ],
        required=True,
        label="Logistics Courier"
    )
    shipping_method = forms.CharField(max_length=100, required=True, initial="Standard Ground", label="Shipping Method / Service Level")
    tracking_number = forms.CharField(
        max_length=120,
        required=False,
        label="Tracking Number",
        help_text="Leave blank to automatically generate an internal system tracking code."
    )
    shipping_cost = forms.DecimalField(max_digits=10, decimal_places=2, required=False, initial=Decimal("0.00"), label="Actual Shipping Cost ($)")
    length = forms.DecimalField(max_digits=8, decimal_places=2, required=False, label="Length (cm)")
    width = forms.DecimalField(max_digits=8, decimal_places=2, required=False, label="Width (cm)")
    height = forms.DecimalField(max_digits=8, decimal_places=2, required=False, label="Height (cm)")
    weight = forms.DecimalField(max_digits=8, decimal_places=3, required=False, label="Weight (kg)")


class ReturnInspectionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ("approve", "Approve RMA Request"),
            ("inspect", "Mark Under Inspection (Items Received)"),
            ("restock", "Complete & Restock Items to Inventory"),
            ("reject", "Reject RMA Request"),
        ],
        required=True,
        label="Inspection Action"
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Enter inspection notes, condition verification, or rejection reason..."}),
        required=False,
        label="Staff Inspection Notes"
    )
