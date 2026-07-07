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
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
    RegistrationSuccessView,
    RegistrationView,
    ResendVerificationView,
    VerifyEmailView,
    ProfileView,
    ProfileEditView,
    AddressListView,
    AddressCreateView,
    AddressUpdateView,
    AddressDeleteView,
    AddressSetDefaultView,
    AccountSettingsView,
    EmailChangeView,
    EmailChangeVerifyView,
    SessionManagementView,
    SessionRevokeView,
    SessionRevokeOthersView,
    AccountDeactivateView,
    AccountDeleteView,
)

app_name = "accounts"

urlpatterns = [
    # Authentication & Registration
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegistrationView.as_view(), name="register"),
    path("register/success/", RegistrationSuccessView.as_view(), name="register_success"),
    
    # Email Verification
    path("verify-email/<str:uidb64>/<str:token>/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend_verification"),
    
    # Password Reset (Forgot Password workflow)
    path("password-reset/", PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<str:uidb64>/<str:token>/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    
    # Password Change (Authenticated workflow)
    path("password/change/", PasswordChangeView.as_view(), name="password_change"),
    
    # Profile Management
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/edit/", ProfileEditView.as_view(), name="profile_edit"),
    
    # Address Book Management
    path("account/addresses/", AddressListView.as_view(), name="address_list"),
    path("account/addresses/add/", AddressCreateView.as_view(), name="address_create"),
    path("account/addresses/<int:pk>/edit/", AddressUpdateView.as_view(), name="address_edit"),
    path("account/addresses/<int:pk>/delete/", AddressDeleteView.as_view(), name="address_delete"),
    path("account/addresses/<int:pk>/set-default/<str:address_type>/", AddressSetDefaultView.as_view(), name="address_set_default"),
    
    # Account Security & Session Management
    path("account/settings/", AccountSettingsView.as_view(), name="settings"),
    path("account/settings/email-change/", EmailChangeView.as_view(), name="email_change"),
    path("account/settings/email-change/verify/<str:token>/", EmailChangeVerifyView.as_view(), name="verify_email_change"),
    path("account/sessions/", SessionManagementView.as_view(), name="sessions"),
    path("account/sessions/revoke/<str:session_key>/", SessionRevokeView.as_view(), name="session_revoke"),
    path("account/sessions/revoke-others/", SessionRevokeOthersView.as_view(), name="session_revoke_others"),
    path("account/deactivate/", AccountDeactivateView.as_view(), name="deactivate"),
    path("account/delete/", AccountDeleteView.as_view(), name="delete"),
]

