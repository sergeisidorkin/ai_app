from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry
from policy_app.models import Product
from projects_app.models import Performer
from .models import ContractTemplate, ContractVariable


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


class ContractVariableForm(forms.ModelForm):
    source_section = forms.ChoiceField(
        label="Раздел", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_section"}),
    )
    source_table = forms.ChoiceField(
        label="Таблица", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_table"}),
    )
    source_column = forms.ChoiceField(
        label="Столбец", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_column"}),
    )

    class Meta:
        model = ContractVariable
        fields = [
            "key", "description",
            "source_section", "source_table", "source_column",
        ]
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control", "placeholder": "{{variable_name}}"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Описание переменной"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.column_registry import (
            get_section_choices, get_table_choices, get_column_choices,
        )
        self.fields["source_section"].choices = get_section_choices()

        sec = (
            self.data.get("source_section", "")
            or self.initial.get("source_section", "")
            or (self.instance.source_section if self.instance and self.instance.pk else "")
        )
        tbl = (
            self.data.get("source_table", "")
            or self.initial.get("source_table", "")
            or (self.instance.source_table if self.instance and self.instance.pk else "")
        )
        if sec:
            self.fields["source_table"].choices = get_table_choices(sec)
        else:
            self.fields["source_table"].choices = [("", "---")]
        if sec and tbl:
            self.fields["source_column"].choices = get_column_choices(sec, tbl)
        else:
            self.fields["source_column"].choices = [("", "---")]

    def clean_key(self):
        import re
        raw = self.cleaned_data.get("key", "").strip()
        inner = raw.removeprefix("{{").removesuffix("}}")
        inner = inner.removeprefix("{").removesuffix("}")
        inner = inner.strip()
        if not inner:
            raise forms.ValidationError("Поле не может быть пустым.")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", inner):
            raise forms.ValidationError(
                "Допускаются только латинские буквы, цифры и подчёркивания. "
                "Значение должно начинаться с буквы."
            )
        return "{{" + inner + "}}"

    def clean(self):
        cleaned = super().clean()
        sec = cleaned.get("source_section", "")
        tbl = cleaned.get("source_table", "")
        col = cleaned.get("source_column", "")
        filled = [f for f in (sec, tbl, col) if f]
        if filled and len(filled) != 3:
            raise forms.ValidationError(
                "Необходимо заполнить все три поля: Раздел, Таблица и Столбец."
            )
        if sec and tbl and col:
            from core.column_registry import validate_column_ref
            if not validate_column_ref(sec, tbl, col):
                raise forms.ValidationError("Указанная комбинация Раздел/Таблица/Столбец не существует.")
        return cleaned
