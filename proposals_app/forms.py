import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import forms
from django.db import models
from django.db.models import Max
from django.utils import timezone

from classifiers_app.models import LegalEntityIdentifier, OKSMCountry, OKVCurrency
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
    ProposalTemplate,
    ProposalVariable,
)
from .cbr import get_cbr_eur_rate_for_today

DATE_INPUT_ATTRS = {"class": "js-date", "autocomplete": "off"}
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]
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


class ProposalRegistrationForm(BootstrapMixin, forms.ModelForm):
    number = forms.IntegerField(
        label="Номер",
        required=True,
        min_value=3333,
        max_value=9999,
        widget=forms.NumberInput(attrs={"min": 3333, "max": 9999, "placeholder": "3333-9999"}),
    )
    group_member = forms.ModelChoiceField(
        label="Группа",
        queryset=GroupMember.objects.none(),
        required=True,
        widget=forms.Select(attrs={"id": "proposal-group-select"}),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "proposal-country-select"}),
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
        label="Срок оказания услуг, мес.",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1"}),
    )
    preliminary_report_date = forms.DateField(
        label="Дата предварительного отчёта",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )
    final_report_date = forms.DateField(
        label="Дата итогового отчёта",
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
            "identifier",
            "registration_number",
            "registration_date",
            "asset_owner",
            "asset_owner_country",
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
            "name": forms.TextInput(attrs={"placeholder": "Название"}),
            "customer": forms.TextInput(attrs={"placeholder": "Искать по наименованию и регистрационному номеру"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        getlist = self.data.getlist if hasattr(self.data, "getlist") else lambda key: []
        if self.data:
            data = self.data.copy()
            for field_name in self._decimal_text_fields:
                value = data.get(field_name, "")
                if value:
                    data[field_name] = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            self.data = data
        for field in self.fields.values():
            _apply_russian_error_messages(field)
        self.fields["group_member"].queryset = _group_choices()
        self.fields["group_member"].label_from_instance = lambda obj: obj.group_display_label
        self.fields["group_member"].empty_label = "— Не выбрано —"
        self.fields["type"].queryset = Product.objects.order_by("position", "id")
        self.fields["type"].label_from_instance = lambda obj: obj.short_name
        self.fields["type"].required = True
        self.fields["type"].empty_label = "— Не выбрано —"
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
            eur_rate = get_cbr_eur_rate_for_today()
            if eur_rate is not None and not str(totals_payload.get("exchange_rate") or "").strip():
                totals_payload["exchange_rate"] = format(eur_rate.quantize(Decimal("0.0001")), "f")
            self.fields["commercial_totals_payload"].initial = json.dumps(
                totals_payload,
                ensure_ascii=False,
            )
        elif "commercial_totals_payload" not in self.data:
            totals_payload = {
                "discount_percent": "5",
                "rub_total_service_text": "Курс евро Банка России на текущую дату:",
                "discounted_total_service_text": "Размер скидки:",
            }
            eur_rate = get_cbr_eur_rate_for_today()
            if eur_rate is not None:
                totals_payload["exchange_rate"] = format(eur_rate.quantize(Decimal("0.0001")), "f")
            self.fields["commercial_totals_payload"].initial = json.dumps(
                totals_payload,
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
        if "service_sections_editor_state" not in self.data:
            self.fields["service_sections_editor_state"].initial = "[]"
        if "service_customer_tz_editor_state" not in self.data:
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

    def clean_group_member(self):
        member = self.cleaned_data.get("group_member")
        if member and not (member.country_alpha2 or "").strip():
            raise forms.ValidationError("Для выбранной строки состава группы не заполнен код Альфа-2.")
        return member

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
            cleaned["asset_owner_identifier"] = cleaned.get("identifier") or ""
            cleaned["asset_owner_registration_number"] = cleaned.get("registration_number") or ""
            cleaned["asset_owner_registration_date"] = cleaned.get("registration_date")
        else:
            cleaned["asset_owner_identifier"] = asset_owner_identifier

        if cleaned.get("service_composition_mode") == "customer_tz":
            cleaned["service_composition"] = cleaned.get("service_composition_customer_tz") or ""

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.service_sections_json = [
            {
                "service_name": item["service_name"],
                "code": item["code"],
            }
            for item in getattr(self, "cleaned_service_sections", [])
        ]
        instance.commercial_totals_json = getattr(self, "cleaned_commercial_totals", {})
        if commit:
            instance.save()
        return instance

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

            asset_day_counts = []
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

        if discount_percent is not None and (discount_percent < 0 or discount_percent > 100):
            raise forms.ValidationError("Скидка должна быть в диапазоне от 0% до 100%.")

        self.cleaned_commercial_totals = {
            "exchange_rate": self._serialize_payload_decimal(exchange_rate),
            "discount_percent": self._serialize_payload_decimal(discount_percent),
            "contract_total": self._serialize_payload_decimal(contract_total),
            "contract_total_auto": self._serialize_payload_decimal(contract_total_auto),
            "rub_total_service_text": str(payload.get("rub_total_service_text") or "").strip(),
            "discounted_total_service_text": str(payload.get("discounted_total_service_text") or "").strip(),
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

            row_has_data = any(
                [
                    asset_short_name if require_asset_short_name else "",
                    short_name,
                    country_id,
                    identifier,
                    registration_number,
                    registration_date_raw,
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
                    position=item["position"],
                    specialist=item["specialist"],
                    job_title=item["job_title"],
                    professional_status=item["professional_status"],
                    service_name=item["service_name"],
                    rate_eur_per_day=item["rate_eur_per_day"],
                    asset_day_counts=item["asset_day_counts"],
                    total_eur_without_vat=item["total_eur_without_vat"],
                )
                for item in items
            ]
        )


class ProposalDispatchForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ProposalRegistration
        fields = [
            "docx_file_name",
            "docx_file_link",
            "pdf_file_name",
            "pdf_file_link",
            "sent_date",
            "recipient",
            "contact_full_name",
            "contact_email",
        ]
        widgets = {
            "docx_file_name": forms.TextInput(),
            "docx_file_link": forms.TextInput(),
            "pdf_file_name": forms.TextInput(),
            "pdf_file_link": forms.TextInput(),
            "sent_date": forms.TextInput(),
            "recipient": forms.TextInput(),
            "contact_full_name": forms.TextInput(),
            "contact_email": forms.EmailInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


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
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proposal_var_source_section"}),
    )
    source_table = forms.ChoiceField(
        label="Таблица",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_proposal_var_source_table"}),
    )
    source_column = forms.ChoiceField(
        label="Столбец",
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

        default_section = "proposals"
        default_table = "registry"
        section_value = (
            self.data.get("source_section")
            or self.initial.get("source_section")
            or (self.instance.source_section if self.instance and self.instance.pk else "")
            or default_section
        )
        table_value = (
            self.data.get("source_table")
            or self.initial.get("source_table")
            or (self.instance.source_table if self.instance and self.instance.pk else "")
            or default_table
        )

        self.fields["source_section"].choices = _proposal_variable_section_choices()
        self.fields["source_table"].choices = _proposal_variable_table_choices(section_value)
        self.fields["source_column"].choices = _proposal_variable_column_choices(section_value, table_value)

        if not self.instance.pk and "source_section" not in self.data:
            self.fields["source_section"].initial = default_section
        if not self.instance.pk and "source_table" not in self.data:
            self.fields["source_table"].initial = default_table

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
        if not (sec and tbl and col):
            raise forms.ValidationError("Необходимо заполнить поля Раздел, Таблица и Столбец.")
        if sec != "proposals" or tbl != "registry":
            raise forms.ValidationError("Для переменных ТКП доступен только раздел «ТКП» и таблица «Реестр ТКП».")
        from core.column_registry import validate_column_ref

        if not validate_column_ref(sec, tbl, col):
            raise forms.ValidationError("Указанная комбинация Раздел/Таблица/Столбец не существует.")
        return cleaned
