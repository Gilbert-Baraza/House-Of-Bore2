from django import forms

from .models import Inventory


class InventoryAdjustmentForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, required=True, label="Quantity")
    reason = forms.CharField(max_length=120, required=True, label="Reason")
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Notes")
    action = forms.ChoiceField(choices=[("increase", "Increase"), ("decrease", "Decrease"), ("correction", "Correction"), ("damage", "Damage"), ("return", "Return")])
