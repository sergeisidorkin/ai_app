from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry

from .models import PersonRecord, PositionRecord


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name", "position", "id")


def _format_prs_id(obj):
    return f"{obj.pk:05d}-PRS"


def _person_label(obj):
    display_name = obj.display_name or "Без имени"
    return f"{_format_prs_id(obj)} | {display_name}"


class PersonRecordForm(forms.ModelForm):
    citizenship = forms.ModelChoiceField(
        label="Гражданство",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.citizenship_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.citizenship_id)).distinct().order_by(
                "short_name", "position", "id"
            )
        self.fields["citizenship"].queryset = qs
        self.fields["citizenship"].label_from_instance = lambda obj: obj.short_name
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.citizenship_id):
            default_country = qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["citizenship"].initial = default_country.pk

    class Meta:
        model = PersonRecord
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "citizenship",
            "identifier",
            "number",
        ]
        widgets = {
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Фамилия"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Имя"}),
            "middle_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отчество"}),
            "identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Идентификатор"}),
            "number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Номер"}),
        }


class PositionRecordForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    organization_short_name = forms.ChoiceField(
        label="Наименование организации (краткое)",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label

        current_value = ""
        if self.is_bound:
            current_value = (self.data.get("organization_short_name") or "").strip()
        elif self.instance and self.instance.pk:
            current_value = self.instance.organization_short_name or ""
        organization_choices = [("", "---------")]
        organization_choices.extend((value, value) for value in PositionRecord.organization_choices())
        if current_value and current_value not in {value for value, _label in organization_choices}:
            organization_choices.append((current_value, current_value))
        self.fields["organization_short_name"].choices = organization_choices

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", 'Дата "Действ. до" не может быть раньше даты "Действ. от".')
        return cleaned_data

    class Meta:
        model = PositionRecord
        fields = [
            "person",
            "organization_short_name",
            "job_title",
            "valid_from",
            "valid_to",
        ]
        widgets = {
            "job_title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Должность"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
