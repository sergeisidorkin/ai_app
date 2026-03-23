from django import forms

from .models import ExternalSMTPAccount


class ExternalSMTPAccountForm(forms.ModelForm):
    smtp_password = forms.CharField(
        label="Пароль / app password",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите пароль или app password",
                "autocomplete": "new-password",
            },
            render_value=False,
        ),
    )

    class Meta:
        model = ExternalSMTPAccount
        fields = [
            "label",
            "smtp_host",
            "smtp_port",
            "username",
            "from_email",
            "reply_to_email",
            "use_tls",
            "use_ssl",
            "skip_tls_verify",
            "is_active",
            "use_for_notifications",
        ]
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например, Corporate SMTP"}),
            "smtp_host": forms.TextInput(attrs={"class": "form-control", "placeholder": "smtp.example.com"}),
            "smtp_port": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 65535}),
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "name@imcgroup.ru"}),
            "from_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@imcgroup.ru"}),
            "reply_to_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Необязательно"}),
            "use_tls": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "use_ssl": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "skip_tls_verify": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "use_for_notifications": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.has_password:
            self.fields["smtp_password"].help_text = "Оставьте пустым, чтобы сохранить текущий пароль."

    def clean(self):
        cleaned_data = super().clean()
        use_tls = cleaned_data.get("use_tls")
        use_ssl = cleaned_data.get("use_ssl")
        smtp_password = (cleaned_data.get("smtp_password") or "").strip()

        if use_tls and use_ssl:
            raise forms.ValidationError("Нельзя одновременно включить STARTTLS и SSL.")

        if not self.instance.pk and not smtp_password:
            self.add_error("smtp_password", "Пароль обязателен при первом подключении.")

        return cleaned_data

    def save(self, commit=True):
        account = super().save(commit=False)
        if self.user is not None:
            account.user = self.user

        smtp_password = (self.cleaned_data.get("smtp_password") or "").strip()
        if smtp_password:
            account.set_password(smtp_password)

        if commit:
            account.save()
        return account
