from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import LegalEntityIdentifier, OKSMCountry
from policy_app.models import ExpertiseDirection
from .models import GroupMember, OrgUnit


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    )


def _identifier_for_country_code(country_code: str) -> str:
    if not country_code:
        return ""
    item = LegalEntityIdentifier.objects.filter(code=country_code).order_by("position", "id").first()
    return item.identifier if item else ""


class GroupMemberForm(forms.ModelForm):
    order_number = forms.IntegerField(
        label="Порядковый номер",
        required=False,
        disabled=True,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "id": "gm-order-number",
                "readonly": True,
                "tabindex": "-1",
                "style": "background-color:#f8f9fa; color:#6c757d;",
            }
        ),
    )

    country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "gm-country-select"}),
    )

    def __init__(self, *args, **kwargs):
        current_order_number = kwargs.pop("current_order_number", 0)
        super().__init__(*args, **kwargs)
        self.fields["order_number"].initial = current_order_number
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
        self.fields["identifier"].widget.attrs.update({
            "readonly": True,
            "tabindex": "-1",
            "style": "background-color:#f8f9fa; color:#6c757d;",
            "id": "gm-identifier",
        })
        if self.instance and self.instance.pk:
            self.initial["identifier"] = self.instance.identifier or _identifier_for_country_code(self.instance.country_code)

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
            instance.country_alpha2 = country.alpha2
            instance.identifier = _identifier_for_country_code(country.code)
        else:
            instance.country_name = ""
            instance.country_code = ""
            instance.country_alpha2 = ""
            instance.identifier = ""
        if commit:
            instance.save()
        return instance


class OrgUnitForm(forms.ModelForm):
    expertise = forms.ModelChoiceField(
        label="Экспертиза",
        queryset=ExpertiseDirection.objects.order_by("position", "id"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = OrgUnit
        fields = ["company", "level", "department_name", "expertise", "functional_subordination", "unit_type"]
        widgets = {
            "company": forms.Select(attrs={
                "class": "form-select",
                "id": "org-company-select",
            }),
            "level": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "placeholder": "1",
                "id": "org-level-input",
            }),
            "department_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Наименование подразделения",
            }),
            "functional_subordination": forms.Select(attrs={
                "class": "form-select",
                "id": "org-func-sub",
            }),
            "unit_type": forms.Select(attrs={
                "class": "form-select",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = GroupMember.objects.all()
        self.fields["company"].label_from_instance = lambda obj: obj.short_name
        self.fields["company"].empty_label = "---------"

        self.fields["expertise"].queryset = ExpertiseDirection.objects.order_by("position", "id")
        self.fields["expertise"].label_from_instance = (
            lambda obj: f"{obj.short_name} {obj.name}"
        )
        self.fields["expertise"].empty_label = "---------"

        qs = OrgUnit.objects.select_related("company").all()
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["functional_subordination"].queryset = qs
        self.fields["functional_subordination"].label_from_instance = (
            lambda obj: obj.department_name
        )
        self.fields["functional_subordination"].required = False
        self.fields["functional_subordination"].empty_label = "---------"

    def clean_level(self):
        level = self.cleaned_data.get("level")
        if level is not None and level < 1:
            raise forms.ValidationError("Уровень не может быть меньше 1.")
        return level
