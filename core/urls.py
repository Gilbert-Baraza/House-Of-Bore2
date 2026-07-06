# core/urls.py
"""
URL configuration for the core marketing application.
"""

from django.urls import path
from core.views import AboutView, ContactView, HomeView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("about/", AboutView.as_view(), name="about"),
    path("contact/", ContactView.as_view(), name="contact"),
]
