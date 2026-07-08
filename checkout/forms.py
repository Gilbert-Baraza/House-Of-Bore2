# checkout/forms.py
"""
checkout/forms.py
──────────────────────────────────────────────────────────────────────────────
Validation forms for shipping, billing, and checkout notes.
Extends AriaErrorHighlightFormMixin to provide accessible UI styling and screen
reader guidance for error feedback.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms
from django.core.exceptions import ValidationError
from accounts.forms import AriaErrorHighlightFormMixin
from checkout.models import CheckoutAddress
import re


class CheckoutAddressForm(AriaErrorHighlightFormMixin, forms.ModelForm):
    """
    Form for validating shipping or billing addresses during checkout.
    Handles international address checks, phone formatting, and ARIA markup.
    """
    class Meta:
        model = CheckoutAddress
        fields = [
            "recipient_name",
            "phone_number",
            "company_name",
            "address_line_1",
            "address_line_2",
            "city",
            "county_or_state",
            "postal_code",
            "country",
        ]
        widgets = {
            "recipient_name": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "Recipient's full name",
                "autocomplete": "name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "e.g., +1 555-0199",
                "autocomplete": "tel",
            }),
            "company_name": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "Company name (optional)",
                "autocomplete": "organization",
            }),
            "address_line_1": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "Street address, P.O. box",
                "autocomplete": "address-line1",
            }),
            "address_line_2": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "Apartment, suite, unit (optional)",
                "autocomplete": "address-line2",
            }),
            "city": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "City",
                "autocomplete": "address-level2",
            }),
            "county_or_state": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "State / Province / County",
                "autocomplete": "address-level1",
            }),
            "postal_code": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
                "placeholder": "Postal or ZIP code",
                "autocomplete": "postal-code",
            }),
            "country": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 focus:outline-none focus:ring-2 focus:ring-accent-500 text-sm cursor-pointer",
                "autocomplete": "country",
            }),
        }

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "").strip()
        if not re.match(r"^\+?[\d\s\-\(\)\.]{7,25}$", phone):
            raise ValidationError("Please enter a valid international phone number (e.g., +1 555-0199 or +44 20 7946 0999).")
        return phone

    def clean(self) -> dict:
        cleaned_data = super().clean()
        postal = cleaned_data.get("postal_code", "").strip() if cleaned_data.get("postal_code") else ""
        country = cleaned_data.get("country", "")
        if country in ("US", "CA", "GB", "FR", "IT", "DE", "CH", "JP", "AU") and not postal:
            self.add_error("postal_code", "Postal code is required for the selected country.")
        return cleaned_data


class CheckoutNotesForm(forms.Form):
    """
    Form for capturing optional order notes and delivery instructions.
    """
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500/50 text-sm",
            "placeholder": "Order notes (e.g., special instructions for delivery)",
            "rows": 3,
        })
    )
