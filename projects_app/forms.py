from django import forms
from django.db import models
from django.db.models import Max
from django.utils import timezone
from datetime import datetime

from classifiers_app.models import OKSMCountry, OKVCurrency, LegalEntityIdentifier, TerritorialDivision
from group_app.models import GroupMember
from policy_app.models import (
    DIRECTION_DIRECTOR_GROUP,
    PROJECTS_HEAD_GROUP,
    Product,
    TypicalSection,
)
from users_app.models import Employee

from .models import LegalEntity, Performer, ProjectRegistration, WorkVolume

_common_input = {"class": "form-control form-control-sm"}
_common_select = {"class": "form-select form-select-sm"}
_common_date = {"class": "form-control form-control-sm", "type": "date"}

# Форматы для дат
DATE_FMT_UI = "%d.%m.%y"  # ДД.ММ.ГГ

READONLY_INPUT = {
    **_common_input,
    "class": _common_input["class"] + " readonly-field",
    "readonly": True,
    "tabindex": "-1",
}

# ------ Миксин для bootstrap-классов ------
class BootstrapMixin:
    def _bootstrapify(self):
        for name, field in self.fields.items():
            w = field.widget
            # Select / MultiSelect -> form-select, остальное -> form-control
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                need = "form-select"
            else:
                need = "form-control"
            # бережно добавляем класс, не перетирая существующие
            existing = w.attrs.get("class", "")
            classes = set(filter(None, existing.split()))
            classes.add(need)
            w.attrs["class"] = " ".join(classes)

# ------ Форма регистрации ------
DATE_INPUT_ATTRS = {"type": "date"}
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]
DATE_WIDGET_FORMAT = "%Y-%m-%d"


def _date_input_widget():
    return forms.DateInput(format=DATE_WIDGET_FORMAT, attrs=DATE_INPUT_ATTRS)


def _parse_project_form_date(raw_value):
    value = str(raw_value or "").strip()
    if not value:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _project_region_choices_for_country(country_id, current_value="", as_of=None):
    choices = []
    seen = set()
    normalized_country_id = None
    if country_id not in (None, ""):
        try:
            normalized_country_id = int(country_id)
        except (TypeError, ValueError):
            normalized_country_id = None
    if normalized_country_id:
        qs = TerritorialDivision.objects.filter(country_id=normalized_country_id)
        if as_of:
            qs = qs.filter(effective_date__lte=as_of).filter(
                models.Q(abolished_date__isnull=True) | models.Q(abolished_date__gte=as_of)
            )
        for region_name in qs.order_by("region_name", "id").values_list("region_name", flat=True):
            if not region_name or region_name in seen:
                continue
            seen.add(region_name)
            choices.append(region_name)
    current_region = str(current_value or "").strip()
    if current_region and current_region not in seen:
        choices.append(current_region)
    return choices

PROJECT_MANAGER_ROLES = (PROJECTS_HEAD_GROUP, DIRECTION_DIRECTOR_GROUP)


def _employee_full_name(employee):
    parts = [
        employee.user.last_name.strip(),
        employee.user.first_name.strip(),
        employee.patronymic.strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _employee_prs_id(employee):
    return (getattr(employee, "formatted_prs_id", "") or "").strip()


def _strip_prs_suffix(label):
    label = (label or "").strip()
    if not label.endswith(")"):
        return label
    name, separator, suffix = label.rpartition(" (")
    prs_suffix = suffix[:-1].strip()
    if separator and (prs_suffix.startswith("ID-PRS-") or prs_suffix.endswith("-PRS")):
        return name.strip()
    return label


def _project_manager_queryset():
    return (
        Employee.objects
        .select_related("user", "person_record")
        .filter(role__in=PROJECT_MANAGER_ROLES)
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )


def _employee_queryset():
    return (
        Employee.objects
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )


def _employee_choices(queryset, current_value="", *, include_missing_current=True, use_prs_value=False, show_prs_label=False):
    choices = [("", "— Не выбрано —")]
    current_value = (current_value or "").strip()
    current_in_choices = False

    for employee in queryset:
        full_name = _employee_full_name(employee)
        if not full_name:
            continue
        prs_id = _employee_prs_id(employee)
        value = (prs_id if use_prs_value else "") or full_name
        label = f"{full_name} ({prs_id})" if show_prs_label and prs_id else full_name
        choices.append((value, label))
        if current_value in {value, full_name, prs_id}:
            current_in_choices = True

    if include_missing_current and current_value and not current_in_choices:
        missing_label = current_value if show_prs_label else _strip_prs_suffix(current_value)
        choices.insert(1, (current_value, missing_label))

    return choices


def _project_manager_choices(current_value="", *, show_prs_label=True):
    return _employee_choices(
        _project_manager_queryset(),
        current_value,
        use_prs_value=True,
        show_prs_label=show_prs_label,
    )


def _resolve_project_manager_choice(value):
    raw = (value or "").strip()
    if not raw:
        return "", ""

    employees = list(_project_manager_queryset())
    normalized = " ".join(raw.replace("\xa0", " ").split()).casefold()
    for employee in employees:
        if _employee_prs_id(employee).casefold() == normalized:
            return _employee_full_name(employee), _employee_prs_id(employee)
    for employee in employees:
        if _employee_full_name(employee).casefold() == normalized:
            return _employee_full_name(employee), _employee_prs_id(employee)
    return raw, ""


def _typical_section_specialty_ids(typical_section_id):
    if not typical_section_id:
        return []
    try:
        typical_section_pk = int(typical_section_id)
    except (TypeError, ValueError):
        return []
    return list(
        TypicalSection.objects
        .filter(pk=typical_section_pk)
        .values_list("specialties__pk", flat=True)
        .exclude(specialties__pk__isnull=True)
        .distinct()
    )


def _all_employee_choices(current_value="", typical_section_id=None):
    queryset = _employee_queryset()
    include_missing_current = True

    if typical_section_id:
        specialty_ids = _typical_section_specialty_ids(typical_section_id)
        if specialty_ids:
            queryset = queryset.filter(expert_profile__specialties__pk__in=specialty_ids).distinct()
        else:
            queryset = queryset.none()
        include_missing_current = False

    return _employee_choices(
        queryset,
        current_value,
        include_missing_current=include_missing_current,
    )


def _next_project_number():
    current_max = ProjectRegistration.objects.aggregate(max_number=Max("number")).get("max_number")
    if current_max is None:
        return 3333
    return 9999 if current_max >= 9999 else current_max + 1

def _group_choices(current_value=""):
    return (
        GroupMember.objects
        .exclude(country_alpha2="")
        .order_by("position", "id")
    )


class ProjectRegistrationForm(BootstrapMixin, forms.ModelForm):
    number = forms.IntegerField(
        label="Номер",
        required=True,
        min_value=0,
        max_value=9999,
        widget=forms.NumberInput(
            attrs={
                "id": "registration-number-input",
                "min": 0,
                "max": 9999,
                "step": 1,
                "placeholder": "0001",
                "autocomplete": "off",
            }
        ),
    )
    deadline = forms.DateField(required=False,
                               widget=_date_input_widget(),
                               input_formats=DATE_INPUT_FORMATS)
    evaluation_date = forms.DateField(
        label="Дата оценки",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    group_member = forms.ModelChoiceField(
        label="Группа",
        queryset=GroupMember.objects.none(),
        required=True,
        widget=forms.Select(attrs={"id": "registration-group-select"}),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "reg-country-select"}),
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"id": "reg-region-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True,
            "tabindex": "-1",
            "class": "form-control readonly-field",
            "id": "reg-identifier-field",
        }),
    )
    project_manager = forms.ChoiceField(
        label="Руководитель проекта",
        required=False,
        choices=(),
        widget=forms.Select(),
    )
    registration_date = forms.DateField(
        label="Дата регистр.",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    asset_owner = forms.CharField(
        label="Владелец активов",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Искать по наименованию и регистрационному номеру",
                "id": "reg-asset-owner-field",
            }
        ),
    )
    asset_owner_matches_customer = forms.BooleanField(
        label="Совпадает с Заказчиком",
        required=False,
        initial=True,
    )
    asset_owner_country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "reg-asset-owner-country-select"}),
    )
    asset_owner_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"id": "reg-asset-owner-region-select"}),
    )
    asset_owner_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True,
            "tabindex": "-1",
            "class": "form-control readonly-field",
            "id": "reg-asset-owner-identifier-field",
        }),
    )
    asset_owner_registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    contract_start = forms.DateField(required=False,
                                     widget=_date_input_widget(),
                                     input_formats=DATE_INPUT_FORMATS)
    contract_end = forms.DateField(required=False,
                                   widget=_date_input_widget(),
                                   input_formats=DATE_INPUT_FORMATS)
    input_data = forms.IntegerField(
        label="Исх. данные, дней",
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1, "class": "form-control js-input-data"}),
    )
    stage1_weeks = forms.DecimalField(
        label="Срок подготовки Предварительного отчёта, мес.",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "class": "form-control readonly-field js-stage1-weeks",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )
    stage1_end = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage1-end readonly-field", "readonly": True}
        ),
    )
    completion_calc = forms.DateField(
        label="Оконч., расчет",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control js-completion-calc readonly-field", "readonly": True}),
    )
    stage2_weeks = forms.DecimalField(
        label="Срок подготовки Итогового отчёта, нед.",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "class": "form-control readonly-field js-stage2-weeks",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )
    stage2_end = forms.DateField(
        label="Дата Итогового отчёта",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={"class": "form-control js-date js-stage2-end"}
        ),
    )
    stage1_date = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={"class": "form-control js-date js-stage1-date"}
        ),
    )
    stage3_weeks = forms.DecimalField(
        label="Этап 3, недель",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1", "class": "form-control js-stage3-weeks"}),
    )
    stage3_end = forms.DateField(
        label="Этап 3, оконч.",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage3-end readonly-field", "readonly": True}
        ),
    )
    term_weeks = forms.DecimalField(
        label="Срок, недель",
        required=False,
        decimal_places=1,
        max_digits=5,
        disabled=True,
        widget=forms.NumberInput(attrs={"class": "form-control js-term-weeks readonly-field", "readonly": True}),
    )
    type_ids = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ProjectRegistration
        fields = [
            "number", "group_member", "agreement_type", "agreement_number", "name",
            "status", "deadline", "year", "evaluation_date",
            "country", "customer", "identifier", "registration_number",
            "registration_region", "registration_date", "project_manager",
            "asset_owner", "asset_owner_matches_customer", "asset_owner_country", "asset_owner_identifier",
            "asset_owner_registration_number", "asset_owner_region",
            "asset_owner_registration_date",
            "contract_start", "contract_end", "completion_calc",
            "input_data", "stage1_weeks", "stage1_end",
            "stage2_weeks", "stage2_end", "stage3_weeks",
        ]
        widgets = {
            "year": forms.NumberInput(attrs={"placeholder": "ГГГГ"}),
            "customer": forms.TextInput(attrs={"placeholder": "Искать по наименованию и регистрационному номеру"}),
        }

    def __init__(self, *args, **kwargs):
        self.allow_multiple_products = kwargs.pop("allow_multiple_products", True)
        super().__init__(*args, **kwargs)
        current_group_member = self.data.get("group_member") or (self.instance.group_member_id if self.instance else "")
        if self.data:
            current_manager = self.data.get("project_manager") or ""
        else:
            instance_manager = self.instance.project_manager if self.instance else ""
            _manager_name, resolved_manager_prs_id = _resolve_project_manager_choice(instance_manager)
            current_manager = (
                (self.instance.project_manager_prs_id if self.instance else "")
                or resolved_manager_prs_id
                or instance_manager
            )
        self.fields["group_member"].queryset = _group_choices(current_group_member)
        self.fields["group_member"].label_from_instance = lambda obj: obj.group_display_label
        self.fields["group_member"].empty_label = "— Не выбрано —"
        self.fields["project_manager"].choices = _project_manager_choices(current_manager, show_prs_label=False)
        if not self.data:
            self.initial["project_manager"] = current_manager
            self.fields["project_manager"].initial = current_manager

        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and (self.instance.country_id or self.instance.asset_owner_country_id):
            country_ids = [
                value
                for value in [self.instance.country_id, self.instance.asset_owner_country_id]
                if value
            ]
            country_qs = (country_qs | OKSMCountry.objects.filter(pk__in=country_ids)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["asset_owner_country"].queryset = country_qs
        self.fields["asset_owner_country"].label_from_instance = lambda obj: obj.short_name

        if self.instance and self.instance.pk and self.instance.identifier:
            self.fields["identifier"].initial = self.instance.identifier
        if self.instance and self.instance.pk and self.instance.asset_owner_identifier:
            self.fields["asset_owner_identifier"].initial = self.instance.asset_owner_identifier

        self._bootstrapify()
        if self.instance and self.instance.pk and self.instance.stage1_end:
            self.fields["stage1_date"].initial = self.instance.stage1_end
        self.fields["asset_owner_matches_customer"].widget.attrs["class"] = "form-check-input"
        if not self.instance.pk and "group_member" not in self.data:
            self.fields["group_member"].initial = (
                GroupMember.objects
                .filter(country_alpha2="RU")
                .order_by("position", "id")
                .values_list("pk", flat=True)
                .first()
            )
        if not self.instance.pk and "country" not in self.data:
            russia = country_qs.filter(short_name="Россия").first()
            if russia:
                self.fields["country"].initial = russia.pk
                lei = LegalEntityIdentifier.objects.filter(country=russia).values_list("identifier", flat=True).first()
                if lei:
                    self.fields["identifier"].initial = lei
        customer_country_id = (
            self.data.get("country")
            if self.is_bound
            else (getattr(self.instance, "country_id", None) or self.fields["country"].initial)
        )
        customer_region = (
            self.data.get("registration_region")
            if self.is_bound
            else getattr(self.instance, "registration_region", "")
        )
        customer_registration_date = (
            _parse_project_form_date(self.data.get("registration_date"))
            if self.is_bound
            else getattr(self.instance, "registration_date", None)
        )
        region_choices = [("", "---------")]
        region_choices.extend(
            (name, name)
            for name in _project_region_choices_for_country(
                customer_country_id,
                current_value=customer_region,
                as_of=customer_registration_date,
            )
        )
        self.fields["registration_region"].choices = region_choices
        asset_owner_country_id = (
            self.data.get("asset_owner_country")
            if self.is_bound
            else getattr(self.instance, "asset_owner_country_id", None)
        )
        asset_owner_region = (
            self.data.get("asset_owner_region")
            if self.is_bound
            else getattr(self.instance, "asset_owner_region", "")
        )
        asset_owner_registration_date = (
            _parse_project_form_date(self.data.get("asset_owner_registration_date"))
            if self.is_bound
            else getattr(self.instance, "asset_owner_registration_date", None)
        )
        asset_owner_region_choices = [("", "---------")]
        asset_owner_region_choices.extend(
            (name, name)
            for name in _project_region_choices_for_country(
                asset_owner_country_id,
                current_value=asset_owner_region,
                as_of=asset_owner_registration_date,
            )
        )
        self.fields["asset_owner_region"].choices = asset_owner_region_choices
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year
        if not self.instance.pk and "number" not in self.data:
            self.fields["number"].initial = _next_project_number()
        if not self.instance.pk and "asset_owner_matches_customer" not in self.data:
            self.fields["asset_owner_matches_customer"].initial = True

    def clean_group_member(self):
        member = self.cleaned_data.get("group_member")
        if member and not (member.country_alpha2 or "").strip():
            raise forms.ValidationError("Для выбранной строки состава группы не заполнен код Альфа-2.")
        return member

    def clean_project_manager(self):
        manager_name, manager_prs_id = _resolve_project_manager_choice(self.cleaned_data.get("project_manager"))
        self._cleaned_project_manager_prs_id = manager_prs_id
        return manager_name

    def clean_input_data(self):
        return self.cleaned_data.get("input_data") or 0

    def clean_stage1_weeks(self):
        return self.cleaned_data.get("stage1_weeks") or 0

    def clean_stage2_weeks(self):
        return self.cleaned_data.get("stage2_weeks") or 0

    def clean_stage3_weeks(self):
        return self.cleaned_data.get("stage3_weeks") or 0

    def clean_registration_region(self):
        return (self.cleaned_data.get("registration_region") or "").strip()

    def clean_asset_owner_region(self):
        return (self.cleaned_data.get("asset_owner_region") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.project_manager_prs_id = getattr(self, "_cleaned_project_manager_prs_id", "") or ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        product_ids = []
        raw_product_ids = self.data.getlist("type_id") if hasattr(self.data, "getlist") else self.data.get("type_id", [])
        if not isinstance(raw_product_ids, (list, tuple)):
            raw_product_ids = [raw_product_ids]
        for raw_id in raw_product_ids:
            raw_id = str(raw_id or "").strip()
            if not raw_id:
                continue
            try:
                product_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue

        seen = set()
        normalized_ids = []
        for product_id in product_ids:
            if product_id in seen:
                continue
            seen.add(product_id)
            normalized_ids.append(product_id)

        valid_ids = list(
            Product.objects
            .filter(pk__in=normalized_ids)
            .order_by("position", "id")
            .values_list("pk", flat=True)
        )
        valid_set = set(valid_ids)
        ordered_valid_ids = [product_id for product_id in normalized_ids if product_id in valid_set]
        if not ordered_valid_ids:
            self.add_error("type_ids", "Укажите хотя бы один продукт.")
        elif not self.allow_multiple_products and len(ordered_valid_ids) > 1:
            self.add_error("type_ids", "Для строки проекта можно выбрать только один продукт.")
        self.cleaned_type_ids = ordered_valid_ids
        if cleaned_data.get("asset_owner_matches_customer"):
            cleaned_data["asset_owner"] = cleaned_data.get("customer") or ""
            cleaned_data["asset_owner_country"] = cleaned_data.get("country")
            cleaned_data["asset_owner_region"] = cleaned_data.get("registration_region") or ""
            cleaned_data["asset_owner_identifier"] = cleaned_data.get("identifier") or ""
            cleaned_data["asset_owner_registration_number"] = cleaned_data.get("registration_number") or ""
            cleaned_data["asset_owner_registration_date"] = cleaned_data.get("registration_date")
        elif asset_owner_country := cleaned_data.get("asset_owner_country"):
            cleaned_data["asset_owner_identifier"] = (
                LegalEntityIdentifier.objects.filter(country=asset_owner_country)
                .values_list("identifier", flat=True)
                .first()
                or ""
            )
        return cleaned_data


class ContractConditionsForm(BootstrapMixin, forms.ModelForm):
    contract_start = forms.DateField(required=False,
                                     widget=_date_input_widget(),
                                     input_formats=DATE_INPUT_FORMATS)
    contract_end = forms.DateField(required=False,
                                   widget=_date_input_widget(),
                                   input_formats=DATE_INPUT_FORMATS)
    input_data = forms.IntegerField(
        label="Исх. данные, дней",
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1, "class": "form-control js-input-data"}),
    )
    stage1_weeks = forms.DecimalField(
        label="Срок подготовки Предварительного отчёта, мес.",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "class": "form-control readonly-field js-stage1-weeks",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )
    stage1_end = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage1-end readonly-field", "readonly": True}
        ),
    )
    completion_calc = forms.DateField(
        label="Оконч., расчет",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control js-completion-calc readonly-field", "readonly": True}),
    )
    stage2_weeks = forms.DecimalField(
        label="Срок подготовки Итогового отчёта, нед.",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "class": "form-control readonly-field js-stage2-weeks",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )
    stage2_end = forms.DateField(
        label="Дата Итогового отчёта",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={"class": "form-control js-date js-stage2-end"}
        ),
    )
    stage1_date = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={"class": "form-control js-date js-stage1-date"}
        ),
    )
    stage3_weeks = forms.DecimalField(
        label="Этап 3, недель",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1", "class": "form-control js-stage3-weeks"}),
    )
    stage3_end = forms.DateField(
        label="Этап 3, оконч.",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage3-end readonly-field", "readonly": True}
        ),
    )
    term_weeks = forms.DecimalField(
        label="Срок, недель",
        required=False,
        decimal_places=1,
        max_digits=5,
        disabled=True,
        widget=forms.NumberInput(attrs={"class": "form-control js-term-weeks readonly-field", "readonly": True}),
    )

    class Meta:
        model = ProjectRegistration
        fields = [
            "agreement_type", "agreement_number",
            "contract_start", "contract_end", "completion_calc",
            "input_data", "stage1_weeks", "stage1_end",
            "stage2_weeks", "stage2_end", "stage3_weeks",
            "contract_subject",
        ]
        widgets = {
            "contract_subject": forms.Textarea(
                attrs={"rows": 6, "style": "max-height:36vh; overflow:auto; resize:vertical;"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        if self.instance and self.instance.pk and self.instance.stage1_end:
            self.fields["stage1_date"].initial = self.instance.stage1_end

    def clean_input_data(self):
        return self.cleaned_data.get("input_data") or 0

    def clean_stage1_weeks(self):
        return self.cleaned_data.get("stage1_weeks") or 0

    def clean_stage2_weeks(self):
        return self.cleaned_data.get("stage2_weeks") or 0

    def clean_stage3_weeks(self):
        return self.cleaned_data.get("stage3_weeks") or 0

class ProjectChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = getattr(obj, "type_short_display", "") or ""
        name_label = obj.name or ""
        parts = [obj.short_uid]
        if type_label:
            parts.append(str(type_label))
        if name_label:
            parts.append(name_label)
        return " ".join(parts)


CONSTRAINT_TYPE_CHOICES = (
    ("", "Нет ограничения"),
    ("asap", "ASAP — Как можно раньше"),
    ("alap", "ALAP — Как можно позже"),
    ("snet", "SNET — Начать не раньше"),
    ("snlt", "SNLT — Начать не позже"),
    ("fnet", "FNET — Закончить не раньше"),
    ("fnlt", "FNLT — Закончить не позже"),
    ("mso",  "MSO — Фиксированное начало"),
    ("mfo",  "MFO — Фиксированное окончание"),
)

# Mirrors the lightbox `type` <select> in policy-panels.js (gantt.config.lightbox.sections > "type").
TASK_TYPE_CHOICES = (
    ("task", "Задача"),
    ("project", "Родительская задача"),
    ("milestone", "Веха"),
    ("service_section", "Раздел (услуга)"),
)
SERVICE_SECTION_TYPE = "service_section"


class ProjectScheduleTaskForm(BootstrapMixin, forms.Form):
    """Plain form that produces a DHTMLX-shaped task dict.

    Used by the table view's Add/Edit buttons. The actual persistence happens
    in `projects_app.services.gantt_tasks` against `ProjectRegistration.gantt_data`,
    so this form is intentionally NOT a ModelForm.
    """

    type = forms.ChoiceField(
        label="Тип",
        required=False,
        choices=TASK_TYPE_CHOICES,
        initial="task",
    )
    # In Gantt parlance: when type == service_section, this picks the service
    # section ("Название раздела (услуг)") and `task`/text holds the optional
    # display name. Choices are populated in `__init__` from the project's
    # primary product.
    service_section_name = forms.ChoiceField(
        label="Название раздела (услуг)",
        required=False,
        choices=[("", "—")],
    )
    task = forms.CharField(label="Название", required=False, max_length=255)
    start_date = forms.DateField(
        label="Начало",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    end_date = forms.DateField(
        label="Окончание",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    # Specialty/executor are closed dropdowns sharing options with the Gantt
    # lightbox (see `policy_app.views._typical_service_term_*_options`). The
    # choices are populated in `__init__` so the form picks up live DB values.
    # Each executor `<option>` carries a `data-specialties` attribute so the
    # form template can filter executors client-side based on the selected
    # specialty - mirroring the lightbox UX exactly.
    specialty = forms.ChoiceField(
        label="Специальность",
        required=False,
        choices=[("", "—")],
    )
    executor = forms.ChoiceField(
        label="Исполнитель",
        required=False,
        choices=[("", "—")],
    )
    deadline = forms.DateField(
        label="Дедлайн",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    constraint_type = forms.ChoiceField(
        label="Тип ограничения",
        required=False,
        choices=CONSTRAINT_TYPE_CHOICES,
    )
    constraint_date = forms.DateField(
        label="Дата ограничения",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    duration = forms.IntegerField(
        label="Длительность (рабочие дни)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": "0", "step": "1"}),
    )
    duration_star = forms.IntegerField(
        label="Длительность (календарные дни)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": "0", "step": "1"}),
    )
    predecessors = forms.CharField(
        label="Предшественники",
        required=False,
        max_length=255,
        # Read-only: this field only mirrors the actual link state computed from
        # gantt_data["links"]. Editing of predecessors happens in the Gantt
        # diagram (Связи panel inside the lightbox), not in the table form.
        widget=forms.TextInput(attrs={"readonly": "readonly", "class": "readonly-field"}),
    )
    progress = forms.IntegerField(
        label="Прогресс",
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={"min": "0", "max": "100", "step": "1"}),
    )

    def __init__(self, *args, registration=None, **kwargs):
        self._registration = registration
        super().__init__(*args, **kwargs)
        self._populate_assignment_choices()
        self._populate_section_choices()
        self._bootstrapify()

    def _populate_section_choices(self):
        """Populate the service-section dropdown from the project's primary product.

        Sections come from the same helper the Gantt uses
        (`policy_app.views._typical_service_term_section_options`), so the
        table form and the diagram lightbox always offer the same list.
        """
        from policy_app.views import _typical_service_term_section_options
        product_id = None
        if self._registration is not None:
            primary = self._registration.primary_product
            product_id = (
                getattr(primary, "pk", None)
                or getattr(self._registration.type, "pk", None)
            )
        sections = _typical_service_term_section_options(product_id) if product_id else []
        labels = [item["label"] for item in sections]
        initial_section = str(self.initial.get("service_section_name") or "").strip()
        if initial_section and initial_section not in labels:
            labels.append(initial_section)
        self.fields["service_section_name"].choices = [("", "—")] + [(s, s) for s in labels]
        # Stash the per-section specialty list so the template can mirror the
        # lightbox's "section drives specialty options" behaviour if needed.
        self.section_options = sections

    def _populate_assignment_choices(self):
        """Populate specialty / executor dropdowns from the same source the Gantt lightbox uses.

        Existing values that are no longer in the live option list are still
        appended so previously-saved tasks remain editable (backward compat).
        """
        from policy_app.views import (
            _typical_service_term_specialty_options,
            _typical_service_term_executor_options,
        )
        specialties = list(_typical_service_term_specialty_options())
        executors = list(_typical_service_term_executor_options())

        initial_specialty = str(self.initial.get("specialty") or "").strip()
        if initial_specialty and initial_specialty not in specialties:
            specialties.append(initial_specialty)
        self.fields["specialty"].choices = [("", "—")] + [(s, s) for s in specialties]

        initial_executor = str(self.initial.get("executor") or "").strip()
        executor_values = {item.get("value") for item in executors if item.get("value")}
        if initial_executor and initial_executor not in executor_values:
            # Show the legacy/orphan value as-is so the user can clear or keep it.
            executors.append({
                "value": initial_executor,
                "label": initial_executor,
                "specialties": [initial_specialty] if initial_specialty else [],
            })
        self.fields["executor"].choices = [("", "—")] + [
            (item["value"], item["label"]) for item in executors if item.get("value")
        ]
        # Stash the full executor metadata so the template can render
        # data-specialties attributes for client-side filtering.
        self.executor_options = executors

    def clean_progress(self):
        return self.cleaned_data.get("progress") or 0

    def task_payload(self) -> dict:
        """Return a dict ready to be merged into a DHTMLX task object.

        Date fields are serialized to ISO strings (`YYYY-MM-DD`); empty
        optional values map to `None` so the service layer can clear them
        out of the existing task. The `predecessors` field is returned
        as a list of strings (WBS or task ids) to be resolved against the
        live payload by the service.
        """
        cleaned = self.cleaned_data
        def _iso(value):
            return value.isoformat() if value else None
        constraint_type = (cleaned.get("constraint_type") or "").lower() or None
        task_type = (cleaned.get("type") or "task").strip() or "task"
        section_name = (cleaned.get("service_section_name") or "").strip()
        text = cleaned.get("task") or ""
        # Mirror the Gantt lightbox `policy_task_name.get_value`: when the task
        # is a service section, persist the section under `service_section_name`
        # and let the display text fall back to the section name when blank.
        if task_type == SERVICE_SECTION_TYPE:
            display_text = text or section_name
        else:
            display_text = text
            section_name = ""
        payload = {
            "type": task_type,
            "text": display_text,
            "start_date": _iso(cleaned.get("start_date")),
            "end_date": _iso(cleaned.get("end_date")),
            "specialty": cleaned.get("specialty") or "",
            "executor": cleaned.get("executor") or "",
            "deadline": _iso(cleaned.get("deadline")),
            "constraint_type": constraint_type,
            "constraint_date": _iso(cleaned.get("constraint_date")),
            "duration": int(cleaned["duration"]) if cleaned.get("duration") is not None else None,
            "duration_star": int(cleaned["duration_star"]) if cleaned.get("duration_star") is not None else None,
            "progress": int(cleaned.get("progress") or 0),
            # Predecessors are intentionally NOT submitted from the table form —
            # the field is read-only there and only reflects current link state.
            # `None` tells the service layer to leave existing links untouched.
            "predecessors": None,
        }
        # Only emit service_section_name when it's set; otherwise let the
        # service layer drop the key from the stored task.
        payload["service_section_name"] = section_name or None
        return payload


class WorkVolumeForm(BootstrapMixin, forms.ModelForm):
    project = ProjectChoiceField(
        queryset=ProjectRegistration.objects.order_by("-id"),
        label="Проект",
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "work-country-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True, "tabindex": "-1",
            "class": "readonly-field",
            "id": "work-identifier-field",
        }),
    )
    registration_date = forms.DateField(
        label="Дата",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    manager = forms.ChoiceField(
        label="Менеджер проекта",
        required=False,
        choices=(),
    )

    class Meta:
        model = WorkVolume
        fields = [
            "project", "type", "name", "asset_name",
            "country", "identifier",
            "registration_number", "registration_date", "manager",
        ]
        widgets = {
            "type": forms.TextInput(attrs={"readonly": True, "tabindex": "-1", "class": "readonly-field"}),
            "name": forms.TextInput(attrs={"readonly": True, "tabindex": "-1", "class": "readonly-field"}),
            "asset_name": forms.TextInput(attrs={"placeholder": "Искать по наименованию и регистрационному номеру"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            current_manager = self.data.get("manager") or ""
        else:
            instance_manager = self.instance.manager if self.instance else ""
            _manager_name, resolved_manager_prs_id = _resolve_project_manager_choice(instance_manager)
            current_manager = resolved_manager_prs_id or instance_manager
        self.fields["manager"].choices = _project_manager_choices(current_manager)

        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if not self.data and not current_manager and getattr(self.instance, "project_id", None):
            _project_manager_name, project_manager_prs_id = _resolve_project_manager_choice(
                self.instance.project.project_manager or ""
            )
            self.fields["manager"].initial = project_manager_prs_id or self.instance.project.project_manager or ""
        elif not self.data and current_manager:
            self.fields["manager"].initial = current_manager
        if not self.data and getattr(self.instance, "project_id", None):
            self.fields["type"].initial = getattr(self.instance.project, "type_short_display", "") or ""
            self.fields["name"].initial = self.instance.project.name or ""
        self._bootstrapify()

    def clean_manager(self):
        manager_name, _manager_prs_id = _resolve_project_manager_choice(self.cleaned_data.get("manager"))
        return manager_name

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.project_id:
            instance.type = getattr(instance.project, "type_short_display", "") or ""
            instance.name = instance.project.name or ""
        if commit:
            instance.save()
        return instance

class PerformerForm(forms.ModelForm):
    registration = ProjectChoiceField(
        queryset=ProjectRegistration.objects.order_by("-id"),
        label="Проект",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # Актив — как выпадающий, опции наполним в шаблоне/JS
    asset_name = forms.ChoiceField(
        choices=[("", "— Не выбрано —")],
        required=False,
        label="Актив",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    # Типовой раздел — тоже выпадающий, заполним по типу продукта выбранной регистрации
    typical_section = forms.ModelChoiceField(
        queryset=TypicalSection.objects.none(),
        required=False,
        label="Типовой раздел",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    executor = forms.ChoiceField(
        label="Исполнитель",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Performer
        fields = [
            "registration", "asset_name", "executor", "grade", "grade_name",
            "currency", "typical_section",
            "actual_costs", "estimated_costs", "agreed_amount",
        ]
        widgets = {
            "grade": forms.HiddenInput(),
            "grade_name": forms.HiddenInput(),
            "actual_costs": forms.TextInput(attrs={"class": "form-control js-money-input", "inputmode": "decimal"}),
            "estimated_costs": forms.HiddenInput(),
            "agreed_amount": forms.HiddenInput(),
        }

    _money_fields = ("actual_costs", "estimated_costs", "agreed_amount")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            data = self.data.copy()
            for fn in self._money_fields:
                v = data.get(fn, "")
                if v:
                    data[fn] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            self.data = data
        current_executor = self.data.get("executor") or (self.instance.executor if self.instance else "")
        current_typical_section_id = (
            self.data.get("typical_section")
            or (self.instance.typical_section_id if self.instance else None)
        )
        self.fields["executor"].choices = _all_employee_choices(
            current_executor,
            typical_section_id=current_typical_section_id,
        )

        today = timezone.now().date()
        currency_qs = OKVCurrency.objects.filter(
            models.Q(approval_date__isnull=True) | models.Q(approval_date__lte=today),
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)).distinct().order_by("code_alpha")
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        if not (self.instance and self.instance.pk):
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.initial["currency"] = rub.pk

    @staticmethod
    def _clean_money(value):
        if not value:
            return value
        return str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")

    def clean_actual_costs(self):
        return self._clean_money(self.cleaned_data.get("actual_costs"))

    def clean_estimated_costs(self):
        return self._clean_money(self.cleaned_data.get("estimated_costs"))

    def clean_agreed_amount(self):
        return self._clean_money(self.cleaned_data.get("agreed_amount"))

class WorkItemChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        project = getattr(obj.project, "short_uid", "")
        type_label = obj.type or ""
        name_label = obj.name or ""
        asset_label = obj.asset_name or name_label or ""
        header_parts = [part for part in (project, type_label, name_label) if part]
        header = " ".join(header_parts)
        if header and asset_label:
            return f"{header} — {asset_label}"
        return header or asset_label or f"Актив #{obj.pk}"


class LegalEntityForm(BootstrapMixin, forms.ModelForm):
    work_item = WorkItemChoiceField(
        queryset=WorkVolume.objects.select_related("project").order_by("-id"),
        label="Наименование актива",
    )
    country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "legal-country-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True, "tabindex": "-1",
            "class": "readonly-field",
            "id": "legal-identifier-field",
        }),
    )
    registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )

    class Meta:
        model = LegalEntity
        fields = [
            "work_item", "work_type", "work_name", "legal_name",
            "country", "identifier",
            "registration_number", "registration_date",
        ]
        widgets = {
            "work_type": forms.TextInput(attrs={"readonly": True, "tabindex": "-1", "class": "readonly-field"}),
            "work_name": forms.TextInput(attrs={"readonly": True, "tabindex": "-1", "class": "readonly-field"}),
            "legal_name": forms.TextInput(attrs={"placeholder": "Искать по наименованию и регистрационному номеру"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if not self.data and getattr(self.instance, "work_item_id", None):
            self.fields["work_type"].initial = (
                getattr(self.instance.work_item.project, "type_short_display", "") or ""
            )
            self.fields["work_name"].initial = self.instance.work_item.name or ""
        self._bootstrapify()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.work_item_id:
            instance.project = instance.work_item.project
            instance.work_type = getattr(instance.work_item.project, "type_short_display", "") or ""
            instance.work_name = instance.work_item.name or ""
        if commit:
            instance.save()
        return instance        