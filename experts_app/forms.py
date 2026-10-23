import json
from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry, TerritorialDivision
from contracts_app.forms import _ContractFileInput
from core.forms import lock_field, locked_attrs
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ExpertiseDirection,
    Grade,
)
from .models import ExpertContractDetails, ExpertProfile, ExpertSpecialty

OWNER_GROUP_VALUE = "__group__"
SPECIALIZATION_AREA_PREFIX = "Специалист по"


def _pairs_from_units(units):
    pairs = []
    for unit in units or []:
        company = getattr(unit, "company", None)
        pairs.append({
            "department": str(getattr(unit, "department_name", "") or "").strip(),
            "organization": str(getattr(company, "short_name", "") or "").strip(),
        })
    return pairs or [{"department": "", "organization": ""}]


def _specialty_direction_derived(directions):
    """Пары подразделение/организация для каждого направления."""
    from group_app.expertise_management import catalog_labels

    directions = list(directions)
    labels = catalog_labels([direction.pk for direction in directions])
    derived = {}
    for direction in directions:
        info = labels.get(direction.pk) or {}
        pairs = _pairs_from_units(info.get("units"))
        derived[direction.pk] = {
            "department": pairs[0]["department"],
            "organization": pairs[0]["organization"],
            "pairs": pairs,
        }
    return derived


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


class SpecialtyExpertiseSelect(forms.Select):
    """Направление экспертизы: у опции пары подразделение/организация."""

    derived = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        direction = getattr(value, "instance", None)
        info = self.derived.get(getattr(direction, "pk", None)) or {}
        option["attrs"]["data-department"] = info.get("department", "")
        option["attrs"]["data-organization"] = info.get("organization", "")
        option["attrs"]["data-pairs"] = json.dumps(info.get("pairs") or [], ensure_ascii=False)
        return option


class ExpertSpecialtyForm(forms.ModelForm):
    specialization_area_suffix = forms.CharField(
        label="Область специализации",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "область специализации",
        }),
    )
    department = forms.CharField(
        label="Подразделение",
        required=False,
        widget=forms.TextInput(attrs=locked_attrs(id="esp-department")),
    )
    organization = forms.CharField(
        label="Организация",
        required=False,
        widget=forms.TextInput(attrs=locked_attrs(id="esp-organization")),
    )

    class Meta:
        model = ExpertSpecialty
        fields = ["specialty", "specialty_en", "expertise_dir"]
        widgets = {
            "specialty": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Специальность",
            }),
            "specialty_en": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Specialty (English)",
            }),
            "expertise_dir": SpecialtyExpertiseSelect(attrs={
                "class": "form-select",
                "id": "esp-dir-select",
            }),
        }
        error_messages = {
            "specialty": {
                "unique": "Специальность с таким именем уже существует.",
            },
        }

    def __init__(self, *args, lock_expertise=False, locked_expertise_dir=None, allowed_expertise_dirs=None, **kwargs):
        self.lock_expertise = lock_expertise
        self.locked_expertise_dir = locked_expertise_dir
        self.allowed_expertise_dirs = list(allowed_expertise_dirs or [])
        self.missing_locked_direction = bool(
            lock_expertise and locked_expertise_dir is None and not self.allowed_expertise_dirs
        )
        super().__init__(*args, **kwargs)
        self.specialization_area_prefix = SPECIALIZATION_AREA_PREFIX

        current_specialization_area = ""
        if self.instance and self.instance.pk:
            current_specialization_area = self.instance.specialization_area or ""
        current_specialization_area = current_specialization_area.strip()
        if current_specialization_area.startswith(SPECIALIZATION_AREA_PREFIX):
            current_specialization_area = current_specialization_area[len(SPECIALIZATION_AREA_PREFIX):].strip()
        self.fields["specialization_area_suffix"].initial = current_specialization_area

        direction_qs = ExpertiseDirection.objects.select_related(
            "department", "department__company"
        ).order_by("position", "id")
        if self.allowed_expertise_dirs:
            direction_qs = direction_qs.filter(pk__in=[item.pk for item in self.allowed_expertise_dirs])
        if self.lock_expertise and not self.allowed_expertise_dirs:
            if self.locked_expertise_dir is not None:
                direction_qs = direction_qs.filter(pk=self.locked_expertise_dir.pk)
                self.fields["expertise_dir"].empty_label = None
                self.fields["expertise_dir"].initial = self.locked_expertise_dir.pk
                self.initial["expertise_dir"] = self.locked_expertise_dir.pk
            else:
                direction_qs = direction_qs.none()
            lock_field(self.fields["expertise_dir"], disabled=True, use_disabled_attr=True)
        self.fields["expertise_dir"].queryset = direction_qs
        self.fields["expertise_dir"].label_from_instance = (
            lambda obj: f"{obj.short_name} {obj.name}"
        )
        if self.allowed_expertise_dirs and self.locked_expertise_dir is None:
            self.fields["expertise_dir"].empty_label = None
            self.fields["expertise_dir"].initial = self.allowed_expertise_dirs[0].pk
            self.initial["expertise_dir"] = self.allowed_expertise_dirs[0].pk
        elif not (self.lock_expertise and self.locked_expertise_dir is not None):
            self.fields["expertise_dir"].empty_label = "---------"
        self.fields["expertise_dir"].required = False
        derived = _specialty_direction_derived(direction_qs)
        self.fields["expertise_dir"].widget.derived = derived
        pairs = self._derived_pairs(derived)
        self.managed_pairs = pairs
        department = pairs[0]["department"]
        organization = pairs[0]["organization"]
        self.fields["department"].initial = department
        self.fields["organization"].initial = organization
        if self.is_bound:
            self.data = self.data.copy()
            self.data[self.add_prefix("department")] = department
            self.data[self.add_prefix("organization")] = organization

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

    def _selected_direction_id(self):
        if self.locked_expertise_dir is not None:
            return self.locked_expertise_dir.pk
        if not self.is_bound and self.allowed_expertise_dirs:
            return self.allowed_expertise_dirs[0].pk
        if self.is_bound:
            raw = self.data.get(self.add_prefix("expertise_dir"))
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        if self.instance and self.instance.pk and self.instance.expertise_dir_id:
            return self.instance.expertise_dir_id
        return None

    def _derived_pairs(self, derived):
        info = derived.get(self._selected_direction_id()) or {}
        pairs = info.get("pairs") or [{"department": "", "organization": ""}]
        return pairs

    def clean(self):
        cleaned = super().clean()
        if self.missing_locked_direction:
            self.add_error(
                "expertise_dir",
                "Для вашего подразделения не задано направление экспертизы.",
            )
        elif self.allowed_expertise_dirs:
            allowed_ids = {item.pk for item in self.allowed_expertise_dirs}
            selected = cleaned.get("expertise_dir")
            if selected is None or selected.pk not in allowed_ids:
                self.add_error(
                    "expertise_dir",
                    "Можно выбрать только направление экспертизы своего подразделения.",
                )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        suffix = (self.cleaned_data.get("specialization_area_suffix") or "").strip()
        if suffix.startswith(SPECIALIZATION_AREA_PREFIX):
            suffix = suffix[len(SPECIALIZATION_AREA_PREFIX):].strip()
        obj.specialization_area = f"{SPECIALIZATION_AREA_PREFIX} {suffix}" if suffix else ""
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
            lock_field(self.fields[field_name], disabled=True)

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
        widget=forms.TextInput(attrs=locked_attrs()),
    )
    citizenship_country = forms.CharField(
        label="Страна гражданства (налоговая юрисдикция)",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs=locked_attrs()),
    )
    citizenship_status = forms.CharField(
        label="Статус",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs=locked_attrs()),
    )
    citizenship_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs=locked_attrs()),
    )
    citizenship_number = forms.CharField(
        label="Номер",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs=locked_attrs()),
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
        lock_field(self.fields["registration_address"], disabled=True)
        self.fields["full_name_genitive"].initial = instance.person_full_name_genitive
        lock_field(self.fields["full_name_genitive"], disabled=True)
        self.fields["gender"].initial = instance.person_gender
        lock_field(self.fields["gender"], disabled=True, use_disabled_attr=True)
        self.fields["birth_date"].initial = instance.person_birth_date
        lock_field(self.fields["birth_date"], disabled=True)
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
