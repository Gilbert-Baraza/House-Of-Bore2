# core/views.py
"""
Class-based views for the core marketing application.
"""

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView
from core.forms import ContactForm


class HomeView(TemplateView):
    """
    Renders the public homepage with structured context for categories,
    features, preview products, and testimonials.
    """
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Featured Categories (6 cards)
        context["featured_categories"] = [
            {
                "name": "Men's Collection",
                "description": "Architectural outerwear, unstructured tailoring, and relaxed wool trousers engineered for enduring modern elegance.",
                "image_alt": "Men's Collection apparel",
                "badge": "New Season",
                "url": "/categories/",
            },
            {
                "name": "Women's Collection",
                "description": "Effortless silhouettes featuring draped silk blouses, cashmere knitwear, and structured weatherproof trench coats.",
                "image_alt": "Women's Collection apparel",
                "badge": "Popular",
                "url": "/categories/",
            },
            {
                "name": "Footwear",
                "description": "Bench-made Chelsea boots, minimal suede loafers, and low-profile leather trainers crafted for exceptional all-day comfort.",
                "image_alt": "Bench-made Footwear collection",
                "url": "/categories/",
            },
            {
                "name": "Leather Goods",
                "description": "Full-grain vegetable-tanned weekend duffels, structured briefcases, and minimal wallets designed to develop a rich patina over decades.",
                "image_alt": "Full-grain Leather Goods collection",
                "url": "/categories/",
            },
            {
                "name": "Seasonal Essentials",
                "description": "Heavyweight Scottish cashmere turtlenecks, merino beanies, and water-repellent outerwear engineered for unpredictable climates.",
                "image_alt": "Seasonal Essentials collection",
                "badge": "Limited",
                "url": "/categories/",
            },
            {
                "name": "New Arrivals",
                "description": "The latest additions to our permanent wardrobe, featuring limited-run Japanese selvedge denim and lightweight linen overshirts.",
                "image_alt": "New Arrivals wardrobe collection",
                "badge": "Just Dropped",
                "url": "/products/?sort=newest",
            },
        ]

        # 2. Why Choose Us (4 feature cards)
        context["why_choose_us"] = [
            {
                "title": "Uncompromising Quality",
                "description": "Every garment and artifact is crafted from certified ethical, heritage-grade natural fibers.",
                "icon_name": "quality",
            },
            {
                "title": "Complimentary Shipping",
                "description": "Express carbon-neutral delivery on all global orders over $200 with signature tracking.",
                "icon_name": "shipping",
            },
            {
                "title": "Lifetime Guarantee",
                "description": "We stand by our craftsmanship with complimentary repairs and restoration for life.",
                "icon_name": "guarantee",
            },
            {
                "title": "Concierge Support",
                "description": "Dedicated personal styling and 24/7 client care available via private chat and phone.",
                "icon_name": "support",
            },
        ]

        # 3. Featured Products Preview (4 cards)
        context["featured_products"] = [
            {
                "name": "The Weatherproof Trench Coat",
                "price": "$680",
                "rating": 4.9,
                "reviews_count": 42,
                "badge": "Best Seller",
                "image_alt": "Weatherproof Trench Coat in Camel",
                "url": "/products/",
            },
            {
                "name": "Heavyweight Cashmere Turtleneck",
                "price": "$340",
                "rating": 4.8,
                "reviews_count": 86,
                "badge": "New Arrival",
                "image_alt": "Cashmere Turtleneck Sweater in Charcoal",
                "url": "/products/",
            },
            {
                "name": "Full-Grain Weekender Duffel",
                "price": "$850",
                "rating": 5.0,
                "reviews_count": 19,
                "badge": "Handcrafted",
                "image_alt": "Leather Weekender Bag in Espresso",
                "url": "/products/",
            },
            {
                "name": "Pleated Italian Wool Trousers",
                "price": "$290",
                "rating": 4.9,
                "reviews_count": 31,
                "badge": "Limited Edition",
                "image_alt": "Pleated Italian Wool Trousers in Navy",
                "url": "/products/",
            },
        ]

        # 4. Testimonials (3 cards)
        context["testimonials"] = [
            {
                "quote": "The attention to detail in the stitching and fabric weight is extraordinary. House of Bore has completely elevated my everyday uniform.",
                "author": "Julian Sterling",
                "title": "Architect & Designer, New York",
            },
            {
                "quote": "In an era of disposable fashion, finding pieces that actually look and feel better after three years of wear is a rare revelation.",
                "author": "Elena Rostova",
                "title": "Creative Director, London",
            },
            {
                "quote": "The customer concierge service is flawless. From sizing advice to overnight delivery for my gallery opening, the experience was peerless.",
                "author": "Marcus Thorne",
                "title": "Art Collector, Tokyo",
            },
        ]

        return context


class AboutView(TemplateView):
    """
    Renders the company story, mission, values, statistics, and team placeholders.
    """
    template_name = "core/about.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Values
        context["values"] = [
            {
                "title": "Intention Over Trend",
                "description": "We reject fast cycles in favor of timeless silhouettes designed to remain relevant for generations.",
            },
            {
                "title": "Radical Transparency",
                "description": "We disclose every mill, tannery, and workshop in our supply chain alongside honest pricing models.",
            },
            {
                "title": "Ecological Stewardship",
                "description": "100% biodegradable packaging, zero-waste cutting patterns, and renewable energy across all operations.",
            },
            {
                "title": "Master Craftsmanship",
                "description": "Partnering exclusively with multi-generational family workshops in Italy, Scotland, and Japan.",
            },
        ]

        # Statistics
        context["stats"] = [
            {"value": "15+", "label": "Years of Heritage"},
            {"value": "100%", "label": "Ethical Traceability"},
            {"value": "40k+", "label": "Discerning Clients"},
            {"value": "0", "label": "Landfill Waste"},
        ]

        # Team placeholders
        context["team"] = [
            {
                "name": "Eleanor Vance",
                "role": "Founder & Creative Director",
                "bio": "Former head of menswear at leading Parisian fashion houses with a passion for architectural tailoring.",
            },
            {
                "name": "Marcus Sterling",
                "role": "Head of Design & Textiles",
                "bio": "Textile engineer specializing in heritage wool weaves and sustainable natural fiber innovation.",
            },
            {
                "name": "Clara Chen",
                "role": "Master of Leather Craft",
                "bio": "Second-generation leather artisan overseeing our Florentine tannery and workshop partnerships.",
            },
        ]

        return context


class ContactView(FormView):
    """
    Renders the contact form and business hours.
    Handles form submission validation without sending emails in Phase 1.5.
    """
    template_name = "core/contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("core:contact")

    def form_valid(self, form):
        # In Phase 1.5, we acknowledge the submission via Django flash messages.
        name = form.cleaned_data.get("name")
        messages.success(
            self.request,
            f"Thank you, {name}. Your inquiry has been received by our concierge team. We will respond within 24 hours."
        )
        return super().form_valid(form)
