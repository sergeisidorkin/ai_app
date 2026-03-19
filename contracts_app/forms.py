from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry
from policy_app.models import Product
from projects_app.models import Performer
from .models import ContractTemplate


class ContractEditForm(forms.ModelForm):
    class Meta:
        model = Performer
        fields = [
            "contract_number",
            "contract_file",
        ]
        widgets = {
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
            "contract_file": forms.TextInput(attrs={"class": "form-control"}),
        }


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name")


class ContractTemplateForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ContractTemplate
        fields = [
            "product", "contract_type", "party",
            "sample_name", "version", "file",
        ]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "contract_type": forms.Select(attrs={"class": "form-select"}),
            "party": forms.Select(attrs={"class": "form-select"}),
            "sample_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование образца"}),
            "version": forms.TextInput(attrs={"class": "form-control", "placeholder": "Версия"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.order_by("position", "id")
        self.fields["product"].label_from_instance = lambda obj: obj.short_name

        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_code:
            qs = (qs | OKSMCountry.objects.filter(code=self.instance.country_code)).distinct().order_by("short_name")
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name

        if self.instance and self.instance.pk and self.instance.country_code:
            try:
                self.initial["country"] = OKSMCountry.objects.get(code=self.instance.country_code).pk
            except OKSMCountry.DoesNotExist:
                pass

    def save(self, commit=True):
        instance = super().save(commit=False)
        country = self.cleaned_data.get("country")
        if country:
            instance.country_name = country.short_name
            instance.country_code = country.code
        else:
            instance.country_name = ""
            instance.country_code = ""
        if commit:
            instance.save()
        return instance
