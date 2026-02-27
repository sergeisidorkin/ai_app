from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from django import forms
from django.db.models import Q

from .models import OKSMCountry, OKVCurrency, TerritorialDivision, LivingWage


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    )


class OKSMCountryForm(forms.ModelForm):
    class Meta:
        model = OKSMCountry
        fields = ["number", "code", "short_name", "full_name", "alpha2", "alpha3", "approval_date", "expiry_date", "source"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Порядковый номер"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "000", "maxlength": "3"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое наименование страны"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Полное наименование страны"}),
            "alpha2": forms.TextInput(attrs={"class": "form-control", "placeholder": "AA", "maxlength": "2", "style": "text-transform:uppercase"}),
            "alpha3": forms.TextInput(attrs={"class": "form-control", "placeholder": "AAA", "maxlength": "3", "style": "text-transform:uppercase"}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_alpha2(self):
        return (self.cleaned_data.get("alpha2") or "").upper()

    def clean_alpha3(self):
        return (self.cleaned_data.get("alpha3") or "").upper()

    def clean_code(self):
        val = self.cleaned_data.get("code") or ""
        if not val.isdigit() or len(val) != 3:
            raise forms.ValidationError("Код должен состоять из трёх цифр.")
        return val


class OKVCurrencyForm(forms.ModelForm):
    countries = forms.ModelMultipleChoiceField(
        label="Страны использования",
        queryset=OKSMCountry.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "8"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs()
        if self.instance and self.instance.pk:
            qs = (qs | self.instance.countries.all()).distinct()
        self.fields["countries"].queryset = qs
        self.fields["countries"].label_from_instance = lambda obj: f"{obj.code} — {obj.short_name}"

    class Meta:
        model = OKVCurrency
        fields = ["code_numeric", "code_alpha", "name", "abbreviation", "symbol", "countries", "approval_date", "expiry_date", "source"]
        widgets = {
            "code_numeric": forms.TextInput(attrs={"class": "form-control", "placeholder": "000", "maxlength": "3"}),
            "code_alpha": forms.TextInput(attrs={"class": "form-control", "placeholder": "AAA", "maxlength": "3", "style": "text-transform:uppercase"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование валюты"}),
            "abbreviation": forms.TextInput(attrs={"class": "form-control", "placeholder": "Сокр. обозначение"}),
            "symbol": forms.TextInput(attrs={"class": "form-control", "placeholder": "₽, $, € ..."}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_code_numeric(self):
        val = self.cleaned_data.get("code_numeric") or ""
        if not val.isdigit() or len(val) != 3:
            raise forms.ValidationError("Код должен состоять из трёх цифр.")
        return val

    def clean_code_alpha(self):
        return (self.cleaned_data.get("code_alpha") or "").upper()


class TerritorialDivisionForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Наименование страны (краткое)",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct()
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name

    class Meta:
        model = TerritorialDivision
        fields = ["country", "region_name", "region_code", "effective_date", "abolished_date", "source"]
        widgets = {
            "region_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование региона"}),
            "region_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код региона"}),
            "effective_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "abolished_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }


class LivingWageForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Наименование страны (краткое)",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "lw-country-select"}),
    )
    region = forms.ModelChoiceField(
        label="Регион",
        queryset=TerritorialDivision.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "lw-region-select"}),
    )
    amount = forms.CharField(
        label="Величина прожиточного минимума",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "0,00",
            "inputmode": "decimal",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs().filter(
            pk__in=TerritorialDivision.objects.values_list("country_id", flat=True).distinct()
        )
        if self.instance and self.instance.pk and self.instance.country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct()
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["region"].label_from_instance = lambda obj: obj.region_name
        if self.instance and self.instance.pk:
            self.fields["region"].queryset = TerritorialDivision.objects.filter(
                country=self.instance.country
            )
        elif "country" in self.data:
            try:
                country_id = int(self.data.get("country"))
                self.fields["region"].queryset = TerritorialDivision.objects.filter(
                    country_id=country_id
                )
            except (ValueError, TypeError):
                pass

    class Meta:
        model = LivingWage
        fields = ["country", "region", "amount", "currency", "approval_date", "expiry_date", "source"]
        widgets = {
            "currency": forms.TextInput(attrs={"class": "form-control", "placeholder": "Валюта", "readonly": True, "tabindex": "-1", "style": "background-color:#f8f9fa; color:#6c757d;"}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_amount(self):
        raw = self.data.get("amount", "")
        cleaned = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Введите корректное числовое значение.")
