# pricing/forms.py
"""
pricing/forms.py
──────────────────────────────────────────────────────────────────────────────
Forms for coupon code submission and validation.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms


class CouponApplyForm(forms.Form):
    """
    Form for applying a promotional discount code inside cart or checkout.
    """
    code = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            "class": "w-full px-4 py-2.5 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-accent-500 text-xs font-mono uppercase tracking-wider",
            "placeholder": "PROMO CODE",
            "autocomplete": "off",
        })
    )

    def clean_code(self) -> str:
        return self.cleaned_data["code"].strip().upper()
