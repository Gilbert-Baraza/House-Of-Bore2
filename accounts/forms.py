# accounts/forms.py
"""
accounts/forms.py
──────────────────────────────────────────────────────────────────────────────
Registration and authentication forms for House of Bore.

Enforces server-side validation including duplicate email/username detection,
Django password validation framework, password confirmation matching, and
mandatory acceptance of legal terms and privacy policy.
──────────────────────────────────────────────────────────────────────────────
"""

from typing import Any, Dict, Optional
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.selectors import email_exists, get_users_for_password_reset, username_exists
from accounts.services import send_password_reset_email
from accounts.models import UserProfile, Address

User = get_user_model()


class AriaErrorHighlightFormMixin:
    """
    Reusable form mixin that automatically attaches ARIA accessibility attributes
    (aria-invalid, aria-describedby) and visual error styling classes to form widgets
    when validation errors occur.
    """
    def full_clean(self) -> None:
        super().full_clean()  # type: ignore[misc]
        fields_to_mark = list(getattr(self, "errors", {}).keys())
        if "__all__" in fields_to_mark:
            for fallback_field in ["email", "password", "old_password"]:
                if fallback_field in getattr(self, "fields", {}):
                    fields_to_mark.append(fallback_field)

        for field_name in set(fields_to_mark):
            if field_name in getattr(self, "fields", {}):
                field = self.fields[field_name]  # type: ignore[attr-defined]
                field_id = field.widget.attrs.get("id") or f"id_{field_name}"
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"{field_id}_error"
                
                existing_class = field.widget.attrs.get("class", "")
                if "border-neutral-300" in existing_class:
                    field.widget.attrs["class"] = existing_class.replace(
                        "border-neutral-300", "border-red-500 text-red-900 focus:ring-red-500"
                    )


class UserRegistrationForm(AriaErrorHighlightFormMixin, forms.ModelForm):
    """
    Customer registration form.
    
    Includes email, password, password confirmation, optional phone number,
    and required legal consent checkboxes.
    """
    email = forms.EmailField(
        label="Email Address",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        ),
        error_messages={
            "required": "Please enter your email address.",
            "invalid": "Please enter a valid email address.",
        },
    )

    phone = forms.CharField(
        label="Phone Number (Optional)",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "+1 (555) 000-0000",
                "autocomplete": "tel",
            }
        ),
    )

    password = forms.CharField(
        label="Password",
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "••••••••••••",
                "autocomplete": "new-password",
            }
        ),
        error_messages={
            "required": "Please create a password.",
        },
    )

    confirm_password = forms.CharField(
        label="Confirm Password",
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "••••••••••••",
                "autocomplete": "new-password",
            }
        ),
        error_messages={
            "required": "Please confirm your password.",
        },
    )

    terms_accepted = forms.BooleanField(
        label="I agree to the Terms & Conditions",
        required=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-primary-900 focus:ring-primary-900 transition-colors cursor-pointer",
            }
        ),
        error_messages={
            "required": "You must accept the Terms & Conditions to create an account.",
        },
    )

    privacy_accepted = forms.BooleanField(
        label="I agree to the Privacy Policy",
        required=True,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-primary-900 focus:ring-primary-900 transition-colors cursor-pointer",
            }
        ),
        error_messages={
            "required": "You must accept the Privacy Policy to create an account.",
        },
    )

    class Meta:
        model = User
        fields = ["email"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        
        # Adaptive check: If the User model explicitly has a username field, add it to the form
        if hasattr(User, "username") and getattr(User, "username", None) is not None:
            self.fields["username"] = forms.CharField(
                label="Username",
                required=True,
                widget=forms.TextInput(
                    attrs={
                        "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                        "placeholder": "Choose a username",
                        "autocomplete": "username",
                    }
                ),
            )

    def clean_email(self) -> str:
        """
        Validate email format and check for duplicates.
        """
        email = self.cleaned_data.get("email", "").strip().lower()
        if email_exists(email):
            raise ValidationError(
                "An account with this email address already exists. Please log in instead.",
                code="duplicate_email"
            )
        return email

    def clean_username(self) -> str:
        """
        Validate username if present on the schema.
        """
        username = self.cleaned_data.get("username", "").strip()
        if username and username_exists(username):
            raise ValidationError(
                "This username is already taken. Please choose another.",
                code="duplicate_username"
            )
        return username

    def clean_password(self) -> str:
        """
        Validate password strength using Django's password validation framework.
        """
        password = self.cleaned_data.get("password")
        email = self.cleaned_data.get("email", "")
        
        # Create a temporary user instance for validators that check password against user attributes
        temp_user = User(email=email)
        if hasattr(temp_user, "username") and getattr(User, "username", None) is not None:
            temp_user.username = self.cleaned_data.get("username", "")  # type: ignore[attr-defined]

        if password:
            password_validation.validate_password(password, user=temp_user)
        return password or ""

    def clean(self) -> Dict[str, Any]:
        """
        Cross-field validation: confirm passwords match.
        """
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error(
                "confirm_password",
                ValidationError("The two password fields didn't match.", code="password_mismatch")
            )

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
        """
        Save is overridden in Phase 3.1 to delegate instantiation to services.py
        when invoked from views. This ModelForm save is provided for compatibility.
        """
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.is_active = True
        
        phone = self.cleaned_data.get("phone")
        if phone and hasattr(user, "phone"):
            setattr(user, "phone", phone)
            
        if commit:
            user.save()
        return user


class UserLoginForm(AriaErrorHighlightFormMixin, forms.Form):
    """
    Custom authentication form supporting email login and 'Remember Me'.
    """
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-3 bg-neutral-50 border border-neutral-300 rounded-btn text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all",
                "placeholder": "patron@houseofbore.com",
                "autocomplete": "email",
                "required": True,
            }
        ),
        error_messages={
            "required": "Please enter your email address.",
            "invalid": "Please enter a valid email address.",
        },
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-neutral-50 border border-neutral-300 rounded-btn text-sm text-neutral-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all",
                "placeholder": "••••••••••••",
                "autocomplete": "current-password",
                "required": True,
            }
        ),
        error_messages={
            "required": "Please enter your password.",
        },
    )
    remember_me = forms.BooleanField(
        label="Remember Me for 30 days",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-primary-900 focus:ring-primary-900 transition-colors cursor-pointer",
            }
        ),
    )

    def __init__(self, request: Optional[HttpRequest] = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.user_cache: Optional[Any] = None
        super().__init__(*args, **kwargs)

    def clean(self) -> Dict[str, Any]:
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(self.request, email=email, password=password)
            if self.user_cache is None:
                raise ValidationError(
                    "Invalid email address or password. Please check your credentials and try again.",
                    code="invalid_login",
                )
            elif not self.user_cache.is_active:
                raise ValidationError(
                    "This account has been deactivated. Please contact concierge support.",
                    code="inactive",
                )
        return cleaned_data

    def get_user(self) -> Any:
        return self.user_cache


class UserPasswordResetForm(AriaErrorHighlightFormMixin, forms.Form):
    """
    Form for requesting a password reset email.
    
    Crucially, to prevent user enumeration attacks, this form never reveals
    whether an email address exists in the system. It always validates successfully
    and dispatches emails only if matching active accounts exist.
    """
    email = forms.EmailField(
        label="Email Address",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        ),
        error_messages={
            "required": "Please enter your email address.",
            "invalid": "Please enter a valid email address.",
        },
    )

    def save(self, request: Optional[HttpRequest] = None) -> None:
        """
        Retrieve matching active accounts and dispatch password reset emails.
        Succeeds silently if no matching account is found.
        """
        email = self.cleaned_data["email"]
        users = get_users_for_password_reset(email)
        for user in users:
            send_password_reset_email(user, request=request)


class UserSetPasswordForm(AriaErrorHighlightFormMixin, auth_forms.SetPasswordForm):
    """
    Form for setting a new password when resetting via token.
    
    Inherits Django's password validation framework and cross-field confirmation check.
    Customizes widgets with luxury styling and ARIA accessibility attributes.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            "placeholder": "••••••••••••",
            "autocomplete": "new-password",
        })
        self.fields["new_password2"].widget.attrs.update({
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            "placeholder": "••••••••••••",
            "autocomplete": "new-password",
        })


class UserPasswordChangeForm(AriaErrorHighlightFormMixin, auth_forms.PasswordChangeForm):
    """
    Form for authenticated users to change their password.
    
    Requires current password verification and enforces Django's password validators
    on the new password. Customizes widgets with luxury styling and ARIA attributes.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            "placeholder": "••••••••••••",
            "autocomplete": "current-password",
        })
        self.fields["new_password1"].widget.attrs.update({
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            "placeholder": "••••••••••••",
            "autocomplete": "new-password",
        })
        self.fields["new_password2"].widget.attrs.update({
            "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            "placeholder": "••••••••••••",
            "autocomplete": "new-password",
        })


class ProfileUpdateForm(AriaErrorHighlightFormMixin, forms.ModelForm):
    """
    Form for updating customer profile attributes and preferences.
    
    Enforces that email and password cannot be changed here.
    """
    class Meta:
        model = UserProfile
        fields = [
            "phone_number",
            "date_of_birth",
            "preferred_language",
            "preferred_currency",
            "marketing_emails",
        ]
        widgets = {
            "phone_number": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "+1 (555) 000-0000",
                "autocomplete": "tel",
            }),
            "date_of_birth": forms.DateInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "type": "date",
            }),
            "preferred_language": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            }),
            "preferred_currency": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
            }),
            "marketing_emails": forms.CheckboxInput(attrs={
                "class": "w-4 h-4 text-primary-900 border-neutral-300 rounded focus:ring-primary-900 transition-all",
            }),
        }

    def clean_date_of_birth(self) -> Any:
        dob = self.cleaned_data.get("date_of_birth")
        if dob and dob > timezone.now().date():
            raise ValidationError("Date of birth cannot be in the future.")
        return dob



class AvatarUploadForm(AriaErrorHighlightFormMixin, forms.ModelForm):
    """
    Form for uploading a new customer avatar image.
    
    Enforces file size (<= 2MB) and valid image extension/format.
    Uses FileField instead of ImageField to avoid premature stream closure by Pillow during form binding.
    """
    avatar = forms.FileField(
        widget=forms.FileInput(attrs={
            "class": "block w-full text-sm text-neutral-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-btn file:border-0 file:text-sm file:font-medium file:bg-neutral-100 file:text-primary-900 hover:file:bg-neutral-200 transition-all cursor-pointer",
            "accept": "image/jpeg,image/png,image/webp,image/gif",
        }),
        error_messages={
            "required": "Please select an image file to upload.",
        }
    )

    class Meta:
        model = UserProfile
        fields = ["avatar"]

    def clean_avatar(self) -> Any:
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            max_size = 2 * 1024 * 1024
            if getattr(avatar, "size", 0) > max_size:
                raise ValidationError("Image file too large. Maximum allowed size is 2MB.")

            valid_extensions = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
            file_name = getattr(avatar, "name", "").lower()
            if not any(file_name.endswith(ext) for ext in valid_extensions):
                raise ValidationError("Invalid image format. Supported formats: JPEG, PNG, WEBP, GIF.")
        return avatar


class AddressForm(AriaErrorHighlightFormMixin, forms.ModelForm):
    """
    ModelForm for adding and editing customer shipping/billing addresses.

    Includes accessibility attributes, international country selection,
    postal code validation, and phone number format checks.
    """
    class Meta:
        model = Address
        fields = [
            "label",
            "recipient_name",
            "phone_number",
            "company_name",
            "address_line_1",
            "address_line_2",
            "city",
            "county_or_state",
            "postal_code",
            "country",
            "address_type",
            "is_default_shipping",
            "is_default_billing",
        ]
        widgets = {
            "label": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "e.g., Home, Office, Parents",
            }),
            "recipient_name": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Full Name",
                "autocomplete": "name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "e.g., +1 555-0199 or +44 20 7946 0999",
                "autocomplete": "tel",
            }),
            "company_name": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Optional company or building name",
                "autocomplete": "organization",
            }),
            "address_line_1": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Street address, P.O. box, c/o",
                "autocomplete": "address-line1",
            }),
            "address_line_2": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Apartment, suite, unit, building, floor, etc.",
                "autocomplete": "address-line2",
            }),
            "city": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "City or Town",
                "autocomplete": "address-level2",
            }),
            "county_or_state": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "State, Province, or County",
                "autocomplete": "address-level1",
            }),
            "postal_code": forms.TextInput(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Postal or ZIP code",
                "autocomplete": "postal-code",
            }),
            "country": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm cursor-pointer",
                "autocomplete": "country",
            }),
            "address_type": forms.Select(attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm cursor-pointer",
            }),
            "is_default_shipping": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-primary-900 focus:ring-primary-900 transition-colors cursor-pointer",
            }),
            "is_default_billing": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-neutral-300 text-primary-900 focus:ring-primary-900 transition-colors cursor-pointer",
            }),
        }

    def clean_phone_number(self) -> str:
        phone = self.cleaned_data.get("phone_number", "").strip()
        import re
        if not re.match(r"^\+?[\d\s\-\(\)\.]{7,25}$", phone):
            raise ValidationError("Please enter a valid international phone number (e.g., +1 555-0199 or +44 20 7946 0999).")
        return phone

    def clean(self) -> Any:
        cleaned_data = super().clean()
        postal = cleaned_data.get("postal_code", "").strip() if cleaned_data.get("postal_code") else ""
        country = cleaned_data.get("country", "")
        if country in ("US", "CA", "GB", "FR", "IT", "DE", "CH", "JP", "AU") and not postal:
            self.add_error("postal_code", "Postal code is required for the selected country.")
        return cleaned_data


class EmailChangeForm(AriaErrorHighlightFormMixin, forms.Form):
    """
    Form for requesting a login email address change.
    Requires current password confirmation and unique new email validation.
    """
    new_email = forms.EmailField(
        label=_("New Email Address"),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Enter your new email address",
                "autocomplete": "email",
            }
        ),
    )
    password = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Enter your current password to confirm",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, *args: Any, user: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self) -> str:
        new_email = self.cleaned_data.get("new_email", "").strip().lower()
        if not new_email:
            raise ValidationError(_("Please provide a valid email address."))

        if self.user and new_email == self.user.email.lower():
            raise ValidationError(_("New email address must be different from your current email."))

        from accounts.selectors import email_exists
        if email_exists(new_email):
            raise ValidationError(_("An account with this email address already exists."))

        return new_email

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password", "")
        if self.user and not self.user.check_password(password):
            raise ValidationError(_("Incorrect current password."))
        return password


class AccountDeactivateForm(AriaErrorHighlightFormMixin, forms.Form):
    """
    Form for deactivating a customer account.
    Requires current password confirmation.
    """
    password = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Enter your password to confirm deactivation",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, *args: Any, user: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password", "")
        if self.user and not self.user.check_password(password):
            raise ValidationError(_("Incorrect current password."))
        return password


class AccountDeleteForm(AriaErrorHighlightFormMixin, forms.Form):
    """
    Form for permanently/soft-deleting a customer account.
    Requires password confirmation and an explicit confirmation phrase.
    """
    password = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )
    confirmation_phrase = forms.CharField(
        label=_("Confirmation Phrase"),
        help_text=_("Type exactly: DELETE MY ACCOUNT"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-3 bg-white border border-neutral-300 rounded-btn text-primary-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-900 focus:border-transparent transition-all text-sm font-mono uppercase",
                "placeholder": "DELETE MY ACCOUNT",
                "autocomplete": "off",
            }
        ),
    )

    def __init__(self, *args: Any, user: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password", "")
        if self.user and not self.user.check_password(password):
            raise ValidationError(_("Incorrect current password."))
        return password

    def clean_confirmation_phrase(self) -> str:
        phrase = self.cleaned_data.get("confirmation_phrase", "").strip()
        if phrase != "DELETE MY ACCOUNT":
            raise ValidationError(_("Please type exactly 'DELETE MY ACCOUNT' to confirm."))
        return phrase

