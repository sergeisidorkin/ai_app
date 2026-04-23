import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import forms
from django.db import models
from django.db.models import Max
from django.utils import timezone

from classifiers_app.models import LegalEntityIdentifier, OKSMCountry, OKVCurrency, TerritorialDivision
from contracts_app.forms import _ContractFileInput
from group_app.models import GroupMember
from policy_app.models import Product, TypicalSection


sys.modules.setdefault("proposals_app.forms", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.forms", sys.modules[__name__])

from .models import (
    ProposalAsset,
    ProposalCommercialOffer,
    ProposalLegalEntity,
    ProposalObject,
    ProposalRegistration,
    ProposalRegistrationProduct,
    ProposalTemplate,
    ProposalVariable,
)
from .cbr import get_cbr_eur_rate_for_today, get_cbr_eur_rate_text

DATE_INPUT_ATTRS = {"class": "js-date", "autocomplete": "off"}
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]
PROPOSAL_TRAVEL_EXPENSES_LABEL = "Командировочные расходы, евро"
PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY = "Командировочные расходы"
PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL = "actual"
PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION = "calculation"
PROPOSAL_REPORT_LANGUAGE_LABELS = ("русский", "английский", "казахский", "китайский")
PROPOSAL_REPORT_LANGUAGE_ALIASES = {
    "ru": "русский",
    "russian": "русский",
    "русский": "русский",
    "en": "английский",
    "english": "английский",
    "английский": "английский",
    "kz": "казахский",
    "kk": "казахский",
    "kazakh": "казахский",
    "казахский": "казахский",
    "zh": "китайский",
    "cn": "китайский",
    "chinese": "китайский",
    "китайский": "китайский",
}

NON_EDITABLE_PROPOSAL_STATUSES = {
    ProposalRegistration.ProposalStatus.SENT,
    ProposalRegistration.ProposalStatus.COMPLETED,
}


def is_proposal_travel_expenses_name(value) -> bool:
    name = str(value or "").strip()
    return name in {PROPOSAL_TRAVEL_EXPENSES_LABEL, PROPOSAL_TRAVEL_EXPENSES_LABEL_LEGACY}


class DisabledOptionsSelect(forms.Select):
    def __init__(self, *args, disabled_values=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_values = {str(value) for value in (disabled_values or [])}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        option_value = option.get("value")
        if option_value is not None and str(option_value) in self.disabled_values:
            option["attrs"]["disabled"] = True
        return option


def normalize_proposal_report_languages(value) -> list[str]:
    if value in (None, ""):
        return ["русский"]
    if isinstance(value, (list, tuple)):
        raw_values = [str(item or "").strip() for item in value]
    else:
        raw_values = [
            item.strip()
            for item in str(value).replace(";", ",").replace("\n", ",").split(",")
        ]
    seen = set()
    for raw in raw_values:
        label = PROPOSAL_REPORT_LANGUAGE_ALIASES.get(raw.strip().lower())
        if label:
            seen.add(label)
    normalized = [label for label in PROPOSAL_REPORT_LANGUAGE_LABELS if label in seen]
    return normalized or ["русский"]


def _apply_russian_error_messages(field: forms.Field) -> None:
    field.error_messages["required"] = "Обязательное поле."

    if "max_length" in field.error_messages:
        field.error_messages["max_length"] = (
            "Убедитесь, что это значение содержит не более %(limit_value)s символов "
            "(сейчас %(show_value)s)."
        )
    if "min_length" in field.error_messages:
        field.error_messages["min_length"] = (
            "Убедитесь, что это значение содержит не менее %(limit_value)s символов "
            "(сейчас %(show_value)s)."
        )
    if "min_value" in field.error_messages:
        field.error_messages["min_value"] = "Значение должно быть не меньше %(limit_value)s."
    if "max_value" in field.error_messages:
        field.error_messages["max_value"] = "Значение должно быть не больше %(limit_value)s."

    if isinstance(field, forms.DateField):
        field.error_messages["invalid"] = "Введите дату в формате ДД.ММ.ГГГГ."
    elif isinstance(field, forms.IntegerField):
        field.error_messages["invalid"] = "Введите целое число."
    elif isinstance(field, forms.DecimalField):
        field.error_messages["invalid"] = "Введите число."
        if "max_digits" in field.error_messages:
            field.error_messages["max_digits"] = "Введите число не более чем с %(max)s цифрами."
        if "max_decimal_places" in field.error_messages:
            field.error_messages["max_decimal_places"] = (
                "Введите число не более чем с %(max)s знаками после запятой."
            )
        if "max_whole_digits" in field.error_messages:
            field.error_messages["max_whole_digits"] = (
                "Введите число не более чем с %(max)s цифрами до запятой."
            )

    if isinstance(field, forms.ModelChoiceField):
        field.error_messages["invalid_choice"] = "Выберите корректное значение."
        field.error_messages["invalid_pk_value"] = "Выберите корректное значение."
    elif isinstance(field, forms.ChoiceField):
        field.error_messages["invalid_choice"] = "Выберите корректное значение."


class BootstrapMixin:
    def _bootstrapify(self):
        for field in self.fields.values():
            widget = field.widget
            expected = "form-select" if isinstance(widget, (forms.Select, forms.SelectMultiple)) else "form-control"
            existing = widget.attrs.get("class", "")
            classes = set(filter(None, existing.split()))
            classes.add(expected)
            widget.attrs["class"] = " ".join(classes)


class _ProposalFileInput(_ContractFileInput):
    def value_from_datadict(self, data, files, name):
        upload = forms.FileInput.value_from_datadict(self, data, files, name)
        self.checked = self.clear_checkbox_name(name) in data
        if not self.is_required:
            clear = forms.CheckboxInput().value_from_datadict(
                data,
                files,
                self.clear_checkbox_name(name),
            )
            if clear and not upload:
                return False
        return upload


def _next_proposal_number():
    current_max = ProposalRegistration.objects.aggregate(max_number=Max("number")).get("max_number")
    if current_max is None:
        return 3333
    return 9999 if current_max >= 9999 else current_max + 1


def _group_choices():
    return GroupMember.objects.exclude(country_alpha2="").order_by("position", "id")


def _proposal_group_member_order_map():
    counters = {}
    result = {}
    for member in GroupMember.objects.all():
        key = member.country_code or member.country_name or ""
        idx = counters.get(key, 0)
        result[member.pk] = idx
        counters[key] = idx + 1
    return result


def _proposal_group_member_label(member, order):
    alpha2 = member.country_alpha2 or ""
    prefix = f"{alpha2}-{order}" if order else alpha2
    return f"{prefix} {member.short_name}"


def _proposal_group_member_short(member, order):
    alpha2 = member.country_alpha2 or ""
    return f"{alpha2}-{order}" if order else alpha2


def _proposal_variable_registry():
    from core.column_registry import COLUMN_REGISTRY

    proposals = COLUMN_REGISTRY.get("proposals", {})
    registry = proposals.get("tables", {}).get("registry", {})
    return {
        "proposals": {
            "label": proposals.get("label", "ТКП"),
            "tables": {
                "registry": {
                    "label": registry.get("label", "Реестр ТКП"),
                    "columns": registry.get("columns", {}),
                }
            },
        }
    }


def proposal_variable_registry_json():
    return json.dumps(_proposal_variable_registry(), ensure_ascii=False)


def _proposal_variable_section_choices():
    registry = _proposal_variable_registry()
    return [(key, value["label"]) for key, value in registry.items()]


def _proposal_variable_table_choices(section_key):
    registry = _proposal_variable_registry()
    section = registry.get(section_key, {})
    return [(key, value["label"]) for key, value in section.get("tables", {}).items()]


def _proposal_variable_column_choices(section_key, table_key):
    registry = _proposal_variable_registry()
    section = registry.get(section_key, {})
    table = section.get("tables", {}).get(table_key, {})
    return list(table.get("columns", {}).items())


def _parse_proposal_form_date(raw_value):
    value = str(raw_value or "").strip()
    if not value:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _proposal_region_choices_for_country(country_id, current_value="", as_of=None):
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
            qs = qs.filter(
                effective_date__lte=as_of,
            ).filter(
                models.Q(abolished_date__isnull=True) | models.Q(abolished_date__gte=as_of),
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


def _default_proposal_evaluation_date(today=None):
    today = today or timezone.now().date()
    if today < date(today.year, 7, 1):
        return date(today.year, 1, 1)
    return date(today.year, 6, 1)


def _proposal_request_list(data, key):
    if hasattr(data, "getlist"):
        return [str(value or "") for value in data.getlist(key)]
    value = data.get(key, [])
    if isinstance(value, (list, tuple)):
        return [str(item or "") for item in value]
    return [str(value or "")]


def _format_stage_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%d.%m.%Y")


class ProposalRegistrationForm(BootstrapMixin, forms.ModelForm):
    number = forms.IntegerField(
        label="Номер",
        required=True,
        min_value=0,
        max_value=9999,
        widget=forms.NumberInput(
            attrs={
                "id": "proposal-number-input",
                "min": 0,
                "max": 9999,
                "step": 1,
                "placeholder": "0001",
                "autocomplete": "off",
            }
        ),
    )
    group_member = forms.ModelChoiceField(
        label="Группа",
        queryset=GroupMember.objects.none(),
        required=True,
        widget=forms.Select(attrs={"id": "proposal-group-select"}),
    )
    status = forms.ChoiceField(
        label="Статус",
        required=True,
        choices=ProposalRegistration.ProposalStatus.choices,
        widget=DisabledOptionsSelect(disabled_values=NON_EDITABLE_PROPOSAL_STATUSES),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "proposal-country-select"}),
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"id": "proposal-region-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(
            attrs={
                "readonly": True,
                "tabindex": "-1",
                "class": "form-control readonly-field",
                "id": "proposal-identifier-field",
            }
        ),
    )
    registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )
    asset_owner = forms.CharField(
        label="Владелец активов",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Искать по наименованию и регистрационному номеру",
                "id": "proposal-asset-owner-field",
            }
        ),
    )
    asset_owner_country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "proposal-asset-owner-country-select"}),
    )
    asset_owner_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"id": "proposal-asset-owner-region-select"}),
    )
    asset_owner_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(
            attrs={
                "readonly": True,
                "tabindex": "-1",
                "class": "form-control readonly-field",
                "id": "proposal-asset-owner-identifier-field",
            }
        ),
    )
    asset_owner_registration_number = forms.CharField(
        label="Регистрационный номер",
        required=False,
    )
    asset_owner_registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=forms.TextInput(attrs={**DATE_INPUT_ATTRS, "id": "proposal-asset-owner-registration-date"}),
        input_formats=DATE_INPUT_FORMATS,
    )
    asset_owner_matches_customer = forms.BooleanField(
        label="Совпадает с Заказчиком",
        required=False,
        initial=True,
    )
    proposal_project_name = forms.CharField(
        label="Наименование ТКП (проекта)",
        required=False,
        widget=forms.TextInput(),
    )
    purpose = forms.CharField(
        label="Цель оказания услуг",
        required=False,
        widget=forms.Textarea(attrs={"rows": 1}),
    )
    service_composition = forms.CharField(
        label="Состав услуг",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    evaluation_date = forms.DateField(
        label="Дата оценки",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )
    service_term_months = forms.DecimalField(
        label="Срок подготовки Предварительного отчёта, мес.",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "readonly": True,
                "tabindex": "-1",
                "class": "readonly-field",
            }
        ),
    )
    preliminary_report_date = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )
    final_report_term_weeks = forms.DecimalField(
        label="Срок подготовки Итогового отчёта, нед.",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "step": "0.1",
                "readonly": True,
                "tabindex": "-1",
                "class": "readonly-field",
            }
        ),
    )
    final_report_date = forms.DateField(
        label="Дата Итогового отчёта",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )
    report_languages = forms.CharField(
        label="Языки отчёта",
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-report-languages"}),
    )
    service_cost = forms.DecimalField(
        label="Стоимость услуг",
        required=False,
        min_value=0,
        max_digits=15,
        decimal_places=2,
        widget=forms.TextInput(attrs={"class": "js-money-input", "inputmode": "decimal"}),
    )
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(),
    )
    advance_percent = forms.DecimalField(
        label="Размер предоплаты в процентах",
        required=False,
        initial=40,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": 0, "max": 100, "step": "1"}),
    )
    advance_term_days = forms.IntegerField(
        label="Срок предоплаты в календарных днях",
        required=False,
        initial=10,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1}),
    )
    preliminary_report_percent = forms.DecimalField(
        label="Размер оплаты Предварительного отчёта в процентах",
        required=False,
        initial=40,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": 0, "max": 100, "step": "1"}),
    )
    preliminary_report_term_days = forms.IntegerField(
        label="Срок оплаты Предварительного отчёта в календарных днях",
        required=False,
        initial=7,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1}),
    )
    final_report_percent = forms.DecimalField(
        label="Размер оплаты Итогового отчёта в процентах",
        required=False,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "min": 0,
                "max": 100,
                "step": "0.01",
                "readonly": True,
                "tabindex": "-1",
                "class": "readonly-field",
            }
        ),
    )
    final_report_term_days = forms.IntegerField(
        label="Срок оплаты Итогового отчёта в календарных днях",
        required=False,
        initial=15,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1}),
    )
    type_ids = forms.CharField(required=False, widget=forms.HiddenInput())
    assets_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-assets-payload"}),
    )
    legal_entities_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-legal-entities-payload"}),
    )
    objects_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-objects-payload"}),
    )
    commercial_offer_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-commercial-offer-payload"}),
    )
    commercial_totals_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-commercial-totals-payload"}),
    )
    summary_commercial_offer_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-summary-commercial-offer-payload"}),
    )
    summary_commercial_totals_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-summary-commercial-totals-payload"}),
    )
    service_sections_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-service-sections-payload"}),
    )
    service_sections_editor_state = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-service-sections-editor-state"}),
    )
    service_customer_tz_editor_state = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-service-customer-tz-editor-state"}),
    )
    service_composition_customer_tz = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "proposal-service-composition-customer-tz"}),
    )
    service_composition_mode = forms.ChoiceField(
        required=False,
        choices=[
            ("sections", "Разделы"),
            ("customer_tz", "ТЗ Заказчика"),
        ],
        widget=forms.HiddenInput(attrs={"id": "proposal-service-composition-mode"}),
    )

    _decimal_text_fields = (
        "service_term_months",
        "final_report_term_weeks",
        "service_cost",
        "advance_percent",
        "preliminary_report_percent",
        "final_report_percent",
    )
    _asset_date_formats = DATE_INPUT_FORMATS

    class Meta:
        model = ProposalRegistration
        fields = [
            "number",
            "group_member",
            "type",
            "name",
            "kind",
            "status",
            "year",
            "customer",
            "country",
            "registration_region",
            "identifier",
            "registration_number",
            "registration_date",
            "asset_owner",
            "asset_owner_country",
            "asset_owner_region",
            "asset_owner_identifier",
            "asset_owner_registration_number",
            "asset_owner_registration_date",
            "asset_owner_matches_customer",
            "proposal_project_name",
            "purpose",
            "service_composition",
            "service_composition_customer_tz",
            "service_composition_mode",
            "evaluation_date",
            "service_term_months",
            "preliminary_report_date",
            "final_report_term_weeks",
            "final_report_date",
            "report_languages",
            "service_cost",
            "currency",
            "advance_percent",
            "advance_term_days",
            "preliminary_report_percent",
            "preliminary_report_term_days",
            "final_report_percent",
            "final_report_term_days",
        ]
        widgets = {
            "year": forms.NumberInput(attrs={"placeholder": "ГГГГ"}),
            "name": forms.TextInput(attrs={"placeholder": "Краткое название компании или месторождения"}),
            "customer": forms.TextInput(attrs={"placeholder": "Искать по наименованию и регистрационному номеру"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        getlist = self.data.getlist if hasattr(self.data, "getlist") else lambda key: []
        if self.data:
            data = self.data.copy()
            for field_name in self._decimal_text_fields:
                if hasattr(data, "getlist"):
                    values = data.getlist(field_name)
                    if values:
                        data.setlist(
                            field_name,
                            [str(value or "").replace("\u00a0", "").replace(" ", "").replace(",", ".") for value in values],
                        )
                else:
                    value = data.get(field_name, "")
                    if isinstance(value, (list, tuple)):
                        data[field_name] = [
                            str(item or "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
                            for item in value
                        ]
                    elif value:
                        data[field_name] = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            self.data = data
        for field in self.fields.values():
            _apply_russian_error_messages(field)
        self.fields["group_member"].queryset = _group_choices()
        self.fields["group_member"].label_from_instance = lambda obj: obj.group_display_label
        self.fields["group_member"].empty_label = "— Не выбрано —"
        self.fields["status"].widget.disabled_values = {str(value) for value in NON_EDITABLE_PROPOSAL_STATUSES}
        if not (self.instance and self.instance.pk) and not self.is_bound:
            self.fields["status"].initial = ProposalRegistration.ProposalStatus.FINAL
            self.fields["evaluation_date"].initial = _default_proposal_evaluation_date()
        self.fields["type"].queryset = Product.objects.order_by("position", "id")
        self.fields["type"].label_from_instance = lambda obj: obj.short_name
        self.fields["type"].required = False
        self.fields["type"].empty_label = "— Не выбрано —"
        self.fields["name"].required = True
        self.fields["year"].required = not bool(self.instance and self.instance.pk)
        self.fields["year"].error_messages["required"] = "Укажите год."

        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and (self.instance.country_id or self.instance.asset_owner_country_id):
            country_ids = [value for value in [self.instance.country_id, self.instance.asset_owner_country_id] if value]
            country_qs = (country_qs | OKSMCountry.objects.filter(pk__in=country_ids)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["asset_owner_country"].queryset = country_qs
        self.fields["asset_owner_country"].label_from_instance = lambda obj: obj.short_name

        customer_country_id = self.data.get("country") if self.is_bound else getattr(self.instance, "country_id", None)
        customer_region = self.data.get("registration_region") if self.is_bound else getattr(self.instance, "registration_region", "")
        customer_registration_date = (
            _parse_proposal_form_date(self.data.get("registration_date"))
            if self.is_bound
            else getattr(self.instance, "registration_date", None)
        )
        customer_region_choices = [("", "---------")]
        customer_region_choices.extend(
            (name, name)
            for name in _proposal_region_choices_for_country(
                customer_country_id,
                current_value=customer_region,
                as_of=customer_registration_date,
            )
        )
        self.fields["registration_region"].choices = customer_region_choices

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
            _parse_proposal_form_date(self.data.get("asset_owner_registration_date"))
            if self.is_bound
            else getattr(self.instance, "asset_owner_registration_date", None)
        )
        asset_owner_region_choices = [("", "---------")]
        asset_owner_region_choices.extend(
            (name, name)
            for name in _proposal_region_choices_for_country(
                asset_owner_country_id,
                current_value=asset_owner_region,
                as_of=asset_owner_registration_date,
            )
        )
        self.fields["asset_owner_region"].choices = asset_owner_region_choices

        currency_qs = OKVCurrency.objects.filter(
            models.Q(approval_date__isnull=True) | models.Q(approval_date__lte=today),
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)).distinct().order_by(
                "code_alpha"
            )
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        self.fields["final_report_percent"].disabled = True
        self.fields["final_report_percent"].widget.attrs["readonly"] = True
        self.fields["final_report_percent"].widget.attrs["tabindex"] = "-1"
        selected_report_languages = normalize_proposal_report_languages(
            getlist("report_language_choices")
            or self.data.get("report_languages")
            or self.initial.get("report_languages", getattr(self.instance, "report_languages", ""))
        )
        self.selected_report_languages = selected_report_languages
        if not self.data:
            self.initial["report_languages"] = ", ".join(selected_report_languages)

        if self.instance and self.instance.pk and self.instance.identifier:
            self.fields["identifier"].initial = self.instance.identifier

        self._bootstrapify()
        self.fields["asset_owner_matches_customer"].widget.attrs["class"] = "form-check-input"

        if self.instance and self.instance.pk and "assets_payload" not in self.data:
            self.fields["assets_payload"].initial = json.dumps(
                [
                    {
                        "short_name": asset.short_name or "",
                        "country_id": asset.country_id or "",
                        "country_name": asset.country.short_name if asset.country_id else "",
                        "identifier": asset.identifier or "",
                        "registration_number": asset.registration_number or "",
                        "registration_date": asset.registration_date.strftime("%d.%m.%Y") if asset.registration_date else "",
                    }
                    for asset in self.instance.assets.select_related("country").all()
                ],
                ensure_ascii=False,
            )
        elif not self.instance.pk and "assets_payload" not in self.data:
            self.fields["assets_payload"].initial = json.dumps(
                [
                    {
                        "short_name": "",
                        "country_id": "",
                        "country_name": "",
                        "identifier": "",
                        "registration_number": "",
                        "registration_date": "",
                    }
                ],
                ensure_ascii=False,
            )

        if self.instance and self.instance.pk and "legal_entities_payload" not in self.data:
            self.fields["legal_entities_payload"].initial = json.dumps(
                [
                    {
                        "asset_short_name": legal_entity.asset_short_name or "",
                        "short_name": legal_entity.short_name or "",
                        "country_id": legal_entity.country_id or "",
                        "country_name": legal_entity.country.short_name if legal_entity.country_id else "",
                        "identifier": legal_entity.identifier or "",
                        "registration_number": legal_entity.registration_number or "",
                        "registration_date": (
                            legal_entity.registration_date.strftime("%d.%m.%Y")
                            if legal_entity.registration_date
                            else ""
                        ),
                    }
                    for legal_entity in self.instance.legal_entities.select_related("country").all()
                ],
                ensure_ascii=False,
            )
        elif not self.instance.pk and "legal_entities_payload" not in self.data:
            self.fields["legal_entities_payload"].initial = "[]"

        if self.instance and self.instance.pk and "objects_payload" not in self.data:
            self.fields["objects_payload"].initial = json.dumps(
                [
                    {
                        "legal_entity_short_name": obj.legal_entity_short_name or "",
                        "short_name": obj.short_name or "",
                        "region": obj.region or "",
                        "object_type": obj.object_type or "",
                        "license": obj.license or "",
                        "registration_date": obj.registration_date.strftime("%d.%m.%Y") if obj.registration_date else "",
                    }
                    for obj in self.instance.proposal_objects.all()
                ],
                ensure_ascii=False,
            )
        elif not self.instance.pk and "objects_payload" not in self.data:
            self.fields["objects_payload"].initial = "[]"

        if self.instance and self.instance.pk and "commercial_offer_payload" not in self.data:
            self.fields["commercial_offer_payload"].initial = json.dumps(
                [
                    {
                        "specialist": item.specialist or "",
                        "job_title": item.job_title or "",
                        "professional_status": item.professional_status or "",
                        "service_name": item.service_name or "",
                        "rate_eur_per_day": str(item.rate_eur_per_day or ""),
                        "asset_day_counts": list(item.asset_day_counts or []),
                        "total_eur_without_vat": str(item.total_eur_without_vat or ""),
                    }
                    for item in self.instance.commercial_offers.all()
                ],
                ensure_ascii=False,
            )
        elif not self.instance.pk and "commercial_offer_payload" not in self.data:
            self.fields["commercial_offer_payload"].initial = "[]"
        if self.instance and self.instance.pk and "commercial_totals_payload" not in self.data:
            totals_payload = {
                "discount_percent": "5",
                "rub_total_service_text": "Курс евро Банка России на текущую дату:",
                "discounted_total_service_text": "Размер скидки:",
                **dict(self.instance.commercial_totals_json or {}),
            }
            self.fields["commercial_totals_payload"].initial = json.dumps(
                totals_payload,
                ensure_ascii=False,
            )
        elif "commercial_totals_payload" not in self.data:
            totals_payload = {
                "discount_percent": "5",
                "rub_total_service_text": get_cbr_eur_rate_text(),
                "discounted_total_service_text": "Размер скидки:",
                "travel_expenses_mode": PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL,
            }
            eur_rate = get_cbr_eur_rate_for_today()
            if eur_rate is not None:
                totals_payload["exchange_rate"] = format(eur_rate.quantize(Decimal("0.0001")), "f")
            self.fields["commercial_totals_payload"].initial = json.dumps(
                totals_payload,
                ensure_ascii=False,
            )
        if self.instance and self.instance.pk and "summary_commercial_offer_payload" not in self.data:
            self.fields["summary_commercial_offer_payload"].initial = json.dumps(
                self._serialize_instance_commercial_rows(),
                ensure_ascii=False,
            )
        elif "summary_commercial_offer_payload" not in self.data:
            self.fields["summary_commercial_offer_payload"].initial = "[]"
        if self.instance and self.instance.pk and "summary_commercial_totals_payload" not in self.data:
            summary_totals_payload = {
                "discount_percent": "5",
                "rub_total_service_text": "Курс евро Банка России на текущую дату:",
                "discounted_total_service_text": "Размер скидки:",
                **dict(self.instance.commercial_totals_json or {}),
            }
            self.fields["summary_commercial_totals_payload"].initial = json.dumps(
                self._merge_stage_commercial_totals_payload(summary_totals_payload),
                ensure_ascii=False,
            )
        elif "summary_commercial_totals_payload" not in self.data:
            self.fields["summary_commercial_totals_payload"].initial = json.dumps(
                self._merge_stage_commercial_totals_payload({}),
                ensure_ascii=False,
            )
        if self.instance and self.instance.pk and "service_sections_payload" not in self.data:
            self.fields["service_sections_payload"].initial = json.dumps(
                [
                    {
                        "service_name": item.get("service_name", ""),
                        "code": item.get("code", ""),
                    }
                    for item in (self.instance.service_sections_json or [])
                ],
                ensure_ascii=False,
            )
        elif not self.instance.pk and "service_sections_payload" not in self.data:
            self.fields["service_sections_payload"].initial = "[]"
        if self.instance and self.instance.pk and "service_sections_editor_state" not in self.data:
            self.fields["service_sections_editor_state"].initial = json.dumps(
                self.instance.service_sections_editor_state or [],
                ensure_ascii=False,
            )
        elif "service_sections_editor_state" not in self.data:
            self.fields["service_sections_editor_state"].initial = "[]"
        if self.instance and self.instance.pk and "service_customer_tz_editor_state" not in self.data:
            self.fields["service_customer_tz_editor_state"].initial = json.dumps(
                self.instance.service_customer_tz_editor_state or {},
                ensure_ascii=False,
            )
        elif "service_customer_tz_editor_state" not in self.data:
            self.fields["service_customer_tz_editor_state"].initial = ""
        if self.instance and self.instance.pk and "service_composition_mode" not in self.data:
            self.fields["service_composition_mode"].initial = self.instance.service_composition_mode or "sections"
        elif "service_composition_mode" not in self.data:
            self.fields["service_composition_mode"].initial = "sections"

        if not self.instance.pk and "group_member" not in self.data:
            self.fields["group_member"].initial = (
                GroupMember.objects.filter(country_alpha2="RU").order_by("position", "id").values_list("pk", flat=True).first()
            )
        if not self.instance.pk and "country" not in self.data:
            russia = country_qs.filter(short_name="Россия").first()
            if russia:
                self.fields["country"].initial = russia.pk
                identifier = LegalEntityIdentifier.objects.filter(country=russia).values_list("identifier", flat=True).first()
                if identifier:
                    self.fields["identifier"].initial = identifier
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year
        if not self.instance.pk and "number" not in self.data:
            self.fields["number"].initial = _next_proposal_number()
        if not self.instance.pk and "currency" not in self.data:
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.fields["currency"].initial = rub.pk
        if not self.instance.pk and "asset_owner_matches_customer" not in self.data:
            self.fields["asset_owner_matches_customer"].initial = True
        try:
            self.initial["final_report_percent"] = self._calculate_final_report_percent(
                advance_percent=(
                    self.data.get("advance_percent")
                    if self.is_bound
                    else self.initial.get("advance_percent", self.instance.advance_percent)
                ),
                preliminary_report_percent=(
                    self.data.get("preliminary_report_percent")
                    if self.is_bound
                    else self.initial.get("preliminary_report_percent", self.instance.preliminary_report_percent)
                ),
            )
        except forms.ValidationError:
            self.initial["final_report_percent"] = self.initial.get(
                "final_report_percent",
                self.instance.final_report_percent,
            )
        self.stage_rows = self._build_stage_rows()
        self.summary_commercial_row = self._build_summary_commercial_row()

    def _default_stage_commercial_totals_payload(self):
        payload = {
            "discount_percent": "5",
            "rub_total_service_text": get_cbr_eur_rate_text(),
            "discounted_total_service_text": "Размер скидки:",
            "travel_expenses_mode": PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL,
        }
        eur_rate = get_cbr_eur_rate_for_today()
        if eur_rate is not None:
            payload["exchange_rate"] = format(eur_rate.quantize(Decimal("0.0001")), "f")
        return payload

    def _merge_stage_commercial_totals_payload(self, payload):
        return {
            **self._default_stage_commercial_totals_payload(),
            **(payload or {}),
        }

    def _serialize_instance_commercial_rows(self):
        if not self.instance or not self.instance.pk:
            return []
        return [
            {
                "specialist": item.specialist or "",
                "job_title": item.job_title or "",
                "professional_status": item.professional_status or "",
                "service_name": item.service_name or "",
                "rate_eur_per_day": str(item.rate_eur_per_day or ""),
                "asset_day_counts": list(item.asset_day_counts or []),
                "total_eur_without_vat": str(item.total_eur_without_vat or ""),
            }
            for item in self.instance.commercial_offers.all()
        ]

    def _build_summary_commercial_row(self):
        offer_payload = ""
        totals_payload = ""
        if self.is_bound:
            offer_payload = str(self.data.get("summary_commercial_offer_payload") or "").strip()
            totals_payload = str(self.data.get("summary_commercial_totals_payload") or "").strip()
        if not offer_payload:
            offer_payload = str(self.fields["summary_commercial_offer_payload"].initial or "[]")
        if not totals_payload:
            totals_payload = str(
                self.fields["summary_commercial_totals_payload"].initial
                or json.dumps(self._merge_stage_commercial_totals_payload({}), ensure_ascii=False)
            )
        return {
            "commercial_offer_payload": offer_payload or "[]",
            "commercial_totals_payload": totals_payload,
        }

    def _empty_stage_row(self, rank=1):
        return {
            "rank": rank,
            "consulting_type": "",
            "service_category": "",
            "service_subtype": "",
            "product_id": "",
            "product_short_label": "",
            "service_sections_payload": "[]",
            "service_sections_editor_state": "[]",
            "service_customer_tz_editor_state": "",
            "service_composition_customer_tz": "",
            "service_composition_mode": "sections",
            "service_composition": "",
            "commercial_offer_payload": "[]",
            "commercial_totals_payload": json.dumps(
                self._merge_stage_commercial_totals_payload({}),
                ensure_ascii=False,
            ),
            "evaluation_date": _format_stage_date(self.fields["evaluation_date"].initial),
            "service_term_months": "",
            "preliminary_report_date": "",
            "final_report_term_weeks": "",
            "final_report_date": "",
        }

    def _build_stage_rows_from_bound_data(self):
        field_names = (
            "type_consulting",
            "type_service_category",
            "type_service_subtype",
            "type",
            "service_sections_payload",
            "service_sections_editor_state",
            "service_customer_tz_editor_state",
            "service_composition_customer_tz",
            "service_composition_mode",
            "service_composition",
            "commercial_offer_payload",
            "commercial_totals_payload",
            "evaluation_date",
            "service_term_months",
            "preliminary_report_date",
            "final_report_term_weeks",
            "final_report_date",
        )
        rows_map = {name: _proposal_request_list(self.data, name) for name in field_names}
        product_ids = {
            int(raw)
            for raw in rows_map["type"]
            if str(raw or "").strip().isdigit()
        }
        product_map = {
            str(product.pk): product
            for product in Product.objects.filter(pk__in=product_ids)
        }
        row_count = max([len(values) for values in rows_map.values()] or [0], default=0)
        row_count = max(row_count, 1)
        rows = []
        for index in range(row_count):
            product_id = (rows_map["type"][index] if index < len(rows_map["type"]) else "").strip()
            product = product_map.get(product_id)
            row = {
                "rank": len(rows) + 1,
                "consulting_type": (rows_map["type_consulting"][index] if index < len(rows_map["type_consulting"]) else "").strip(),
                "service_category": (
                    rows_map["type_service_category"][index] if index < len(rows_map["type_service_category"]) else ""
                ).strip(),
                "service_subtype": (
                    rows_map["type_service_subtype"][index] if index < len(rows_map["type_service_subtype"]) else ""
                ).strip(),
                "product_id": product_id,
                "product_short_label": (getattr(product, "short_name", "") or "").strip(),
                "service_sections_payload": (
                    rows_map["service_sections_payload"][index] if index < len(rows_map["service_sections_payload"]) else "[]"
                ),
                "service_sections_editor_state": (
                    rows_map["service_sections_editor_state"][index]
                    if index < len(rows_map["service_sections_editor_state"])
                    else "[]"
                ),
                "service_customer_tz_editor_state": (
                    rows_map["service_customer_tz_editor_state"][index]
                    if index < len(rows_map["service_customer_tz_editor_state"])
                    else ""
                ),
                "service_composition_customer_tz": (
                    rows_map["service_composition_customer_tz"][index]
                    if index < len(rows_map["service_composition_customer_tz"])
                    else ""
                ),
                "service_composition_mode": (
                    rows_map["service_composition_mode"][index]
                    if index < len(rows_map["service_composition_mode"])
                    else "sections"
                ).strip()
                or "sections",
                "service_composition": (
                    rows_map["service_composition"][index] if index < len(rows_map["service_composition"]) else ""
                ),
                "commercial_offer_payload": (
                    rows_map["commercial_offer_payload"][index]
                    if index < len(rows_map["commercial_offer_payload"])
                    else "[]"
                ),
                "commercial_totals_payload": (
                    rows_map["commercial_totals_payload"][index]
                    if index < len(rows_map["commercial_totals_payload"])
                    else json.dumps(self._merge_stage_commercial_totals_payload({}), ensure_ascii=False)
                ),
                "evaluation_date": (
                    rows_map["evaluation_date"][index] if index < len(rows_map["evaluation_date"]) else ""
                ).strip(),
                "service_term_months": (
                    rows_map["service_term_months"][index] if index < len(rows_map["service_term_months"]) else ""
                ).strip(),
                "preliminary_report_date": (
                    rows_map["preliminary_report_date"][index]
                    if index < len(rows_map["preliminary_report_date"])
                    else ""
                ).strip(),
                "final_report_term_weeks": (
                    rows_map["final_report_term_weeks"][index]
                    if index < len(rows_map["final_report_term_weeks"])
                    else ""
                ).strip(),
                "final_report_date": (
                    rows_map["final_report_date"][index] if index < len(rows_map["final_report_date"]) else ""
                ).strip(),
            }
            has_data = any(
                row[key]
                for key in (
                    "consulting_type",
                    "service_category",
                    "service_subtype",
                    "product_id",
                    "service_composition",
                    "service_composition_customer_tz",
                    "evaluation_date",
                    "service_term_months",
                    "preliminary_report_date",
                    "final_report_term_weeks",
                    "final_report_date",
                )
            )
            if has_data or row_count == 1:
                rows.append(row)
        return rows or [self._empty_stage_row()]

    def _build_stage_rows_from_instance(self):
        instance = self.instance
        if not instance or not instance.pk:
            return [self._empty_stage_row()]

        ordered_products = list(instance.ordered_products())
        product_map = {str(product.pk): product for product in ordered_products if getattr(product, "pk", None)}
        stored_stages = list(instance.stage_payloads_json or [])
        if stored_stages:
            normalized_rows = []
            for index, payload in enumerate(stored_stages, start=1):
                payload = payload if isinstance(payload, dict) else {}
                product_id = str(payload.get("product_id") or "")
                product = product_map.get(product_id)
                normalized_rows.append(
                    {
                        "rank": index,
                        "consulting_type": (getattr(product, "consulting_type_display", "") or "").strip(),
                        "service_category": (getattr(product, "service_category_display", "") or "").strip(),
                        "service_subtype": (getattr(product, "service_subtype_display", "") or "").strip(),
                        "product_id": product_id,
                        "product_short_label": (getattr(product, "short_name", "") or "").strip(),
                        "service_sections_payload": json.dumps(payload.get("service_sections_json") or [], ensure_ascii=False),
                        "service_sections_editor_state": json.dumps(
                            payload.get("service_sections_editor_state") or [],
                            ensure_ascii=False,
                        ),
                        "service_customer_tz_editor_state": json.dumps(
                            payload.get("service_customer_tz_editor_state") or {},
                            ensure_ascii=False,
                        )
                        if payload.get("service_customer_tz_editor_state")
                        else "",
                        "service_composition_customer_tz": str(payload.get("service_composition_customer_tz") or ""),
                        "service_composition_mode": str(payload.get("service_composition_mode") or "sections") or "sections",
                        "service_composition": str(payload.get("service_composition") or ""),
                        "commercial_offer_payload": json.dumps(
                            payload.get("commercial_offer_payload") or [],
                            ensure_ascii=False,
                        ),
                        "commercial_totals_payload": json.dumps(
                            self._merge_stage_commercial_totals_payload(payload.get("commercial_totals_json") or {}),
                            ensure_ascii=False,
                        ),
                        "evaluation_date": str(payload.get("evaluation_date") or ""),
                        "service_term_months": str(payload.get("service_term_months") or ""),
                        "preliminary_report_date": str(payload.get("preliminary_report_date") or ""),
                        "final_report_term_weeks": str(payload.get("final_report_term_weeks") or ""),
                        "final_report_date": str(payload.get("final_report_date") or ""),
                    }
                )
            if normalized_rows:
                return normalized_rows

        product = ordered_products[-1] if ordered_products else getattr(instance, "type", None)
        commercial_rows = self._serialize_instance_commercial_rows()
        return [
            {
                "rank": 1,
                "consulting_type": (getattr(product, "consulting_type_display", "") or "").strip(),
                "service_category": (getattr(product, "service_category_display", "") or "").strip(),
                "service_subtype": (getattr(product, "service_subtype_display", "") or "").strip(),
                "product_id": str(getattr(product, "pk", "") or ""),
                "product_short_label": (getattr(product, "short_name", "") or "").strip(),
                "service_sections_payload": json.dumps(instance.service_sections_json or [], ensure_ascii=False),
                "service_sections_editor_state": json.dumps(instance.service_sections_editor_state or [], ensure_ascii=False),
                "service_customer_tz_editor_state": json.dumps(
                    instance.service_customer_tz_editor_state or {},
                    ensure_ascii=False,
                )
                if instance.service_customer_tz_editor_state
                else "",
                "service_composition_customer_tz": instance.service_composition_customer_tz or "",
                "service_composition_mode": instance.service_composition_mode or "sections",
                "service_composition": instance.service_composition or "",
                "commercial_offer_payload": json.dumps(commercial_rows, ensure_ascii=False),
                "commercial_totals_payload": json.dumps(
                    self._merge_stage_commercial_totals_payload(instance.commercial_totals_json or {}),
                    ensure_ascii=False,
                ),
                "evaluation_date": _format_stage_date(instance.evaluation_date),
                "service_term_months": str(instance.service_term_months or ""),
                "preliminary_report_date": _format_stage_date(instance.preliminary_report_date),
                "final_report_term_weeks": str(instance.final_report_term_weeks or ""),
                "final_report_date": _format_stage_date(instance.final_report_date),
            }
        ]

    def _build_stage_rows(self):
        if self.is_bound:
            return self._build_stage_rows_from_bound_data()
        rows = self._build_stage_rows_from_instance()
        return rows or [self._empty_stage_row()]

    def clean_group_member(self):
        member = self.cleaned_data.get("group_member")
        if member and not (member.country_alpha2 or "").strip():
            raise forms.ValidationError("Для выбранной строки состава группы не заполнен код Альфа-2.")
        return member

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status in NON_EDITABLE_PROPOSAL_STATUSES:
            current_status = str(getattr(self.instance, "status", "") or "")
            if self.instance.pk and status == current_status:
                return status
            raise forms.ValidationError("Выберите корректное значение.")
        return status

    def _calculate_final_report_percent(self, *, advance_percent, preliminary_report_percent):
        advance = self._parse_payload_decimal(
            advance_percent,
            "Размер предоплаты в процентах должен быть корректным числом.",
        ) or Decimal("0")
        preliminary = self._parse_payload_decimal(
            preliminary_report_percent,
            "Размер оплаты Предварительного отчёта в процентах должен быть корректным числом.",
        ) or Decimal("0")
        result = Decimal("100") - advance - preliminary
        return result.quantize(Decimal("0.01"))

    def _parse_stage_date(self, value, *, row_index, field_label):
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = _parse_proposal_form_date(raw)
        if parsed is None:
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")
        return parsed

    def _parse_stage_decimal(self, value, *, row_index, field_label):
        raw = str(value or "").strip()
        if not raw:
            return None
        return self._parse_payload_decimal(raw, f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")

    def _load_stage_json(self, raw, *, row_index, field_label, expected_type, default):
        raw = str(raw or "").strip()
        if not raw:
            return default
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» передано в некорректном формате.")
        if not isinstance(value, expected_type):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» передано в некорректном формате.")
        return value

    def _normalize_stage_service_sections(self, raw, *, row_index, product=None):
        items = self._load_stage_json(
            raw,
            row_index=row_index,
            field_label="Состав услуг / техническое задание",
            expected_type=list,
            default=[],
        )
        sections_by_name = {}
        if product is not None:
            for section in TypicalSection.objects.filter(product=product).order_by("position", "id"):
                name_ru = (section.name_ru or "").strip()
                if name_ru and name_ru not in sections_by_name:
                    sections_by_name[name_ru] = (section.code or "").strip()
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            service_name = str(item.get("service_name") or "").strip()
            code = str(item.get("code") or "").strip()
            if not service_name and not code:
                continue
            normalized.append(
                {
                    "service_name": service_name,
                    "code": sections_by_name.get(service_name, "") or code,
                }
            )
        return normalized

    def _normalize_stage_editor_state(self, raw, *, row_index):
        items = self._load_stage_json(
            raw,
            row_index=row_index,
            field_label="Состояние редактора состава услуг",
            expected_type=list,
            default=[],
        )
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "code": str(item.get("code") or "").strip(),
                    "service_name": str(item.get("service_name") or "").strip(),
                    "html": str(item.get("html") or "").strip(),
                    "plain_text": str(item.get("plain_text") or "").strip(),
                }
            )
        return normalized

    def _normalize_stage_customer_tz_state(self, raw, *, row_index):
        value = self._load_stage_json(
            raw,
            row_index=row_index,
            field_label="Состояние редактора ТЗ Заказчика",
            expected_type=dict,
            default={},
        )
        return {
            "html": str(value.get("html") or "").strip(),
            "plain_text": str(value.get("plain_text") or "").strip(),
        }

    def _load_summary_json(self, raw, *, field_label, expected_type, default):
        raw = str(raw or "").strip()
        if not raw:
            return default
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError(f"Сводный блок: поле «{field_label}» передано в некорректном формате.")
        if not isinstance(value, expected_type):
            raise forms.ValidationError(f"Сводный блок: поле «{field_label}» передано в некорректном формате.")
        return value

    def _normalize_stage_commercial_rows(self, raw, *, row_index, totals_raw=""):
        items = self._load_stage_json(
            raw,
            row_index=row_index,
            field_label="Коммерческое предложение",
            expected_type=list,
            default=[],
        )
        travel_expenses_mode = self._normalize_stage_commercial_totals(
            totals_raw,
            row_index=row_index,
        ).get("travel_expenses_mode")
        normalized = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            specialist = str(item.get("specialist") or "").strip()
            job_title = str(item.get("job_title") or "").strip()
            professional_status = str(item.get("professional_status") or "").strip()
            service_name = str(item.get("service_name") or "").strip()
            rate_raw = str(item.get("rate_eur_per_day") or "").strip()
            total_raw = str(item.get("total_eur_without_vat") or "").strip()
            asset_day_counts = item.get("asset_day_counts") or []
            if not isinstance(asset_day_counts, list):
                asset_day_counts = []
            is_travel_expenses_row = is_proposal_travel_expenses_name(service_name)
            cleaned_day_counts = []
            if is_travel_expenses_row and travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                for day_idx, raw_value in enumerate(asset_day_counts, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        cleaned_day_counts.append("")
                        continue
                    parsed_amount = self._parse_payload_decimal(
                        value,
                        f"Этап {row_index}: значение по активу #{day_idx} заполнено некорректно.",
                    )
                    if parsed_amount is not None and parsed_amount < 0:
                        raise forms.ValidationError(
                            f"Этап {row_index}: значение по активу #{day_idx} не может быть отрицательным."
                        )
                    cleaned_day_counts.append(self._serialize_payload_decimal(parsed_amount))
            else:
                for day_idx, raw_value in enumerate(asset_day_counts, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        cleaned_day_counts.append("")
                        continue
                    try:
                        parsed_int = int(value)
                    except (TypeError, ValueError):
                        raise forms.ValidationError(
                            f"Этап {row_index}: значение дня #{day_idx} заполнено некорректно."
                        )
                    if parsed_int < 0:
                        raise forms.ValidationError(
                            f"Этап {row_index}: значение дня #{day_idx} не может быть отрицательным."
                        )
                    cleaned_day_counts.append(parsed_int)
            row_has_data = any(
                [
                    specialist,
                    job_title,
                    professional_status,
                    service_name,
                    rate_raw,
                    total_raw,
                    any(value != "" for value in cleaned_day_counts),
                ]
            )
            if not row_has_data:
                continue
            rate_value = self._parse_payload_decimal(
                rate_raw,
                f"Этап {row_index}: поле «Ставка, евро / день» заполнено некорректно.",
            )
            total_value = self._parse_payload_decimal(
                total_raw,
                f"Этап {row_index}: поле «Итого, евро без НДС» заполнено некорректно.",
            )
            if is_travel_expenses_row:
                rate_value = None
                if travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                    total_value = sum(
                        (
                            Decimal(str(value))
                            for value in cleaned_day_counts
                            if value not in (None, "")
                        ),
                        Decimal("0"),
                    )
                else:
                    cleaned_day_counts = ["" for _ in cleaned_day_counts]
            normalized.append(
                {
                    "position": index,
                    "specialist": specialist,
                    "job_title": job_title,
                    "professional_status": professional_status,
                    "service_name": service_name,
                    "rate_eur_per_day": rate_value,
                    "asset_day_counts": cleaned_day_counts,
                    "total_eur_without_vat": total_value,
                }
            )
        return normalized

    def _normalize_stage_commercial_totals(self, raw, *, row_index):
        value = self._load_stage_json(
            raw,
            row_index=row_index,
            field_label="Итоги коммерческого предложения",
            expected_type=dict,
            default={},
        )
        return self._merge_stage_commercial_totals_payload(
            {
                "exchange_rate": str(value.get("exchange_rate") or "").strip(),
                "discount_percent": str(value.get("discount_percent") or "").strip(),
                "contract_total": str(value.get("contract_total") or "").strip(),
                "contract_total_auto": str(value.get("contract_total_auto") or "").strip(),
                "rub_total_service_text": str(value.get("rub_total_service_text") or "").strip(),
                "discounted_total_service_text": str(value.get("discounted_total_service_text") or "").strip(),
                "travel_expenses_mode": str(value.get("travel_expenses_mode") or "").strip()
                or PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL,
            }
        )

    def _normalize_summary_commercial_rows(self, raw, *, totals_raw=""):
        items = self._load_summary_json(
            raw,
            field_label="Коммерческое предложение",
            expected_type=list,
            default=[],
        )
        travel_expenses_mode = self._normalize_summary_commercial_totals(
            totals_raw,
        ).get("travel_expenses_mode")
        normalized = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            specialist = str(item.get("specialist") or "").strip()
            job_title = str(item.get("job_title") or "").strip()
            professional_status = str(item.get("professional_status") or "").strip()
            service_name = str(item.get("service_name") or "").strip()
            rate_raw = str(item.get("rate_eur_per_day") or "").strip()
            total_raw = str(item.get("total_eur_without_vat") or "").strip()
            asset_day_counts = item.get("asset_day_counts") or []
            if not isinstance(asset_day_counts, list):
                asset_day_counts = []
            is_travel_expenses_row = is_proposal_travel_expenses_name(service_name)
            cleaned_day_counts = []
            if is_travel_expenses_row and travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                for day_idx, raw_value in enumerate(asset_day_counts, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        cleaned_day_counts.append("")
                        continue
                    parsed_amount = self._parse_payload_decimal(
                        value,
                        f"Сводный блок: значение по подстолбцу #{day_idx} заполнено некорректно.",
                    )
                    if parsed_amount is not None and parsed_amount < 0:
                        raise forms.ValidationError(
                            f"Сводный блок: значение по подстолбцу #{day_idx} не может быть отрицательным."
                        )
                    cleaned_day_counts.append(self._serialize_payload_decimal(parsed_amount))
            else:
                for day_idx, raw_value in enumerate(asset_day_counts, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        cleaned_day_counts.append("")
                        continue
                    try:
                        parsed_int = int(value)
                    except (TypeError, ValueError):
                        raise forms.ValidationError(
                            f"Сводный блок: значение дня #{day_idx} заполнено некорректно."
                        )
                    if parsed_int < 0:
                        raise forms.ValidationError(
                            f"Сводный блок: значение дня #{day_idx} не может быть отрицательным."
                        )
                    cleaned_day_counts.append(parsed_int)
            row_has_data = any(
                [
                    specialist,
                    job_title,
                    professional_status,
                    service_name,
                    rate_raw,
                    total_raw,
                    any(value != "" for value in cleaned_day_counts),
                ]
            )
            if not row_has_data:
                continue
            rate_value = self._parse_payload_decimal(
                rate_raw,
                "Сводный блок: поле «Ставка, евро / день» заполнено некорректно.",
            )
            total_value = self._parse_payload_decimal(
                total_raw,
                "Сводный блок: поле «Итого, евро без НДС» заполнено некорректно.",
            )
            if is_travel_expenses_row:
                rate_value = None
                if travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                    total_value = sum(
                        (
                            Decimal(str(value))
                            for value in cleaned_day_counts
                            if value not in (None, "")
                        ),
                        Decimal("0"),
                    )
                else:
                    cleaned_day_counts = ["" for _ in cleaned_day_counts]
            normalized.append(
                {
                    "position": index,
                    "specialist": specialist,
                    "job_title": job_title,
                    "professional_status": professional_status,
                    "service_name": service_name,
                    "rate_eur_per_day": rate_value,
                    "asset_day_counts": cleaned_day_counts,
                    "total_eur_without_vat": total_value,
                }
            )
        return normalized

    def _normalize_summary_commercial_totals(self, raw):
        value = self._load_summary_json(
            raw,
            field_label="Итоги коммерческого предложения",
            expected_type=dict,
            default={},
        )
        return self._merge_stage_commercial_totals_payload(
            {
                "exchange_rate": str(value.get("exchange_rate") or "").strip(),
                "discount_percent": str(value.get("discount_percent") or "").strip(),
                "contract_total": str(value.get("contract_total") or "").strip(),
                "contract_total_auto": str(value.get("contract_total_auto") or "").strip(),
                "rub_total_service_text": str(value.get("rub_total_service_text") or "").strip(),
                "discounted_total_service_text": str(value.get("discounted_total_service_text") or "").strip(),
                "travel_expenses_mode": str(value.get("travel_expenses_mode") or "").strip()
                or PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL,
            }
        )

    def _build_summary_commercial_fallback(self, stage_payloads):
        asset_count = max(
            [len(item.get("asset_day_counts") or []) for stage in stage_payloads for item in stage["commercial_offer_payload"]],
            default=0,
        )
        asset_count = max(asset_count, 1)
        grouped_rows = {}
        travel_total = Decimal("0")
        travel_day_totals = [Decimal("0") for _ in range(asset_count)]
        has_travel_calculation = False
        has_travel_actual = False

        for stage in stage_payloads:
            travel_mode = (
                str((stage.get("commercial_totals_json") or {}).get("travel_expenses_mode") or "").strip()
                or PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
            )
            for item in stage["commercial_offer_payload"]:
                is_travel_row = is_proposal_travel_expenses_name(item.get("service_name") or "")
                day_values = list(item.get("asset_day_counts") or [])[:asset_count]
                while len(day_values) < asset_count:
                    day_values.append("")
                if is_travel_row:
                    total_value = item.get("total_eur_without_vat") or Decimal("0")
                    if not isinstance(total_value, Decimal):
                        total_value = self._parse_payload_decimal(
                            total_value,
                            "Сводный блок: поле «Итого, евро без НДС» заполнено некорректно.",
                        ) or Decimal("0")
                    travel_total += total_value
                    if travel_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                        has_travel_calculation = True
                        for index, raw_value in enumerate(day_values):
                            if raw_value in (None, ""):
                                continue
                            travel_day_totals[index] += Decimal(str(raw_value))
                    else:
                        has_travel_actual = True
                    continue

                key = (
                    str(item.get("specialist") or "").strip(),
                    str(item.get("job_title") or "").strip(),
                )
                bucket = grouped_rows.get(key)
                if bucket is None:
                    bucket = {
                        "position": len(grouped_rows) + 1,
                        "specialist": key[0],
                        "job_title": key[1],
                        "professional_status": str(item.get("professional_status") or "").strip(),
                        "service_name": "",
                        "rate_eur_per_day": item.get("rate_eur_per_day"),
                        "asset_day_counts": [0 for _ in range(asset_count)],
                        "total_eur_without_vat": Decimal("0"),
                    }
                    grouped_rows[key] = bucket
                for index, raw_value in enumerate(day_values):
                    if raw_value in (None, ""):
                        continue
                    bucket["asset_day_counts"][index] += int(raw_value)
                total_value = item.get("total_eur_without_vat") or Decimal("0")
                if not isinstance(total_value, Decimal):
                    total_value = self._parse_payload_decimal(
                        total_value,
                        "Сводный блок: поле «Итого, евро без НДС» заполнено некорректно.",
                    ) or Decimal("0")
                bucket["total_eur_without_vat"] += total_value

        summary_rows = []
        for bucket in grouped_rows.values():
            summary_rows.append(
                {
                    "position": bucket["position"],
                    "specialist": bucket["specialist"],
                    "job_title": bucket["job_title"],
                    "professional_status": bucket["professional_status"],
                    "service_name": "",
                    "rate_eur_per_day": bucket["rate_eur_per_day"],
                    "asset_day_counts": [value if value else "" for value in bucket["asset_day_counts"]],
                    "total_eur_without_vat": bucket["total_eur_without_vat"],
                }
            )

        travel_mode = (
            PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
            if has_travel_calculation and not has_travel_actual
            else PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL
        )
        if has_travel_calculation or has_travel_actual or travel_total > 0:
            summary_rows.append(
                {
                    "position": len(summary_rows) + 1,
                    "specialist": "",
                    "job_title": "",
                    "professional_status": "",
                    "service_name": PROPOSAL_TRAVEL_EXPENSES_LABEL,
                    "rate_eur_per_day": None,
                    "asset_day_counts": (
                        [self._serialize_payload_decimal(value) if value else "" for value in travel_day_totals]
                        if travel_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION
                        else ["" for _ in range(asset_count)]
                    ),
                    "total_eur_without_vat": travel_total,
                }
            )

        return summary_rows, travel_mode

    def _parse_summary_service_cost(self, totals):
        contract_total = str((totals or {}).get("contract_total") or "").strip()
        if not contract_total:
            return None
        return self._parse_payload_decimal(
            contract_total,
            "Сводный блок: поле «Стоимость услуг» заполнено некорректно.",
        )

    def _collect_stage_payloads(self):
        stage_payloads = []
        cleaned_product_ids = []
        seen_product_ids = set()
        for row in self.stage_rows:
            rank = int(row.get("rank") or len(stage_payloads) + 1)
            row_has_data = any(
                str(row.get(key) or "").strip()
                for key in (
                    "consulting_type",
                    "service_category",
                    "service_subtype",
                    "product_id",
                    "service_composition",
                    "service_composition_customer_tz",
                    "evaluation_date",
                    "service_term_months",
                    "preliminary_report_date",
                    "final_report_term_weeks",
                    "final_report_date",
                )
            )
            product_raw = str(row.get("product_id") or "").strip()
            if not product_raw:
                if row_has_data:
                    raise forms.ValidationError(f"Этап {rank}: выберите продукт.")
                continue
            try:
                product_id = int(product_raw)
            except (TypeError, ValueError):
                raise forms.ValidationError(f"Этап {rank}: выбран некорректный продукт.")
            product = Product.objects.filter(pk=product_id).first()
            if product is None:
                raise forms.ValidationError(f"Этап {rank}: выбранный продукт не найден.")
            if product_id in seen_product_ids:
                raise forms.ValidationError(f"Этап {rank}: продукт уже выбран для другого этапа.")
            seen_product_ids.add(product_id)
            cleaned_product_ids.append(product_id)

            service_composition_mode = str(row.get("service_composition_mode") or "sections").strip() or "sections"
            if service_composition_mode not in {"sections", "customer_tz"}:
                service_composition_mode = "sections"
            service_composition_customer_tz = str(row.get("service_composition_customer_tz") or "").strip()

            stage_payloads.append(
                {
                    "rank": rank,
                    "product": product,
                    "product_id": product_id,
                    "service_sections_json": self._normalize_stage_service_sections(
                        row.get("service_sections_payload"),
                        row_index=rank,
                        product=product,
                    ),
                    "service_sections_editor_state": self._normalize_stage_editor_state(
                        row.get("service_sections_editor_state"),
                        row_index=rank,
                    ),
                    "service_customer_tz_editor_state": self._normalize_stage_customer_tz_state(
                        row.get("service_customer_tz_editor_state"),
                        row_index=rank,
                    ),
                    "service_composition_customer_tz": service_composition_customer_tz,
                    "service_composition_mode": service_composition_mode,
                    "service_composition": (
                        service_composition_customer_tz
                        if service_composition_mode == "customer_tz"
                        else str(row.get("service_composition") or "").strip()
                    ),
                    "commercial_offer_payload": self._normalize_stage_commercial_rows(
                        row.get("commercial_offer_payload"),
                        row_index=rank,
                        totals_raw=row.get("commercial_totals_payload"),
                    ),
                    "commercial_totals_json": self._normalize_stage_commercial_totals(
                        row.get("commercial_totals_payload"),
                        row_index=rank,
                    ),
                    "evaluation_date": self._parse_stage_date(
                        row.get("evaluation_date"),
                        row_index=rank,
                        field_label="Дата оценки",
                    ),
                    "service_term_months": self._parse_stage_decimal(
                        row.get("service_term_months"),
                        row_index=rank,
                        field_label="Срок подготовки Предварительного отчёта, мес.",
                    ),
                    "preliminary_report_date": self._parse_stage_date(
                        row.get("preliminary_report_date"),
                        row_index=rank,
                        field_label="Дата Предварительного отчёта",
                    ),
                    "final_report_term_weeks": self._parse_stage_decimal(
                        row.get("final_report_term_weeks"),
                        row_index=rank,
                        field_label="Срок подготовки Итогового отчёта, нед.",
                    ),
                    "final_report_date": self._parse_stage_date(
                        row.get("final_report_date"),
                        row_index=rank,
                        field_label="Дата Итогового отчёта",
                    ),
                }
            )
        self.cleaned_type_ids = cleaned_product_ids
        self.cleaned_stage_payloads = stage_payloads
        if not cleaned_product_ids:
            self.add_error("type_ids", "Укажите хотя бы один продукт.")

    def clean(self):
        cleaned = super().clean()
        if self.errors.get("advance_percent") or self.errors.get("preliminary_report_percent"):
            final_percent = None
        else:
            try:
                final_percent = self._calculate_final_report_percent(
                    advance_percent=cleaned.get("advance_percent"),
                    preliminary_report_percent=cleaned.get("preliminary_report_percent"),
                )
            except forms.ValidationError:
                final_percent = None

        if final_percent is not None and (final_percent < 0 or final_percent > 100):
            self.add_error(
                "final_report_percent",
                "Рассчитанный размер оплаты Итогового отчёта должен быть в диапазоне от 0% до 100%.",
            )
        elif final_percent is not None:
            cleaned["final_report_percent"] = final_percent

        cleaned["registration_region"] = (cleaned.get("registration_region") or "").strip()
        cleaned["asset_owner_region"] = (cleaned.get("asset_owner_region") or "").strip()

        asset_owner_country = cleaned.get("asset_owner_country")
        asset_owner_identifier = ""
        if asset_owner_country:
            asset_owner_identifier = (
                LegalEntityIdentifier.objects.filter(country=asset_owner_country)
                .values_list("identifier", flat=True)
                .first()
                or ""
            )

        if cleaned.get("asset_owner_matches_customer"):
            cleaned["asset_owner"] = cleaned.get("customer") or ""
            cleaned["asset_owner_country"] = cleaned.get("country")
            cleaned["asset_owner_region"] = cleaned.get("registration_region") or ""
            cleaned["asset_owner_identifier"] = cleaned.get("identifier") or ""
            cleaned["asset_owner_registration_number"] = cleaned.get("registration_number") or ""
            cleaned["asset_owner_registration_date"] = cleaned.get("registration_date")
        else:
            cleaned["asset_owner_identifier"] = asset_owner_identifier

        if cleaned.get("service_composition_mode") == "customer_tz":
            cleaned["service_composition"] = cleaned.get("service_composition_customer_tz") or ""

        try:
            self._collect_stage_payloads()
        except forms.ValidationError as error:
            self.add_error("type_ids", error)
            return cleaned

        if getattr(self, "cleaned_stage_payloads", None) and len(self.cleaned_stage_payloads) > 1:
            summary_offer_raw = str(cleaned.get("summary_commercial_offer_payload") or "").strip()
            summary_totals_raw = str(cleaned.get("summary_commercial_totals_payload") or "").strip()
            if summary_offer_raw:
                self.cleaned_commercial_offers = self._normalize_summary_commercial_rows(
                    summary_offer_raw,
                    totals_raw=summary_totals_raw,
                )
            else:
                self.cleaned_commercial_offers, inferred_travel_mode = self._build_summary_commercial_fallback(
                    self.cleaned_stage_payloads
                )
                if not summary_totals_raw:
                    summary_totals_raw = json.dumps(
                        {
                            **(self.cleaned_stage_payloads[-1]["commercial_totals_json"] or {}),
                            "travel_expenses_mode": inferred_travel_mode,
                        },
                        ensure_ascii=False,
                    )
            self.cleaned_commercial_totals = (
                self._normalize_summary_commercial_totals(summary_totals_raw)
                if summary_totals_raw
                else self._merge_stage_commercial_totals_payload({})
            )
            if not str(self.cleaned_commercial_totals.get("travel_expenses_mode") or "").strip():
                _, inferred_travel_mode = self._build_summary_commercial_fallback(self.cleaned_stage_payloads)
                self.cleaned_commercial_totals["travel_expenses_mode"] = inferred_travel_mode
            summary_service_cost = self._parse_summary_service_cost(self.cleaned_commercial_totals)
            cleaned["service_cost"] = summary_service_cost

        if getattr(self, "cleaned_stage_payloads", None):
            last_stage = self.cleaned_stage_payloads[-1]
            cleaned["type"] = last_stage["product"]
            cleaned["service_composition_mode"] = last_stage["service_composition_mode"]
            cleaned["service_composition"] = last_stage["service_composition"]
            cleaned["service_composition_customer_tz"] = last_stage["service_composition_customer_tz"]
            cleaned["evaluation_date"] = last_stage["evaluation_date"]
            cleaned["service_term_months"] = last_stage["service_term_months"]
            cleaned["preliminary_report_date"] = last_stage["preliminary_report_date"]
            cleaned["final_report_term_weeks"] = last_stage["final_report_term_weeks"]
            cleaned["final_report_date"] = last_stage["final_report_date"]

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        stage_payloads = list(getattr(self, "cleaned_stage_payloads", []))
        last_stage = stage_payloads[-1] if stage_payloads else None
        if last_stage:
            instance.type = last_stage["product"]
            instance.service_sections_json = list(last_stage["service_sections_json"])
            instance.service_sections_editor_state = list(last_stage["service_sections_editor_state"])
            instance.service_customer_tz_editor_state = dict(last_stage["service_customer_tz_editor_state"])
            instance.service_composition_customer_tz = last_stage["service_composition_customer_tz"]
            instance.service_composition_mode = last_stage["service_composition_mode"]
            instance.service_composition = last_stage["service_composition"]
            instance.commercial_totals_json = dict(last_stage["commercial_totals_json"])
            instance.evaluation_date = last_stage["evaluation_date"]
            instance.service_term_months = last_stage["service_term_months"]
            instance.preliminary_report_date = last_stage["preliminary_report_date"]
            instance.final_report_term_weeks = last_stage["final_report_term_weeks"]
            instance.final_report_date = last_stage["final_report_date"]
            self.cleaned_service_sections = list(last_stage["service_sections_json"])
            self.cleaned_service_sections_editor_state = list(last_stage["service_sections_editor_state"])
            self.cleaned_service_customer_tz_editor_state = dict(last_stage["service_customer_tz_editor_state"])
            if len(stage_payloads) == 1:
                instance.commercial_totals_json = dict(last_stage["commercial_totals_json"])
                self.cleaned_commercial_offers = list(last_stage["commercial_offer_payload"])
                self.cleaned_commercial_totals = dict(last_stage["commercial_totals_json"])
            else:
                instance.commercial_totals_json = dict(getattr(self, "cleaned_commercial_totals", {}) or {})
        else:
            instance.service_sections_json = [
                {
                    "service_name": item["service_name"],
                    "code": item["code"],
                }
                for item in getattr(self, "cleaned_service_sections", [])
            ]
            instance.service_sections_editor_state = getattr(self, "cleaned_service_sections_editor_state", [])
            instance.service_customer_tz_editor_state = getattr(self, "cleaned_service_customer_tz_editor_state", {})
            instance.commercial_totals_json = getattr(self, "cleaned_commercial_totals", {})
        instance.stage_payloads_json = [
            {
                "rank": item["rank"],
                "product_id": item["product_id"],
                "service_sections_json": list(item["service_sections_json"]),
                "service_sections_editor_state": list(item["service_sections_editor_state"]),
                "service_customer_tz_editor_state": dict(item["service_customer_tz_editor_state"]),
                "service_composition_customer_tz": item["service_composition_customer_tz"],
                "service_composition_mode": item["service_composition_mode"],
                "service_composition": item["service_composition"],
                "commercial_offer_payload": [
                    {
                        "position": offer.get("position") or index,
                        "specialist": offer.get("specialist") or "",
                        "job_title": offer.get("job_title") or "",
                        "professional_status": offer.get("professional_status") or "",
                        "service_name": offer.get("service_name") or "",
                        "rate_eur_per_day": str(offer.get("rate_eur_per_day") or ""),
                        "asset_day_counts": list(offer.get("asset_day_counts") or []),
                        "total_eur_without_vat": str(offer.get("total_eur_without_vat") or ""),
                    }
                    for index, offer in enumerate(item["commercial_offer_payload"], start=1)
                ],
                "commercial_totals_json": dict(item["commercial_totals_json"]),
                "evaluation_date": _format_stage_date(item["evaluation_date"]),
                "service_term_months": str(item["service_term_months"] or ""),
                "preliminary_report_date": _format_stage_date(item["preliminary_report_date"]),
                "final_report_term_weeks": str(item["final_report_term_weeks"] or ""),
                "final_report_date": _format_stage_date(item["final_report_date"]),
            }
            for item in stage_payloads
        ]
        if commit:
            instance.save()
            self._save_ranked_products(instance)
        return instance

    def _save_ranked_products(self, proposal):
        product_ids = list(getattr(self, "cleaned_type_ids", []))
        ProposalRegistrationProduct.objects.filter(proposal=proposal).delete()
        if not product_ids:
            return
        ProposalRegistrationProduct.objects.bulk_create(
            [
                ProposalRegistrationProduct(
                    proposal=proposal,
                    product_id=product_id,
                    rank=rank,
                )
                for rank, product_id in enumerate(product_ids, start=1)
            ]
        )

    def clean_service_sections_editor_state(self):
        raw = (self.cleaned_data.get("service_sections_editor_state") or "").strip()
        if not raw:
            self.cleaned_service_sections_editor_state = []
            return "[]"
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректное состояние редактора состава услуг.")
        if not isinstance(value, list):
            raise forms.ValidationError("Некорректный формат состояния редактора состава услуг.")
        normalized = []
        for item in value:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "code": str(item.get("code") or "").strip(),
                    "service_name": str(item.get("service_name") or "").strip(),
                    "html": str(item.get("html") or "").strip(),
                    "plain_text": str(item.get("plain_text") or "").strip(),
                }
            )
        self.cleaned_service_sections_editor_state = normalized
        return json.dumps(normalized, ensure_ascii=False)

    def clean_service_customer_tz_editor_state(self):
        raw = (self.cleaned_data.get("service_customer_tz_editor_state") or "").strip()
        if not raw:
            self.cleaned_service_customer_tz_editor_state = {}
            return ""
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректное состояние редактора ТЗ Заказчика.")
        if not isinstance(value, dict):
            raise forms.ValidationError("Некорректный формат состояния редактора ТЗ Заказчика.")
        normalized = {
            "html": str(value.get("html") or "").strip(),
            "plain_text": str(value.get("plain_text") or "").strip(),
        }
        self.cleaned_service_customer_tz_editor_state = normalized
        return json.dumps(normalized, ensure_ascii=False)

    def clean_assets_payload(self):
        cleaned_assets = self._clean_related_payload(
            raw=self.cleaned_data.get("assets_payload"),
            item_label="актива",
        )
        self.cleaned_assets = cleaned_assets
        return self._serialize_related_payload(cleaned_assets)

    def clean_service_sections_payload(self):
        raw = (self.cleaned_data.get("service_sections_payload") or "").strip()
        if not raw:
            self.cleaned_service_sections = []
            return "[]"

        try:
            rows = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректные данные по составу услуг.")

        if not isinstance(rows, list):
            raise forms.ValidationError("Некорректный формат данных по составу услуг.")

        type_obj = self.cleaned_data.get("type")
        sections_by_name = {}
        if type_obj:
            for section in TypicalSection.objects.filter(product=type_obj).order_by("position", "id"):
                name_ru = (section.name_ru or "").strip()
                if name_ru and name_ru not in sections_by_name:
                    sections_by_name[name_ru] = (section.code or "").strip()

        cleaned_rows = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f"Строка состава услуг #{idx} передана в некорректном формате.")

            service_name = str(row.get("service_name") or "").strip()
            code = str(row.get("code") or "").strip()
            if not service_name and not code:
                continue
            if not service_name:
                raise forms.ValidationError(
                    f"В строке состава услуг #{idx} заполните поле «Наименование раздела (услуги)»."
                )

            expected_code = sections_by_name.get(service_name, "")
            cleaned_rows.append(
                {
                    "position": len(cleaned_rows) + 1,
                    "service_name": service_name,
                    "code": expected_code or code,
                }
            )

        self.cleaned_service_sections = cleaned_rows
        return json.dumps(
            [
                {
                    "service_name": item["service_name"],
                    "code": item["code"],
                }
                for item in cleaned_rows
            ],
            ensure_ascii=False,
        )

    def clean_legal_entities_payload(self):
        cleaned_legal_entities = self._clean_related_payload(
            raw=self.cleaned_data.get("legal_entities_payload"),
            item_label="юрлица",
            require_asset_short_name=True,
            require_short_name=False,
        )
        self.cleaned_legal_entities = cleaned_legal_entities
        return self._serialize_related_payload(cleaned_legal_entities, include_asset_short_name=True)

    def clean_objects_payload(self):
        raw = (self.cleaned_data.get("objects_payload") or "").strip()
        if not raw:
            self.cleaned_objects = []
            return "[]"

        try:
            rows = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректные данные по объектам.")

        if not isinstance(rows, list):
            raise forms.ValidationError("Некорректный формат данных по объектам.")

        cleaned_objects = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f"Строка объекта #{idx} передана в некорректном формате.")

            legal_entity_short_name = str(row.get("legal_entity_short_name") or "").strip()
            short_name = str(row.get("short_name") or "").strip()
            region = str(row.get("region") or "").strip()
            object_type = str(row.get("object_type") or "").strip()
            license_value = str(row.get("license") or "").strip()
            registration_date_raw = str(row.get("registration_date") or "").strip()

            if not any([legal_entity_short_name, short_name, region, object_type, license_value, registration_date_raw]):
                continue

            # The objects editor is currently hidden in the UI, but row syncing from
            # legal entities can still create placeholder rows that only carry the
            # linked legal entity name. Those hidden placeholders must not block save.
            if legal_entity_short_name and not short_name and not any([region, object_type, license_value, registration_date_raw]):
                continue

            if not legal_entity_short_name:
                raise forms.ValidationError(
                    f"В строке объекта #{idx} заполните поле «Наименование юрлица (краткое)»."
                )
            if not short_name:
                raise forms.ValidationError(
                    f"В строке объекта #{idx} заполните поле «Наименование объекта (краткое)»."
                )

            registration_date = None
            if registration_date_raw:
                registration_date = self._parse_asset_date(registration_date_raw, idx, item_label="объекта")

            cleaned_objects.append(
                {
                    "position": len(cleaned_objects) + 1,
                    "legal_entity_short_name": legal_entity_short_name,
                    "short_name": short_name,
                    "region": region,
                    "object_type": object_type,
                    "license": license_value,
                    "registration_date": registration_date,
                }
            )

        self.cleaned_objects = cleaned_objects
        return json.dumps(
            [
                {
                    "legal_entity_short_name": item["legal_entity_short_name"],
                    "short_name": item["short_name"],
                    "region": item["region"],
                    "object_type": item["object_type"],
                    "license": item["license"],
                    "registration_date": item["registration_date"].strftime("%d.%m.%Y")
                    if item["registration_date"]
                    else "",
                }
                for item in cleaned_objects
            ],
            ensure_ascii=False,
        )

    def _extract_travel_expenses_mode_from_payload(self):
        raw = str(self.data.get("commercial_totals_payload") or "").strip()
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        mode = str(payload.get("travel_expenses_mode") or "").strip()
        if mode in {PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL, PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION}:
            return mode
        return ""

    def clean_commercial_offer_payload(self):
        raw = (self.cleaned_data.get("commercial_offer_payload") or "").strip()
        if not raw:
            self.cleaned_commercial_offers = []
            return "[]"

        try:
            rows = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректные данные по коммерческому предложению.")

        if not isinstance(rows, list):
            raise forms.ValidationError("Некорректный формат данных по коммерческому предложению.")

        travel_expenses_mode = self._extract_travel_expenses_mode_from_payload()
        cleaned_rows = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f"Строка коммерческого предложения #{idx} передана в некорректном формате.")

            specialist = str(row.get("specialist") or "").strip()
            job_title = str(row.get("job_title") or "").strip()
            professional_status = str(row.get("professional_status") or "").strip()
            service_name = str(row.get("service_name") or "").strip()
            rate_raw = str(row.get("rate_eur_per_day") or "").strip()
            total_raw = str(row.get("total_eur_without_vat") or "").strip()
            asset_day_counts_raw = row.get("asset_day_counts") or []

            if not isinstance(asset_day_counts_raw, list):
                raise forms.ValidationError(
                    f"Строка коммерческого предложения #{idx}: поле «Количество дней» передано некорректно."
                )

            is_travel_expenses_row = is_proposal_travel_expenses_name(service_name)
            asset_day_counts = []
            if is_travel_expenses_row and travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                for day_idx, raw_value in enumerate(asset_day_counts_raw, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        asset_day_counts.append("")
                        continue
                    parsed_amount = self._parse_payload_decimal(
                        value,
                        f"Строка коммерческого предложения #{idx}: значение по активу #{day_idx} заполнено некорректно.",
                    )
                    if parsed_amount is not None and parsed_amount < 0:
                        raise forms.ValidationError(
                            f"Строка коммерческого предложения #{idx}: значение по активу #{day_idx} не может быть отрицательным."
                        )
                    asset_day_counts.append(self._serialize_payload_decimal(parsed_amount))
            else:
                for day_idx, raw_value in enumerate(asset_day_counts_raw, start=1):
                    value = str(raw_value or "").strip()
                    if not value:
                        asset_day_counts.append("")
                        continue
                    try:
                        parsed_int = int(value)
                    except (TypeError, ValueError):
                        raise forms.ValidationError(
                            f"Строка коммерческого предложения #{idx}: значение дня #{day_idx} заполнено некорректно."
                        )
                    if parsed_int < 0:
                        raise forms.ValidationError(
                            f"Строка коммерческого предложения #{idx}: значение дня #{day_idx} не может быть отрицательным."
                        )
                    asset_day_counts.append(parsed_int)

            row_has_data = any(
                [
                    specialist,
                    job_title,
                    professional_status,
                    service_name,
                    rate_raw,
                    total_raw,
                    any(value != "" for value in asset_day_counts),
                ]
            )
            if not row_has_data:
                continue

            rate_value = self._parse_payload_decimal(
                rate_raw,
                f"Строка коммерческого предложения #{idx}: поле «Ставка, евро / день» заполнено некорректно.",
            )
            total_value = self._parse_payload_decimal(
                total_raw,
                f"Строка коммерческого предложения #{idx}: поле «Итого, евро без НДС» заполнено некорректно.",
            )
            if is_travel_expenses_row:
                rate_value = None
                if travel_expenses_mode == PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION:
                    total_value = sum(
                        (
                            Decimal(str(value))
                            for value in asset_day_counts
                            if value not in (None, "")
                        ),
                        Decimal("0"),
                    )
                else:
                    asset_day_counts = ["" for _ in asset_day_counts]

            cleaned_rows.append(
                {
                    "position": len(cleaned_rows) + 1,
                    "specialist": specialist,
                    "job_title": job_title,
                    "professional_status": professional_status,
                    "service_name": service_name,
                    "rate_eur_per_day": rate_value,
                    "asset_day_counts": asset_day_counts,
                    "total_eur_without_vat": total_value,
                }
            )

        self.cleaned_commercial_offers = cleaned_rows
        return json.dumps(
            [
                {
                    "specialist": item["specialist"],
                    "job_title": item["job_title"],
                    "professional_status": item["professional_status"],
                    "service_name": item["service_name"],
                    "rate_eur_per_day": str(item["rate_eur_per_day"] or ""),
                    "asset_day_counts": item["asset_day_counts"],
                    "total_eur_without_vat": str(item["total_eur_without_vat"] or ""),
                }
                for item in cleaned_rows
            ],
            ensure_ascii=False,
        )

    def clean_commercial_totals_payload(self):
        raw = (self.cleaned_data.get("commercial_totals_payload") or "").strip()
        if not raw:
            self.cleaned_commercial_totals = {}
            return "{}"

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректные данные по итогам коммерческого предложения.")

        if not isinstance(payload, dict):
            raise forms.ValidationError("Некорректный формат данных по итогам коммерческого предложения.")

        exchange_rate = self._parse_payload_decimal(
            str(payload.get("exchange_rate") or "").strip(),
            "Поле «ИТОГО, рубли без НДС» заполнено некорректно.",
        )
        discount_percent = self._parse_payload_decimal(
            str(payload.get("discount_percent") or "").replace("%", "").strip(),
            "Поле «ИТОГО, рубли без НДС с учетом скидки» заполнено некорректно.",
        )
        contract_total = self._parse_payload_decimal(
            str(payload.get("contract_total") or "").strip(),
            "Поле «ИТОГО в договор, рубли без НДС с учётом дополнительной скидки» заполнено некорректно.",
        )
        contract_total_auto = self._parse_payload_decimal(
            str(payload.get("contract_total_auto") or "").strip(),
            "Расчётное значение итога по договору заполнено некорректно.",
        )
        travel_expenses_mode = str(payload.get("travel_expenses_mode") or "").strip() or PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL

        if discount_percent is not None and (discount_percent < 0 or discount_percent > 100):
            raise forms.ValidationError("Скидка должна быть в диапазоне от 0% до 100%.")
        if travel_expenses_mode not in {
            PROPOSAL_TRAVEL_EXPENSES_MODE_ACTUAL,
            PROPOSAL_TRAVEL_EXPENSES_MODE_CALCULATION,
        }:
            raise forms.ValidationError("Режим строки командировочных расходов заполнен некорректно.")

        self.cleaned_commercial_totals = {
            "exchange_rate": self._serialize_payload_decimal(exchange_rate),
            "discount_percent": self._serialize_payload_decimal(discount_percent),
            "contract_total": self._serialize_payload_decimal(contract_total),
            "contract_total_auto": self._serialize_payload_decimal(contract_total_auto),
            "rub_total_service_text": str(payload.get("rub_total_service_text") or "").strip(),
            "discounted_total_service_text": str(payload.get("discounted_total_service_text") or "").strip(),
            "travel_expenses_mode": travel_expenses_mode,
        }
        return json.dumps(self.cleaned_commercial_totals, ensure_ascii=False)

    def clean_report_languages(self):
        has_choice_values = False
        selected_choices = []
        if hasattr(self.data, "getlist"):
            has_choice_values = "report_language_choices" in self.data
            if has_choice_values:
                selected_choices = normalize_proposal_report_languages(self.data.getlist("report_language_choices"))
        elif isinstance(self.data, dict) and "report_language_choices" in self.data:
            has_choice_values = True
            raw_value = self.data.get("report_language_choices")
            if isinstance(raw_value, (list, tuple)):
                selected_choices = normalize_proposal_report_languages(list(raw_value))
            else:
                selected_choices = normalize_proposal_report_languages(raw_value)
        if has_choice_values:
            return ", ".join(selected_choices)
        return ", ".join(normalize_proposal_report_languages(self.cleaned_data.get("report_languages")))

    def _clean_related_payload(self, raw, *, item_label, require_asset_short_name=False, require_short_name=True):
        raw = (raw or "").strip()
        if not raw:
            return []

        try:
            rows = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError(f"Некорректные данные по {item_label}.")

        if not isinstance(rows, list):
            raise forms.ValidationError(f"Некорректный формат данных по {item_label}.")

        cleaned_rows = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f"Строка {item_label} #{idx} передана в некорректном формате.")

            asset_short_name = str(row.get("asset_short_name") or "").strip()
            short_name = str(row.get("short_name") or "").strip()
            country_id = str(row.get("country_id") or "").strip()
            identifier = str(row.get("identifier") or "").strip()
            registration_number = str(row.get("registration_number") or "").strip()
            registration_date_raw = str(row.get("registration_date") or "").strip()
            selected_identifier_record_id = str(row.get("selected_identifier_record_id") or "").strip()
            selected_from_autocomplete_raw = str(row.get("selected_from_autocomplete") or "").strip().lower()
            user_edited_raw = str(row.get("user_edited") or "").strip().lower()

            row_has_data = any(
                [
                    asset_short_name if require_asset_short_name else "",
                    short_name,
                    country_id,
                    identifier,
                    registration_number,
                    registration_date_raw,
                    selected_identifier_record_id,
                ]
            )
            if not row_has_data:
                continue

            if require_asset_short_name and not asset_short_name:
                raise forms.ValidationError(
                    f"В строке {item_label} #{idx} заполните поле «Наименование актива (краткое)»."
                )

            if require_short_name and not short_name:
                raise forms.ValidationError(f"В строке {item_label} #{idx} заполните поле «Наименование (краткое)».")

            registration_date = None
            if registration_date_raw:
                registration_date = self._parse_asset_date(registration_date_raw, idx, item_label=item_label)

            country = None
            if country_id:
                country = OKSMCountry.objects.filter(pk=country_id).first()

            cleaned_rows.append(
                {
                    "position": len(cleaned_rows) + 1,
                    "asset_short_name": asset_short_name,
                    "short_name": short_name,
                    "country": country,
                    "identifier": identifier,
                    "registration_number": registration_number,
                    "registration_date": registration_date,
                    "selected_identifier_record_id": selected_identifier_record_id,
                    "selected_from_autocomplete": selected_from_autocomplete_raw in {"1", "true", "yes", "on"},
                    "user_edited": user_edited_raw in {"1", "true", "yes", "on"},
                }
            )
        return cleaned_rows

    def _serialize_related_payload(self, items, include_asset_short_name=False):
        return json.dumps(
            [
                {
                    **(
                        {"asset_short_name": item["asset_short_name"]}
                        if include_asset_short_name
                        else {}
                    ),
                    "short_name": item["short_name"],
                    "country_id": item["country"].pk if item["country"] else "",
                    "country_name": item["country"].short_name if item["country"] else "",
                    "identifier": item["identifier"],
                    "registration_number": item["registration_number"],
                    "registration_date": item["registration_date"].strftime("%d.%m.%Y")
                    if item["registration_date"]
                    else "",
                    "selected_identifier_record_id": item.get("selected_identifier_record_id", ""),
                    "selected_from_autocomplete": bool(item.get("selected_from_autocomplete")),
                    "user_edited": bool(item.get("user_edited")),
                }
                for item in items
            ],
            ensure_ascii=False,
        )

    def _parse_asset_date(self, value, row_index, *, item_label="актива"):
        for fmt in self._asset_date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise forms.ValidationError(
            f"В строке {item_label} #{row_index} поле «Дата регистрации» заполнено некорректно."
        )

    def _parse_payload_decimal(self, value, error_message):
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            parsed = Decimal(normalized)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError(error_message)
        if parsed < 0:
            raise forms.ValidationError(error_message)
        return parsed

    def _serialize_payload_decimal(self, value):
        if value is None:
            return ""
        return str(value)

    def save_assets(self, proposal, user=None):
        assets = getattr(self, "cleaned_assets", [])
        proposal.assets.all().delete()
        if not assets:
            return

        ProposalAsset.objects.bulk_create(
            [
                ProposalAsset(
                    proposal=proposal,
                    position=item["position"],
                    short_name=item["short_name"],
                    country=item["country"],
                    identifier=item["identifier"],
                    registration_number=item["registration_number"],
                    registration_date=item["registration_date"],
                )
                for item in assets
            ]
        )

    def save_legal_entities(self, proposal, user=None):
        legal_entities = getattr(self, "cleaned_legal_entities", [])
        proposal.legal_entities.all().delete()
        if not legal_entities:
            return

        ProposalLegalEntity.objects.bulk_create(
            [
                ProposalLegalEntity(
                    proposal=proposal,
                    position=item["position"],
                    asset_short_name=item["asset_short_name"],
                    short_name=item["short_name"],
                    country=item["country"],
                    identifier=item["identifier"],
                    registration_number=item["registration_number"],
                    registration_date=item["registration_date"],
                )
                for item in legal_entities
            ]
        )

    def save_objects(self, proposal, user=None):
        objects = getattr(self, "cleaned_objects", [])
        proposal.proposal_objects.all().delete()
        if not objects:
            return

        ProposalObject.objects.bulk_create(
            [
                ProposalObject(
                    proposal=proposal,
                    position=item["position"],
                    legal_entity_short_name=item["legal_entity_short_name"],
                    short_name=item["short_name"],
                    region=item["region"],
                    object_type=item["object_type"],
                    license=item["license"],
                    registration_date=item["registration_date"],
                )
                for item in objects
            ]
        )

    def save_commercial_offers(self, proposal, user=None):
        items = getattr(self, "cleaned_commercial_offers", [])
        proposal.commercial_offers.all().delete()
        if not items:
            return

        ProposalCommercialOffer.objects.bulk_create(
            [
                ProposalCommercialOffer(
                    proposal=proposal,
                    position=item.get("position") or index,
                    specialist=item["specialist"],
                    job_title=item["job_title"],
                    professional_status=item["professional_status"],
                    service_name=item["service_name"],
                    rate_eur_per_day=(None if item.get("rate_eur_per_day") in ("", None) else item.get("rate_eur_per_day")),
                    asset_day_counts=item["asset_day_counts"],
                    total_eur_without_vat=(
                        None if item.get("total_eur_without_vat") in ("", None) else item.get("total_eur_without_vat")
                    ),
                )
                for index, item in enumerate(items, start=1)
            ]
        )


class ProposalDispatchForm(BootstrapMixin, forms.ModelForm):
    recipient_country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "proposal-dispatch-recipient-country-select"}),
    )
    recipient_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(
            attrs={
                "readonly": True,
                "tabindex": "-1",
                "class": "form-control readonly-field",
                "id": "proposal-dispatch-recipient-identifier-field",
            }
        ),
    )
    recipient_registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=forms.TextInput(attrs={**DATE_INPUT_ATTRS, "id": "proposal-dispatch-recipient-registration-date"}),
        input_formats=DATE_INPUT_FORMATS,
    )
    recipient_job_title = forms.CharField(label="Должность", required=False, widget=forms.TextInput())
    contact_last_name = forms.CharField(
        label="Фамилия",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Искать по фамилии контакта"}),
    )
    contact_first_name = forms.CharField(label="Имя", required=False, widget=forms.TextInput())
    contact_middle_name = forms.CharField(label="Отчество", required=False, widget=forms.TextInput())

    @staticmethod
    def _split_contact_name_parts(value):
        parts = [part for part in str(value or "").strip().split() if part]
        if not parts:
            return "", "", ""
        last_name = parts[0]
        first_name = parts[1] if len(parts) > 1 else ""
        middle_name = " ".join(parts[2:]) if len(parts) > 2 else ""
        return last_name, first_name, middle_name

    class Meta:
        model = ProposalRegistration
        fields = [
            "docx_file_name",
            "docx_file_link",
            "pdf_file_name",
            "pdf_file_link",
            "sent_date",
            "recipient",
            "recipient_country",
            "recipient_identifier",
            "recipient_registration_number",
            "recipient_registration_date",
            "recipient_job_title",
            "contact_email",
        ]
        widgets = {
            "docx_file_name": forms.TextInput(),
            "docx_file_link": forms.TextInput(),
            "pdf_file_name": forms.TextInput(),
            "pdf_file_link": forms.TextInput(),
            "sent_date": forms.TextInput(
                attrs={
                    "readonly": True,
                    "tabindex": "-1",
                    "class": "readonly-field",
                }
            ),
            "recipient": forms.TextInput(
                attrs={
                    "placeholder": "Искать по наименованию и регистрационному номеру",
                    "id": "proposal-dispatch-recipient-field",
                }
            ),
            "recipient_registration_number": forms.TextInput(),
            "recipient_job_title": forms.TextInput(),
            "contact_email": forms.EmailInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _apply_russian_error_messages(field)
        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.recipient_country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.recipient_country_id)).distinct().order_by(
                "short_name"
            )
        self.fields["recipient_country"].queryset = country_qs
        self.fields["recipient_country"].label_from_instance = lambda obj: obj.short_name
        if not self.is_bound and not getattr(self.instance, "recipient_country_id", None):
            default_country = country_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["recipient_country"].initial = default_country.pk
        if self.is_bound:
            self.fields["contact_last_name"].initial = (self.data.get("contact_last_name") or "").strip()
            self.fields["contact_first_name"].initial = (self.data.get("contact_first_name") or "").strip()
            self.fields["contact_middle_name"].initial = (self.data.get("contact_middle_name") or "").strip()
        else:
            last_name, first_name, middle_name = self._split_contact_name_parts(
                getattr(self.instance, "contact_full_name", "")
            )
            self.fields["contact_last_name"].initial = last_name
            self.fields["contact_first_name"].initial = first_name
            self.fields["contact_middle_name"].initial = middle_name
        self._bootstrapify()

    def save(self, commit=True):
        instance = super().save(commit=False)
        name_parts = [
            (self.cleaned_data.get("contact_last_name") or "").strip(),
            (self.cleaned_data.get("contact_first_name") or "").strip(),
            (self.cleaned_data.get("contact_middle_name") or "").strip(),
        ]
        instance.contact_full_name = " ".join(part for part in name_parts if part).strip()
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ProposalTemplateForm(forms.ModelForm):
    class Meta:
        model = ProposalTemplate
        fields = [
            "group_member",
            "product",
            "sample_name",
            "version",
            "file",
        ]
        widgets = {
            "group_member": forms.Select(attrs={"class": "form-select"}),
            "product": forms.Select(attrs={"class": "form-select"}),
            "sample_name": forms.TextInput(
                attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}
            ),
            "version": forms.TextInput(
                attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}
            ),
            "file": _ProposalFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._orig_sample_name = ""
        self._orig_version = ""
        if self.instance and self.instance.pk:
            self._orig_sample_name = self.instance.sample_name or ""
            self._orig_version = self.instance.version or ""

        order_map = _proposal_group_member_order_map()
        members_qs = GroupMember.objects.all()
        self.fields["group_member"].queryset = members_qs
        self.fields["group_member"].label_from_instance = (
            lambda obj: _proposal_group_member_label(obj, order_map.get(obj.pk, 0))
        )
        self.fields["group_member"].required = True

        self.fields["product"].queryset = Product.objects.order_by("position", "id")
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
        self.fields["file"].required = not (self.instance and self.instance.pk and self.instance.file)

        self.group_alpha2_map = {str(m.pk): (m.country_alpha2 or "").strip().upper() for m in members_qs}
        self.group_short_name_map = {str(m.pk): (m.short_name or "").strip() for m in members_qs}

        existing = ProposalTemplate.objects.select_related("product", "group_member").all()
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        version_map = {}
        for template in existing:
            key = f"{template.group_member_id or ''}:{template.product_id or ''}"
            try:
                version = int(template.version)
            except (ValueError, TypeError):
                version = 0
            version_map[key] = max(version_map.get(key, 0), version)
        self.version_map = version_map

        self.current_pair = ""
        self.current_version = ""
        if self.instance and self.instance.pk:
            self.current_pair = f"{self.instance.group_member_id or ''}:{self.instance.product_id or ''}"
            self.current_version = self.instance.version or ""

    def save(self, commit=True):
        import os

        instance = super().save(commit=False)
        alpha2 = ""
        short_name = ""
        if instance.group_member_id:
            alpha2 = (instance.group_member.country_alpha2 or "").strip().upper()
            short_name = (instance.group_member.short_name or "").strip()
        product_short = ""
        if instance.product_id:
            product_short = (instance.product.short_name or "").strip()

        prefix = " ".join(part for part in [alpha2, "Шаблон ТКП"] if part)
        tail = "_".join(part for part in [short_name, product_short] if part)
        base_name = "_".join(part for part in [prefix, tail] if part)
        pair_key = f"{instance.group_member_id or ''}:{instance.product_id or ''}"
        existing = ProposalTemplate.objects.all()

        if instance.pk and pair_key == self.current_pair:
            version = self._orig_version or "1"
        else:
            if instance.pk:
                existing = existing.exclude(pk=instance.pk)
            version = str(self._next_version(existing, instance.group_member_id, instance.product_id))

        instance.sample_name = base_name
        instance.version = version

        uploaded = self.cleaned_data.get("file")
        file_stub = f"{instance.sample_name}_v{instance.version}"
        if uploaded:
            ext = os.path.splitext(uploaded.name)[1]
            instance.file.name = file_stub + ext
        elif instance.pk and instance.file:
            old_path = instance.file.name
            ext = os.path.splitext(old_path)[1]
            new_name = "proposal_templates/" + file_stub + ext
            if old_path != new_name:
                storage = instance.file.storage
                if storage.exists(old_path):
                    old_full = storage.path(old_path)
                    new_full = storage.path(new_name)
                    os.makedirs(os.path.dirname(new_full), exist_ok=True)
                    os.rename(old_full, new_full)
                instance.file.name = new_name

        if commit:
            instance.save()
        return instance

    @staticmethod
    def _next_version(qs, group_member_id, product_id):
        max_version = 0
        for template in qs:
            if template.group_member_id != group_member_id or template.product_id != product_id:
                continue
            try:
                version = int(template.version)
            except (ValueError, TypeError):
                version = 0
            max_version = max(max_version, version)
        return max_version + 1


class ProposalVariableForm(forms.ModelForm):
    source_section = forms.ChoiceField(
        label="Раздел",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proposal_var_source_section"}),
    )
    source_table = forms.ChoiceField(
        label="Таблица",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proposal_var_source_table"}),
    )
    source_column = forms.ChoiceField(
        label="Столбец",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proposal_var_source_column"}),
    )

    class Meta:
        model = ProposalVariable
        fields = [
            "key",
            "description",
            "source_section",
            "source_table",
            "source_column",
        ]
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control", "placeholder": "{{variable_name}}"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Описание переменной"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_computed = bool(
            self.instance and self.instance.pk and self.instance.is_computed
        )

        default_section = "proposals"
        default_table = "registry"
        section_value = (
            self.data.get("source_section")
            or self.initial.get("source_section")
            or (self.instance.source_section if self.instance and self.instance.pk else "")
        )
        table_value = (
            self.data.get("source_table")
            or self.initial.get("source_table")
            or (self.instance.source_table if self.instance and self.instance.pk else "")
        )

        if self.is_computed:
            self.fields["source_section"].choices = [("", "---")]
            self.fields["source_table"].choices = [("", "---")]
            self.fields["source_column"].choices = [("", "---")]
            locked_style = "background-color:#f8f9fa; color:#6c757d;"
            self.fields["key"].widget.attrs.update({
                "readonly": True,
                "tabindex": "-1",
                "style": locked_style,
            })
            self.fields["key"].disabled = True
            for field_name in ("source_section", "source_table", "source_column"):
                self.fields[field_name].disabled = True
                self.fields[field_name].widget.attrs.update({
                    "disabled": True,
                    "style": locked_style,
                })
        else:
            section_value = section_value or default_section
            table_value = table_value or default_table
            self.fields["source_section"].choices = _proposal_variable_section_choices()
            self.fields["source_table"].choices = _proposal_variable_table_choices(section_value)
            self.fields["source_column"].choices = _proposal_variable_column_choices(section_value, table_value)

        if not self.instance.pk and "source_section" not in self.data:
            self.fields["source_section"].initial = default_section
        if not self.instance.pk and "source_table" not in self.data:
            self.fields["source_table"].initial = default_table

    def clean_key(self):
        import re

        if self.is_computed:
            return self.instance.key
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
        if self.is_computed:
            cleaned["source_section"] = self.instance.source_section
            cleaned["source_table"] = self.instance.source_table
            cleaned["source_column"] = self.instance.source_column
            return cleaned
        sec = cleaned.get("source_section", "")
        tbl = cleaned.get("source_table", "")
        col = cleaned.get("source_column", "")
        if not (sec and tbl and col):
            raise forms.ValidationError("Необходимо заполнить поля Раздел, Таблица и Столбец.")
        if sec != "proposals" or tbl != "registry":
            raise forms.ValidationError("Для переменных ТКП доступен только раздел «ТКП» и таблица «Реестр ТКП».")
        from core.column_registry import validate_column_ref

        if not validate_column_ref(sec, tbl, col):
            raise forms.ValidationError("Указанная комбинация Раздел/Таблица/Столбец не существует.")
        return cleaned
