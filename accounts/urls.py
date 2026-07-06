# accounts/urls.py
"""
accounts/urls.py
──────────────────────────────────────────────────────────────────────────────
URL routing for customer authentication and account management.

Namespace: "accounts"
──────────────────────────────────────────────────────────────────────────────
"""

from django.urls import path
from accounts.views import (
    LoginView,
    LogoutView,
    RegistrationSuccessView,
    RegistrationView,
    ResendVerificationView,
    VerifyEmailView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegistrationView.as_view(), name="register"),
    path("register/success/", RegistrationSuccessView.as_view(), name="register_success"),
    path("verify-email/<str:uidb64>/<str:token>/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend_verification"),
]
