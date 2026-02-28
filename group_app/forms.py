from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry
from .models import GroupMember


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    )


class GroupMemberForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "gm-country-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_code:
            qs = (qs | OKSMCountry.objects.filter(code=self.instance.country_code)).distinct()
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if self.instance and self.instance.pk and self.instance.country_code:
            try:
                self.initial["country"] = OKSMCountry.objects.get(code=self.instance.country_code).pk
            except OKSMCountry.DoesNotExist:
                pass

    class Meta:
        model = GroupMember
        fields = [
            "short_name", "full_name", "name_en",
            "identifier", "registration_number", "registration_date",
        ]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое наименование"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Полное наименование"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "Name in English"}),
            "identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Идентификатор"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Регистрационный номер"}),
            "registration_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        country = self.cleaned_data.get("country")
        if country:
            instance.country_name = country.short_name
            instance.country_code = country.code
        if commit:
            instance.save()
        return instance
