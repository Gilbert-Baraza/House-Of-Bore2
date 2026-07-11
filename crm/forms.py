# crm/forms.py
"""
crm/forms.py
──────────────────────────────────────────────────────────────────────────────
Forms for administrative staff notes and manual interaction logs.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms
from .models import CustomerInteractionRecord, CustomerStaffNote


class CustomerStaffNoteForm(forms.ModelForm):
    """
    Form for creating or modifying a private staff-only customer note.
    """
    class Meta:
        model = CustomerStaffNote
        fields = ["note", "category", "is_pinned"]
        widgets = {
            "note": forms.Textarea(attrs={
                "rows": 4,
                "class": "w-full rounded-xl border border-neutral-300 p-3 text-xs focus:ring-2 focus:ring-amber-500",
                "placeholder": "Enter private staff note, VIP preference, or interaction summary...",
            }),
            "category": forms.Select(attrs={
                "class": "w-full rounded-xl border border-neutral-300 px-3 py-2 text-xs font-semibold text-neutral-900 focus:ring-2 focus:ring-amber-500",
            }),
            "is_pinned": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-amber-600 focus:ring-amber-500",
            }),
        }


class CustomerInteractionRecordForm(forms.ModelForm):
    """
    Form for recording an offline or manual concierge communication event.
    """
    class Meta:
        model = CustomerInteractionRecord
        fields = ["interaction_type", "summary", "details", "timestamp"]
        widgets = {
            "interaction_type": forms.Select(attrs={
                "class": "w-full rounded-xl border border-neutral-300 px-3 py-2 text-xs font-semibold text-neutral-900 focus:ring-2 focus:ring-amber-500",
            }),
            "summary": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-neutral-300 px-3 py-2 text-xs focus:ring-2 focus:ring-amber-500",
                "placeholder": "e.g. Phone verification regarding high-value wire transfer",
            }),
            "details": forms.Textarea(attrs={
                "rows": 3,
                "class": "w-full rounded-xl border border-neutral-300 p-3 text-xs focus:ring-2 focus:ring-amber-500",
                "placeholder": "Optional detailed notes on the interaction...",
            }),
            "timestamp": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "w-full rounded-xl border border-neutral-300 px-3 py-2 text-xs focus:ring-2 focus:ring-amber-500",
            }),
        }
