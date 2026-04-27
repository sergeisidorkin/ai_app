import json
from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry, TerritorialDivision
from contracts_app.forms import _ContractFileInput
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUPS,
    ExpertiseDirection,
    Grade,
)
from users_app.models import Employee
from .models import ExpertContractDetails, ExpertProfile, ExpertSpecialty

OWNER_GROUP_VALUE = "__group__"


def _territorial_division_region_choices_for_country(country_id, current_value=""):
    choices = []
    seen = set()
    if country_id:
        today = date_type.today()
        qs = TerritorialDivision.objects.filter(
            country_id=country_id,
            effective_date__lte=today,
        ).filter(
            Q(abolished_date__isnull=True) | Q(abolished_date__gte=today),
        )
        for region_name in qs.order_by("region_name", "position", "id").values_list("region_name", flat=True):
            if not region_name or region_name in seen:
                continue
            seen.add(region_name)
            choices.append((region_name, region_name))
    if current_value and current_value not in seen:
        choices.append((current_value, current_value))
    return choices


class ExpertSpecialtyForm(forms.ModelForm):
    class Meta:
        model = ExpertSpecialty
        fields = ["expertise_direction", "specialty", "specialty_en", "expertise_dir", "head_of_direction"]
        widgets = {
            "expertise_direction": forms.Select(attrs={"class": "form-select", "id": "esp-dept-select"}),
            "specialty": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Специальность",
            }),
            "specialty_en": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Specialty (English)",
            }),
            "expertise_dir": forms.Select(attrs={"class": "form-select", "id": "esp-dir-select"}),
            "head_of_direction": forms.Select(attrs={"class": "form-select"}),
        }
        error_messages = {
            "specialty": {
                "unique": "Специальность с таким именем уже существует.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        all_org_units = OrgUnit.objects.all()
        self.fields["expertise_direction"].queryset = all_org_units
        self.fields["expertise_direction"].label_from_instance = (
            lambda obj: obj.department_name
        )
        self.fields["expertise_direction"].empty_label = "---------"
        self.fields["expertise_direction"].required = False

        org_unit_info = {}
        for u in all_org_units.values("pk", "unit_type", "company_id", "expertise_id"):
            org_unit_info[str(u["pk"])] = {
                "type": u["unit_type"],
                "company_id": u["company_id"],
                "expertise_id": u["expertise_id"],
            }
        self.org_unit_info_json = json.dumps(org_unit_info, ensure_ascii=False)

        self.fields["expertise_dir"].queryset = ExpertiseDirection.objects.all()
        self.fields["expertise_dir"].label_from_instance = (
            lambda obj: f"{obj.short_name} {obj.name}"
        )
        self.fields["expertise_dir"].empty_label = "---------"
        self.fields["expertise_dir"].required = False

        self.fields["head_of_direction"].queryset = Employee.objects.filter(
            role__in=(DEPARTMENT_HEAD_GROUP, *DIRECTOR_GROUPS)
        )
        self.fields["head_of_direction"].label_from_instance = (
            lambda obj: obj.job_title
        )
        self.fields["head_of_direction"].empty_label = "---------"
        self.fields["head_of_direction"].required = False

        self.owner_options = list(GroupMember.objects.order_by("position", "id").values("pk", "short_name"))
        self.selected_owner_ids = []
        self.is_group_selected = False
        if self.is_bound:
            owner_values = self.data.getlist("owner_ids")
            if OWNER_GROUP_VALUE in owner_values:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
        elif self.instance and self.instance.pk:
            if self.instance.is_group_owner:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = list(
                    self.instance.owners.values_list("pk", flat=True)
                )

        directions = ExpertiseDirection.objects.prefetch_related("owners").all()
        dir_owners = {}
        for d in directions:
            dir_owners[str(d.pk)] = {
                "owner_ids": list(d.owners.values_list("pk", flat=True)),
                "is_group": d.is_group_owner,
            }
        self.dir_owners_json = json.dumps(dir_owners, ensure_ascii=False)

    def save(self, commit=True):
        obj = super().save(commit=False)
        owner_values = self.data.getlist("owner_ids")
        if OWNER_GROUP_VALUE in owner_values:
            obj.is_group_owner = True
        else:
            obj.is_group_owner = False
        if commit:
            obj.save()
            if obj.is_group_owner:
                obj.owners.clear()
            else:
                member_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
                obj.owners.set(member_ids)
        return obj


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name")


def _active_regions_qs(country_pk=None):
    today = date_type.today()
    qs = TerritorialDivision.objects.filter(
        effective_date__lte=today,
    ).filter(
        Q(abolished_date__isnull=True) | Q(abolished_date__gte=today),
    )
    if country_pk:
        qs = qs.filter(country_id=country_pk)
    return qs.order_by("region_name")


class ExpertProfileForm(forms.ModelForm):
    class Meta:
        model = ExpertProfile
        fields = [
            "extra_email", "extra_phone",
            "expertise_direction", "professional_status", "professional_status_short", "grade",
            "country", "region", "status",
        ]
        widgets = {
            "extra_email": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "name@mail.ru",
            }),
            "extra_phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+7 000 000-00-00",
            }),
            "expertise_direction": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-direction-select",
            }),
            "professional_status": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Профессиональный статус",
            }),
            "professional_status_short": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Профессиональный статус (кратко)",
            }),
            "grade": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-grade-select",
            }),
            "country": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-country-select",
            }),
            "region": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-region-select",
            }),
            "status": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Статус",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["expertise_direction"].queryset = OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(level=1)
        )
        self.fields["expertise_direction"].label_from_instance = (
            lambda obj: obj.department_name
        )
        self.fields["expertise_direction"].empty_label = "---------"
        self.fields["expertise_direction"].required = False

        direction_pk = self._resolve_fk("expertise_direction")
        if direction_pk:
            self.fields["grade"].queryset = Grade.objects.filter(
                created_by__employee_profile__department_id=direction_pk
            )
        else:
            self.fields["grade"].queryset = Grade.objects.all()
        self.fields["grade"].label_from_instance = lambda obj: obj.grade_ru
        self.fields["grade"].empty_label = "---------"
        self.fields["grade"].required = False

        resolved_country = None
        resolved_region = None
        if self.instance and self.instance.pk:
            resolved_country = self.instance.resolved_country()
            resolved_region = self.instance.resolved_region()

        self.fields["country"].queryset = _active_countries_qs()
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["country"].empty_label = "---------"
        self.fields["country"].required = False
        if resolved_country is not None:
            self.initial["country"] = resolved_country.pk

        country_pk = self._resolve_fk("country")
        if country_pk:
            self.fields["region"].queryset = _active_regions_qs(country_pk)
        else:
            self.fields["region"].queryset = TerritorialDivision.objects.none()
        if resolved_region is not None:
            self.initial["region"] = resolved_region.pk
        self.fields["region"].label_from_instance = lambda obj: obj.region_name
        self.fields["region"].label = "Регион проживания"
        self.fields["region"].empty_label = "---------"
        self.fields["region"].required = False

        extra_email_value = ""
        extra_phone_value = ""
        if self.instance and self.instance.pk:
            extra_email_value = self.instance.resolved_extra_email()
            extra_phone_value = self.instance.resolved_extra_phone()
        self.initial["extra_email"] = extra_email_value
        self.initial["extra_phone"] = extra_phone_value
        for field_name in ("extra_email", "extra_phone", "country", "region"):
            field = self.fields[field_name]
            field.disabled = True
            field.widget.attrs["readonly"] = True
            field.widget.attrs["tabindex"] = "-1"
            field.widget.attrs["class"] = field.widget.attrs.get("class", "") + " readonly-field"

    def _resolve_fk(self, field_name):
        if self.data:
            val = self.data.get(field_name)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        if self.instance and self.instance.pk:
            val = getattr(self.instance, f"{field_name}_id", None)
            if val:
                return val
        if field_name in self.initial:
            try:
                return int(self.initial[field_name])
            except (ValueError, TypeError):
                pass
        return None


class ExpertContractDetailsForm(forms.ModelForm):
    citizenship = forms.CharField(
        label="Гражданство",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
    )
    citizenship_country = forms.CharField(
        label="Страна гражданства (налоговая юрисдикция)",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
    )
    citizenship_status = forms.CharField(
        label="Статус",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
    )
    citizenship_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
    )
    citizenship_number = forms.CharField(
        label="Номер",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "ecd-registration-region-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance is None:
            return
        country_id = getattr(getattr(instance, "citizenship_record", None), "country_id", None)
        current_region = ""
        if self.is_bound:
            current_region = self.data.get("registration_region") or ""
        elif getattr(instance, "pk", None):
            current_region = instance.registration_region or ""
        self.fields["registration_region"].choices = [("", "---------")] + _territorial_division_region_choices_for_country(
            country_id,
            current_value=current_region,
        )
        self.fields["citizenship"].initial = instance.calculated_citizenship
        self.fields["citizenship_country"].initial = instance.citizenship_country
        self.fields["citizenship_country"].widget.attrs["data-country-id"] = str(country_id or "")
        self.fields["citizenship_status"].initial = instance.citizenship_status
        self.fields["citizenship_identifier"].initial = instance.citizenship_identifier
        self.fields["citizenship_number"].initial = instance.citizenship_number
        self.fields["registration_address"].initial = instance.calculated_registration_address
        self.fields["registration_address"].disabled = True
        self.fields["registration_address"].widget.attrs.update(
            {
                "readonly": True,
                "tabindex": "-1",
                "class": self.fields["registration_address"].widget.attrs.get("class", "") + " readonly-field",
            }
        )
        self.fields["full_name_genitive"].initial = instance.person_full_name_genitive
        self.fields["full_name_genitive"].disabled = True
        self.fields["full_name_genitive"].widget.attrs.update(
            {
                "readonly": True,
                "tabindex": "-1",
                "class": self.fields["full_name_genitive"].widget.attrs.get("class", "") + " readonly-field",
            }
        )
        self.fields["gender"].initial = instance.person_gender
        self.fields["gender"].disabled = True
        self.fields["gender"].widget.attrs.update(
            {
                "tabindex": "-1",
                "class": self.fields["gender"].widget.attrs.get("class", "") + " readonly-field",
            }
        )
        self.fields["birth_date"].initial = instance.person_birth_date
        self.fields["birth_date"].disabled = True
        self.fields["birth_date"].widget.attrs.update(
            {
                "readonly": True,
                "tabindex": "-1",
                "class": self.fields["birth_date"].widget.attrs.get("class", "") + " readonly-field",
            }
        )
        self.fields["facsimile_file"].widget.attrs.update(
            {
                "cloud_current_url": getattr(instance.facsimile_file, "url", "") if getattr(instance, "facsimile_file", None) else "",
                "cloud_current_name": getattr(instance.facsimile_file, "name", "") if getattr(instance, "facsimile_file", None) else "",
            }
        )

    class Meta:
        model = ExpertContractDetails
        fields = [
            "full_name_genitive", "self_employed", "tax_rate",
            "gender", "snils", "birth_date",
            "passport_series", "passport_number", "passport_issued_by",
            "passport_issue_date", "passport_expiry_date", "passport_division_code",
            "registration_address", "registration_postal_code", "registration_region",
            "registration_locality", "registration_street",
            "registration_building", "registration_premise", "registration_premise_part", "registration_date",
            "bank_name", "bank_swift", "bank_inn", "bank_bik",
            "settlement_account", "corr_account", "bank_address",
            "corr_bank_name", "corr_bank_address", "corr_bank_bik", "corr_bank_swift",
            "corr_bank_settlement_account", "corr_bank_corr_account",
            "facsimile_file",
        ]
        widgets = {
            "full_name_genitive": forms.TextInput(attrs={"class": "form-control"}),
            "self_employed": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "snils": forms.TextInput(attrs={"class": "form-control", "placeholder": "000-000-000 00"}),
            "birth_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_series": forms.TextInput(attrs={"class": "form-control"}),
            "passport_number": forms.TextInput(attrs={"class": "form-control"}),
            "passport_issued_by": forms.TextInput(attrs={"class": "form-control"}),
            "passport_issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_division_code": forms.TextInput(attrs={"class": "form-control"}),
            "registration_address": forms.TextInput(attrs={"class": "form-control"}),
            "registration_postal_code": forms.TextInput(attrs={"class": "form-control"}),
            "registration_locality": forms.TextInput(attrs={"class": "form-control"}),
            "registration_street": forms.TextInput(attrs={"class": "form-control"}),
            "registration_building": forms.TextInput(attrs={"class": "form-control"}),
            "registration_premise": forms.TextInput(attrs={"class": "form-control"}),
            "registration_premise_part": forms.TextInput(attrs={"class": "form-control"}),
            "registration_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "bank_name": forms.TextInput(attrs={"class": "form-control"}),
            "bank_swift": forms.TextInput(attrs={"class": "form-control"}),
            "bank_inn": forms.TextInput(attrs={"class": "form-control"}),
            "bank_bik": forms.TextInput(attrs={"class": "form-control"}),
            "settlement_account": forms.TextInput(attrs={"class": "form-control"}),
            "corr_account": forms.TextInput(attrs={"class": "form-control"}),
            "bank_address": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_name": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_address": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_bik": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_swift": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_settlement_account": forms.TextInput(attrs={"class": "form-control"}),
            "corr_bank_corr_account": forms.TextInput(attrs={"class": "form-control"}),
            "facsimile_file": _ContractFileInput(attrs={"class": "form-control"}),
        }
