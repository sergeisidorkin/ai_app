import json
from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry, TerritorialDivision
from group_app.models import GroupMember, OrgUnit
from policy_app.models import ExpertiseDirection, Grade
from users_app.models import Employee
from .models import ExpertSpecialty, ExpertProfile

OWNER_GROUP_VALUE = "__group__"


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
            Q(role="Руководитель направления") | Q(role="Директор")
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
            "expertise_direction", "grade",
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

        self.fields["country"].queryset = _active_countries_qs()
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["country"].empty_label = "---------"
        self.fields["country"].required = False

        if not self.instance or not self.instance.pk or not self.instance.country_id:
            russia = _active_countries_qs().filter(short_name="Россия").first()
            if russia:
                self.initial.setdefault("country", russia.pk)

        country_pk = self._resolve_fk("country")
        if country_pk:
            self.fields["region"].queryset = _active_regions_qs(country_pk)
        else:
            self.fields["region"].queryset = TerritorialDivision.objects.none()
        self.fields["region"].label_from_instance = lambda obj: obj.region_name
        self.fields["region"].empty_label = "---------"
        self.fields["region"].required = False

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
    class Meta:
        model = ExpertProfile
        fields = [
            "full_name_genitive", "self_employed", "tax_rate", "citizenship",
            "gender", "inn", "snils", "birth_date",
            "passport_series", "passport_number", "passport_issued_by",
            "passport_issue_date", "passport_expiry_date", "passport_division_code",
            "registration_address",
            "bank_name", "bank_swift", "bank_inn", "bank_bik",
            "settlement_account", "corr_account", "bank_address",
            "corr_bank_name", "corr_bank_address", "corr_bank_bik", "corr_bank_swift",
            "corr_bank_settlement_account", "corr_bank_corr_account",
        ]
        widgets = {
            "full_name_genitive": forms.TextInput(attrs={"class": "form-control"}),
            "self_employed": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "tax_rate": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "citizenship": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "inn": forms.TextInput(attrs={"class": "form-control"}),
            "snils": forms.TextInput(attrs={"class": "form-control", "placeholder": "000-000-000 00"}),
            "birth_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_series": forms.TextInput(attrs={"class": "form-control"}),
            "passport_number": forms.TextInput(attrs={"class": "form-control"}),
            "passport_issued_by": forms.TextInput(attrs={"class": "form-control"}),
            "passport_issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "passport_division_code": forms.TextInput(attrs={"class": "form-control"}),
            "registration_address": forms.TextInput(attrs={"class": "form-control"}),
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
        }
