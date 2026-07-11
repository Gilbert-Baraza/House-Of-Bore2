# dashboard/forms.py
"""
dashboard/forms.py
──────────────────────────────────────────────────────────────────────────────
Forms for the Custom Administration Dashboard staff profile management.

Includes:
1. StaffContactForm: Update contact details (`phone_number`).
2. StaffAvatarForm: Upload and validate staff avatar image.
3. StaffPreferenceForm: Configure alert channels and dark mode preferences.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import UserProfile
from .models import StaffPreference


class StaffContactForm(forms.ModelForm):
    """
    Form allowing staff members to update their contact details.
    """
    class Meta:
        model = UserProfile
        fields = ["phone_number"]
        widgets = {
            "phone_number": forms.TextInput(
                attrs={
                    "class": "block w-full rounded-md border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-900",
                    "placeholder": "+1 (555) 000-0000",
                }
            )
        }


class StaffAvatarForm(forms.ModelForm):
    """
    Form allowing staff members to update their profile avatar.
    """
    class Meta:
        model = UserProfile
        fields = ["avatar"]
        widgets = {
            "avatar": forms.FileInput(
                attrs={
                    "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer",
                }
            )
        }


class StaffPreferenceForm(forms.ModelForm):
    """
    Form allowing staff members to customize their alert frequencies and UI theme.
    """
    class Meta:
        model = StaffPreference
        fields = [
            "email_alerts",
            "low_stock_alerts",
            "new_order_alerts",
            "system_notification_alerts",
            "dark_mode",
        ]
        widgets = {
            "email_alerts": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900"}),
            "low_stock_alerts": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900"}),
            "new_order_alerts": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900"}),
            "system_notification_alerts": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900"}),
            "dark_mode": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900"}),
        }
