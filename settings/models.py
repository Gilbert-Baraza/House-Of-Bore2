# settings/models.py
"""
settings/models.py
──────────────────────────────────────────────────────────────────────────────
Centralized Store Configuration and Site Settings data models.

Implements a production-ready Singleton model (`StoreSettings`) that stores all
business configuration options (profile, branding, taxes, shipping, emails,
SEO, social links, maintenance mode, feature flags, and legal policies) without
requiring source code changes or environment variable modifications.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

CACHE_KEY_STORE_SETTINGS = "store_settings_singleton"
CACHE_TIMEOUT_STORE_SETTINGS = 60 * 60 * 24  # 24 hours (invalidated immediately on save)


class StoreSettings(models.Model):
    """
    Singleton configuration model storing all administrative store settings.
    Guarantees only one row (id=1) exists in the database.
    """
    CACHE_KEY = CACHE_KEY_STORE_SETTINGS
    # ─── 1. STORE PROFILE ────────────────────────────────────────────────────────
    store_name = models.CharField(
        _("Store Name"),
        max_length=150,
        default="House of Bore",
        help_text=_("Public display name shown on storefront navigation and browser tabs.")
    )
    business_name = models.CharField(
        _("Legal Business Name"),
        max_length=255,
        default="House of Bore Luxury Ltd.",
        help_text=_("Official corporate entity name used in invoices and legal documents.")
    )
    store_description = models.TextField(
        _("Store Description"),
        default="Premium luxury garments and bespoke fashion tailored for timeless silhouettes.",
        help_text=_("Brief overview of the store shown in footers and default metadata.")
    )
    logo = models.ImageField(
        _("Store Logo"),
        upload_to="branding/logos/",
        blank=True,
        null=True,
        help_text=_("Primary logo image (PNG or SVG recommended).")
    )
    favicon = models.ImageField(
        _("Store Favicon"),
        upload_to="branding/favicons/",
        blank=True,
        null=True,
        help_text=_("Small icon displayed in browser tabs (ICO or PNG 32x32).")
    )
    email = models.EmailField(
        _("General Contact Email"),
        default="concierge@houseofbore.com",
        help_text=_("Public contact email shown on contact page and customer inquiries.")
    )
    phone = models.CharField(
        _("Primary Telephone"),
        max_length=50,
        default="+254 700 000 000",
        help_text=_("Contact telephone number with country code.")
    )
    whatsapp = models.CharField(
        _("WhatsApp Business Number"),
        max_length=50,
        default="+254 700 000 000",
        help_text=_("WhatsApp contact number for instant concierge messaging.")
    )
    physical_address = models.TextField(
        _("Physical Address"),
        default="Bore House, 4th Floor, Kimathi Street, Nairobi, Kenya",
        help_text=_("Store or headquarters address displayed on invoices and contact page.")
    )
    business_hours = models.CharField(
        _("Business Operating Hours"),
        max_length=255,
        default="Mon - Sat: 9:00 AM - 6:00 PM EAT",
        help_text=_("Publicly displayed operating schedule.")
    )

    # ─── 2. BRANDING SETTINGS ────────────────────────────────────────────────────
    primary_color = models.CharField(
        _("Primary Brand Color (Hex)"),
        max_length=20,
        default="#1A1A1A",
        help_text=_("Primary color code for headers, footers, and major UI elements (e.g., #1A1A1A).")
    )
    secondary_color = models.CharField(
        _("Secondary Color (Hex)"),
        max_length=20,
        default="#4A4A4A",
        help_text=_("Secondary neutral color code for text and borders (e.g., #4A4A4A).")
    )
    accent_color = models.CharField(
        _("Accent / Gold Color (Hex)"),
        max_length=20,
        default="#C5A059",
        help_text=_("Highlight color code for buttons, badges, and accents (e.g., #C5A059).")
    )
    footer_text = models.TextField(
        _("Footer Tagline Text"),
        default="Crafted with intention, delivered with care. Exploring the intersection of heritage couture and modern comfort.",
        help_text=_("Descriptive text displayed in the footer brand column.")
    )
    announcement_banner_enabled = models.BooleanField(
        _("Enable Announcement Banner"),
        default=True,
        help_text=_("Display a top-of-page announcement bar across the storefront.")
    )
    announcement_banner_text = models.CharField(
        _("Announcement Banner Text"),
        max_length=255,
        default="Complimentary concierge delivery across East Africa on orders above KSh 50,000.",
        help_text=_("Promotional or informational text inside the top banner.")
    )
    default_placeholder_image = models.ImageField(
        _("Default Placeholder Image"),
        upload_to="branding/placeholders/",
        blank=True,
        null=True,
        help_text=_("Fallback image shown when products or variants lack uploaded media.")
    )

    # ─── 3. CURRENCY & TAX CONFIGURATION ─────────────────────────────────────────
    default_currency = models.CharField(
        _("Default Currency Code"),
        max_length=10,
        default="KES",
        help_text=_("ISO currency code (e.g., KES, USD, EUR, GBP).")
    )
    currency_symbol = models.CharField(
        _("Currency Symbol"),
        max_length=10,
        default="KSh",
        help_text=_("Symbol prepended to prices across the store (e.g., KSh, $, €).")
    )
    decimal_precision = models.PositiveSmallIntegerField(
        _("Decimal Precision"),
        default=2,
        help_text=_("Number of decimal digits shown on prices (typically 2, or 0 for whole currency units).")
    )
    tax_enabled = models.BooleanField(
        _("Enable Tax Calculations"),
        default=True,
        help_text=_("Whether value added tax (VAT/GST) is calculated on orders.")
    )
    tax_percentage = models.DecimalField(
        _("Tax Rate Percentage"),
        max_digits=5,
        decimal_places=2,
        default=16.00,
        help_text=_("Standard tax rate applied to taxable items (e.g., 16.00 for 16% VAT).")
    )
    TAX_DISPLAY_CHOICES = [
        ("inclusive", _("Inclusive of Tax (Prices displayed already include tax)")),
        ("exclusive", _("Exclusive of Tax (Tax added at checkout)")),
    ]
    tax_display_mode = models.CharField(
        _("Tax Display Mode"),
        max_length=20,
        choices=TAX_DISPLAY_CHOICES,
        default="inclusive",
        help_text=_("Determine whether storefront product prices are shown inclusive or exclusive of tax.")
    )

    # ─── 4. SHIPPING CONFIGURATION ───────────────────────────────────────────────
    free_shipping_threshold = models.DecimalField(
        _("Free Shipping Order Threshold"),
        max_digits=12,
        decimal_places=2,
        default=50000.00,
        help_text=_("Cart subtotal required for customer to qualify for free shipping.")
    )
    flat_shipping_rate = models.DecimalField(
        _("Standard Flat Shipping Rate"),
        max_digits=12,
        decimal_places=2,
        default=1500.00,
        help_text=_("Default shipping cost applied when order is below free shipping threshold.")
    )
    local_pickup_enabled = models.BooleanField(
        _("Enable Local Studio Pickup"),
        default=True,
        help_text=_("Allow customers to choose complimentary local pickup during checkout.")
    )
    estimated_delivery_message = models.CharField(
        _("Estimated Delivery Timeframe"),
        max_length=150,
        default="Standard Delivery: 2-4 Business Days",
        help_text=_("Public timeframe shown on product pages and checkout options.")
    )
    default_shipping_policy = models.TextField(
        _("Short Shipping Policy Summary"),
        default="Orders dispatched within 24 hours via insured courier service with signature confirmation upon arrival.",
        help_text=_("Concise shipping summary displayed in shipping drawers and cart.")
    )

    # ─── 5. EMAIL SETTINGS ───────────────────────────────────────────────────────
    store_sender_name = models.CharField(
        _("Store Sender Name"),
        max_length=150,
        default="House of Bore Concierge",
        help_text=_("Name displayed as the sender on automated order and account emails.")
    )
    reply_to_email = models.EmailField(
        _("Reply-To Email Address"),
        default="support@houseofbore.com",
        help_text=_("Address where customer replies to automated notifications are directed.")
    )
    customer_support_email = models.EmailField(
        _("Customer Support Email"),
        default="support@houseofbore.com",
        help_text=_("Dedicated customer support inbox address.")
    )
    order_notification_recipients = models.TextField(
        _("Order Notification Recipients"),
        default="orders@houseofbore.com",
        help_text=_("Comma-separated list of staff email addresses that receive alert notifications when new orders are placed.")
    )

    # ─── 6. SEO DEFAULTS ─────────────────────────────────────────────────────────
    default_meta_title = models.CharField(
        _("Default Meta Title"),
        max_length=200,
        default="House of Bore | Luxury Garments & Bespoke Fashion",
        help_text=_("Default title tag when a specific product or page title is not set.")
    )
    default_meta_description = models.TextField(
        _("Default Meta Description"),
        default="Explore House of Bore's exquisite collection of luxury garments, tailored silhouettes, and timeless couture.",
        help_text=_("Default meta description used by search engines and social cards.")
    )
    default_og_image = models.ImageField(
        _("Default Open Graph Share Image"),
        upload_to="branding/seo/",
        blank=True,
        null=True,
        help_text=_("Image displayed when pages are shared on social media (1200x630 recommended).")
    )
    default_social_share_description = models.TextField(
        _("Default Social Share Description"),
        default="Discover luxury fashion and timeless elegance at House of Bore.",
        help_text=_("Brief description snippet used for social graph sharing cards.")
    )
    ROBOTS_CHOICES = [
        ("index, follow", _("Index, Follow (Recommended for Production Storefront)")),
        ("noindex, nofollow", _("NoIndex, NoFollow (Recommended for Staging / Private)")),
        ("index, nofollow", _("Index, NoFollow")),
    ]
    robots_index_preference = models.CharField(
        _("Robots Indexing Preference"),
        max_length=50,
        choices=ROBOTS_CHOICES,
        default="index, follow",
        help_text=_("Instructs web crawlers and search engines whether to index the site.")
    )

    # ─── 7. SOCIAL MEDIA LINKS ───────────────────────────────────────────────────
    facebook_url = models.URLField(
        _("Facebook URL"),
        blank=True,
        default="https://facebook.com/houseofbore",
        help_text=_("Full URL to Facebook page.")
    )
    instagram_url = models.URLField(
        _("Instagram URL"),
        blank=True,
        default="https://instagram.com/houseofbore",
        help_text=_("Full URL to Instagram profile.")
    )
    twitter_url = models.URLField(
        _("X (Twitter) URL"),
        blank=True,
        default="https://x.com/houseofbore",
        help_text=_("Full URL to X / Twitter profile.")
    )
    tiktok_url = models.URLField(
        _("TikTok URL"),
        blank=True,
        default="https://tiktok.com/@houseofbore",
        help_text=_("Full URL to TikTok profile.")
    )
    youtube_url = models.URLField(
        _("YouTube Channel URL"),
        blank=True,
        default="https://youtube.com/@houseofbore",
        help_text=_("Full URL to YouTube channel.")
    )
    linkedin_url = models.URLField(
        _("LinkedIn Company URL"),
        blank=True,
        default="https://linkedin.com/company/houseofbore",
        help_text=_("Full URL to LinkedIn company page.")
    )

    # ─── 8. MAINTENANCE MODE ─────────────────────────────────────────────────────
    maintenance_mode_enabled = models.BooleanField(
        _("Enable Public Maintenance Mode"),
        default=False,
        help_text=_("If active, public visitors will see a branded maintenance page (503 status). Staff members can still access all pages normally.")
    )
    maintenance_message = models.TextField(
        _("Maintenance Page Message"),
        default="Our digital flagship is undergoing seasonal curation and upgrades. We will return shortly.",
        help_text=_("Custom message displayed to visitors on the maintenance screen.")
    )
    maintenance_return_date = models.DateTimeField(
        _("Expected Return Date & Time"),
        blank=True,
        null=True,
        help_text=_("Optional date and time when the store is scheduled to reopen.")
    )

    # ─── 9. FEATURE FLAGS ────────────────────────────────────────────────────────
    feature_wishlist = models.BooleanField(
        _("Wishlist Feature"),
        default=True,
        help_text=_("Allow customers to save products to their personal wishlists.")
    )
    feature_reviews = models.BooleanField(
        _("Product Reviews & Ratings"),
        default=True,
        help_text=_("Allow customers to submit and view ratings and reviews on product pages.")
    )
    feature_compare = models.BooleanField(
        _("Product Comparison Tool"),
        default=True,
        help_text=_("Enable the floating comparison drawer and side-by-side spec comparison.")
    )
    feature_recently_viewed = models.BooleanField(
        _("Recently Viewed Products"),
        default=True,
        help_text=_("Track and display recently viewed product history to visitors.")
    )
    feature_promotions = models.BooleanField(
        _("Promotions & Discount Engine"),
        default=True,
        help_text=_("Enable coupon code redemption and promotional discount calculations.")
    )
    feature_guest_checkout = models.BooleanField(
        _("Guest Checkout"),
        default=True,
        help_text=_("Allow visitors to complete orders without registering for a customer account.")
    )

    # ─── 10. STORE POLICIES ──────────────────────────────────────────────────────
    privacy_policy = models.TextField(
        _("Privacy Policy Content"),
        default="### Privacy Policy\n\nHouse of Bore treats patron data with the utmost discretion. We collect and process personal details strictly for order fulfillment, personalized concierge services, and secure authentication.",
        help_text=_("Full legal text for the Privacy Policy (Supports Markdown formatting).")
    )
    terms_and_conditions = models.TextField(
        _("Terms & Conditions Content"),
        default="### Terms & Conditions\n\nBy accessing or purchasing from House of Bore, you agree to our terms of service regarding luxury bespoke tailoring, intellectual property rights, and payment verification.",
        help_text=_("Full legal text for Terms & Conditions (Supports Markdown formatting).")
    )
    shipping_policy = models.TextField(
        _("Full Shipping Policy Content"),
        default="### Shipping Policy\n\nAll deliveries are fully insured from our Nairobi flagship studio to your designated address. Signature verification is mandatory upon receipt of all couture packages.",
        help_text=_("Full legal text for Shipping Policy (Supports Markdown formatting).")
    )
    returns_policy = models.TextField(
        _("Returns Policy Content"),
        default="### Returns Policy\n\nGarments returned in pristine, unworn condition with original authenticity seals within 14 days of receipt are eligible for exchange or store credit.",
        help_text=_("Full legal text for Returns & Exchanges Policy (Supports Markdown formatting).")
    )
    refund_policy = models.TextField(
        _("Refund Policy Content"),
        default="### Refund Policy\n\nApproved refunds are processed to the original payment method within 5-7 business days after technical inspection of returned garments.",
        help_text=_("Full legal text for Refund Policy (Supports Markdown formatting).")
    )

    updated_at = models.DateTimeField(_("Last Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Store Settings")
        verbose_name_plural = _("Store Settings")
        permissions = [
            ("manage_branding", _("Can manage store branding & theme colors")),
            ("manage_policies", _("Can edit legal store policies")),
            ("toggle_maintenance", _("Can enable or disable public maintenance mode")),
            ("manage_featureflags", _("Can toggle store feature flags")),
        ]

    def __str__(self) -> str:
        return f"Store Settings ({self.store_name})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Enforce singleton constraint (pk=1) and invalidate cache on save.
        """
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY_STORE_SETTINGS)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """
        Prevent deletion of the singleton StoreSettings instance.
        """
        raise ValidationError(_("The primary StoreSettings configuration cannot be deleted."))

    @classmethod
    def load(cls) -> "StoreSettings":
        """
        Retrieve the singleton instance from cache or database.
        Creates a default instance if none exists yet.
        """
        instance = cache.get(CACHE_KEY_STORE_SETTINGS)
        if instance is None:
            instance, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY_STORE_SETTINGS, instance, CACHE_TIMEOUT_STORE_SETTINGS)
        return instance
