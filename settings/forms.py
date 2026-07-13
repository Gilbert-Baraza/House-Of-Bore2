# settings/forms.py
"""
settings/forms.py
──────────────────────────────────────────────────────────────────────────────
Dashboard form classes for modifying sections of the StoreSettings singleton.

Provides 10 focused `ModelForm` classes styled with Tailwind CSS (`form-input`,
`form-textarea`, `form-checkbox`, `form-select`), accessible labels, and clear
validation constraints.
──────────────────────────────────────────────────────────────────────────────
"""

from django import forms
from .models import StoreSettings


class BaseSettingsModelForm(forms.ModelForm):
    """
    Base form applying Tailwind utility styling across all form elements automatically.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-checkbox h-5 w-5 text-accent-500 rounded border-neutral-300 focus:ring-accent-500"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = "form-select w-full rounded-md border-neutral-300 bg-white py-2 px-3 text-neutral-800 shadow-sm focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500 text-sm"
            elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
                widget.attrs["class"] = "block w-full text-sm text-neutral-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-accent-50 file:text-accent-700 hover:file:bg-accent-100 cursor-pointer border border-neutral-200 rounded-md"
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = "form-textarea block w-full rounded-md border-neutral-300 py-2 px-3 text-neutral-800 shadow-sm focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500 text-sm font-mono"
                widget.attrs["rows"] = 5
            else:
                widget.attrs["class"] = "form-input block w-full rounded-md border-neutral-300 py-2 px-3 text-neutral-800 shadow-sm focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500 text-sm"


class StoreProfileForm(BaseSettingsModelForm):
    """
    Form for editing general store information, contact details, and brand logos.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "store_name",
            "business_name",
            "store_description",
            "email",
            "phone",
            "whatsapp",
            "physical_address",
            "business_hours",
            "logo",
            "favicon",
        ]
        widgets = {
            "store_description": forms.Textarea(attrs={"rows": 3}),
            "physical_address": forms.Textarea(attrs={"rows": 2}),
        }


class BrandingForm(BaseSettingsModelForm):
    """
    Form for configuring theme colors, footer copy, and announcement banner.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "primary_color",
            "secondary_color",
            "accent_color",
            "footer_text",
            "announcement_banner_enabled",
            "announcement_banner_text",
            "default_placeholder_image",
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-24 p-1 rounded border border-neutral-300 cursor-pointer"}),
            "secondary_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-24 p-1 rounded border border-neutral-300 cursor-pointer"}),
            "accent_color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-24 p-1 rounded border border-neutral-300 cursor-pointer"}),
            "footer_text": forms.Textarea(attrs={"rows": 3}),
        }


class CurrencyTaxForm(BaseSettingsModelForm):
    """
    Form for configuring default currency codes, precision, and VAT/GST tax settings.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "default_currency",
            "currency_symbol",
            "decimal_precision",
            "tax_enabled",
            "tax_percentage",
            "tax_display_mode",
        ]


class ShippingSettingsForm(BaseSettingsModelForm):
    """
    Form for configuring free shipping thresholds, flat shipping rates, and delivery messages.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "free_shipping_threshold",
            "flat_shipping_rate",
            "local_pickup_enabled",
            "estimated_delivery_message",
            "default_shipping_policy",
        ]
        widgets = {
            "default_shipping_policy": forms.Textarea(attrs={"rows": 3}),
        }


class EmailSettingsForm(BaseSettingsModelForm):
    """
    Form for modifying automated email sender names, reply-to addresses, and notification recipients.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "store_sender_name",
            "reply_to_email",
            "customer_support_email",
            "order_notification_recipients",
        ]
        widgets = {
            "order_notification_recipients": forms.Textarea(attrs={"rows": 2, "placeholder": "orders@houseofbore.com, warehouse@houseofbore.com"}),
        }


class SeoDefaultsForm(BaseSettingsModelForm):
    """
    Form for setting default search engine metadata, Open Graph images, and crawler rules.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "default_meta_title",
            "default_meta_description",
            "default_og_image",
            "default_social_share_description",
            "robots_index_preference",
        ]
        widgets = {
            "default_meta_description": forms.Textarea(attrs={"rows": 3}),
            "default_social_share_description": forms.Textarea(attrs={"rows": 2}),
        }


class SocialMediaForm(BaseSettingsModelForm):
    """
    Form for managing storefront footer and contact page social media links.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "facebook_url",
            "instagram_url",
            "twitter_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
        ]


class FeatureFlagsForm(BaseSettingsModelForm):
    """
    Form for enabling or disabling optional storefront features dynamically.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "feature_wishlist",
            "feature_reviews",
            "feature_compare",
            "feature_recently_viewed",
            "feature_promotions",
            "feature_guest_checkout",
        ]


class MaintenanceModeForm(BaseSettingsModelForm):
    """
    Form for controlling global storefront maintenance mode and reopening schedules.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "maintenance_mode_enabled",
            "maintenance_message",
            "maintenance_return_date",
        ]
        widgets = {
            "maintenance_message": forms.Textarea(attrs={"rows": 4}),
            "maintenance_return_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.maintenance_return_date:
            # Format datetime for datetime-local input widget
            self.initial["maintenance_return_date"] = self.instance.maintenance_return_date.strftime("%Y-%m-%dT%H:%M")


class StorePoliciesForm(BaseSettingsModelForm):
    """
    Form for editing store legal policies using markdown/rich text formatting.
    """
    class Meta:
        model = StoreSettings
        fields = [
            "privacy_policy",
            "terms_and_conditions",
            "shipping_policy",
            "returns_policy",
            "refund_policy",
        ]
