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
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from accounts.selectors import email_exists, username_exists

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):
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

    def full_clean(self) -> None:
        """
        Override full_clean to automatically attach ARIA accessibility attributes
        and styling classes to widgets when form validation errors occur.
        """
        super().full_clean()
        for field_name in self.errors:
            if field_name in self.fields:
                field = self.fields[field_name]
                field_id = field.widget.attrs.get("id") or f"id_{field_name}"
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"{field_id}_error"
                
                # Add visual error highlight styling to text inputs
                existing_class = field.widget.attrs.get("class", "")
                if "border-neutral-300" in existing_class:
                    field.widget.attrs["class"] = existing_class.replace(
                        "border-neutral-300", "border-red-500 text-red-900 focus:ring-red-500"
                    )

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


class UserLoginForm(forms.Form):
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

    def full_clean(self) -> None:
        """
        Override full_clean to automatically attach ARIA accessibility attributes
        and styling classes to widgets when login validation errors occur.
        """
        super().full_clean()
        fields_to_mark = list(self.errors.keys())
        if "__all__" in fields_to_mark:
            fields_to_mark.extend(["email", "password"])

        for field_name in set(fields_to_mark):
            if field_name in self.fields:
                field = self.fields[field_name]
                field_id = field.widget.attrs.get("id") or f"id_{field_name}"
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"{field_id}_error"
                
                # Add visual error highlight styling to text inputs
                existing_class = field.widget.attrs.get("class", "")
                if "border-neutral-300" in existing_class:
                    field.widget.attrs["class"] = existing_class.replace(
                        "border-neutral-300", "border-red-500 text-red-900 focus:ring-red-500"
                    )
