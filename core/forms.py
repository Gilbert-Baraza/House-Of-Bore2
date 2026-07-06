# core/forms.py
"""
Core forms for public marketing pages.
"""

from django import forms


class ContactForm(forms.Form):
    """
    Contact form for customer inquiries.
    Does not send emails yet in Phase 1.5; validates input and provides structure.
    """
    INQUIRY_CHOICES = [
        ("", "Select a topic"),
        ("order", "Order Status & Shipping"),
        ("product", "Product Information"),
        ("returns", "Returns & Exchanges"),
        ("press", "Press & Media"),
        ("other", "General Inquiry"),
    ]

    name = forms.CharField(
        max_length=100,
        label="Your Name",
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "e.g. Eleanor Vance",
            "autocomplete": "name",
        }),
    )
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            "class": "form-input",
            "placeholder": "name@example.com",
            "autocomplete": "email",
        }),
    )
    subject = forms.ChoiceField(
        choices=INQUIRY_CHOICES,
        label="Subject",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )
    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={
            "class": "form-textarea form-input",
            "placeholder": "How can we assist you today?",
            "rows": 5,
        }),
    )
