import json
from datetime import date as date_type, datetime
from decimal import Decimal
from types import SimpleNamespace

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from classifiers_app.models import LegalEntityIdentifier, OKSMCountry
from group_app.models import GroupMember
from policy_app.models import (
    Product,
    SYSTEM_DSC_SECTION_CODE,
    SYSTEM_DSC_SECTION_DEFAULTS,
    TypicalSection,
    TypicalServiceTerm,
    ensure_system_dsc_section,
    is_system_dsc_code,
)
from projects_app.forms import (
    BootstrapMixin,
    DATE_INPUT_FORMATS,
    _date_input_widget,
    _group_choices,
    _project_manager_choices,
    _project_region_choices_for_country,
    _resolve_project_manager_choice,
)
from projects_app.models import Performer
from proposals_app.models import ProposalRegistration, ProposalRegistrationProduct
from .models import (
    ContractProjectRegistration,
    ContractSubject,
    ContractTemplate,
    ContractVariable,
)

SECTION_ALL_VALUE = "__all__"


def _contract_request_list(data, key):
    if hasattr(data, "getlist"):
        return [str(value or "") for value in data.getlist(key)]
    value = data.get(key, [])
    if isinstance(value, (list, tuple)):
        return [str(item or "") for item in value]
    return [str(value or "")]


def _format_contract_stage_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%d.%m.%Y")


def _parse_contract_form_date(raw_value):
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _contract_stage_enabled_value(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "off", "no", "нет"}


def _normalize_preliminary_report_term_unit(value):
    raw = str(value or "").strip()
    valid_units = {choice[0] for choice in ContractProjectRegistration.PreliminaryReportTermUnit.choices}
    if raw in valid_units:
        return raw
    return ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value


def _normalize_source_data_term_unit(value):
    raw = str(value or "").strip()
    valid_units = {choice[0] for choice in ContractProjectRegistration.SourceDataTermUnit.choices}
    if raw in valid_units:
        return raw
    return ContractProjectRegistration.SourceDataTermUnit.WEEKS.value


def _normalize_final_report_term_unit(value):
    raw = str(value or "").strip()
    valid_units = {choice[0] for choice in ContractProjectRegistration.FinalReportTermUnit.choices}
    if raw in valid_units:
        return raw
    return ContractProjectRegistration.FinalReportTermUnit.WEEKS.value


def _default_contract_evaluation_date(today=None):
    today = today or timezone.now().date()
    if today < date_type(today.year, 7, 1):
        return date_type(today.year, 1, 1)
    return date_type(today.year, 6, 1)


def _contract_payload_bool(value):
    if value is True:
        return True
    raw = str(value or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _contract_is_dsc_payload_item(item, product=None):
    if not isinstance(item, dict):
        return False
    if item.get("is_system_dsc") is True:
        return True
    return is_system_dsc_code(item.get("code"))


def _contract_system_dsc_payload(product):
    if product is None:
        return None
    section = ensure_system_dsc_section(product)
    if section is None:
        return None
    return {
        "service_name": section.name_ru or SYSTEM_DSC_SECTION_DEFAULTS["name_ru"],
        "code": section.code or SYSTEM_DSC_SECTION_CODE,
    }


GROUP_ALL_VALUE = "__all__"


class _ContractFileInput(forms.ClearableFileInput):
    initial_text = "Текущий файл"
    input_text = "Загрузить другой"
    clear_checkbox_label = "Удалить"
    template_name = "contracts_app/widgets/clearable_file_input.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        cloud_url = ctx["widget"].get("attrs", {}).get("cloud_current_url", "")
        cloud_name = ctx["widget"].get("attrs", {}).get("cloud_current_name", "")
        if not ctx["widget"].get("is_initial") and cloud_url:
            ctx["widget"]["is_initial"] = True
            ctx["widget"]["value"] = SimpleNamespace(url=cloud_url)
            ctx["widget"]["file_basename"] = cloud_name or ""
        if ctx["widget"].get("is_initial") and value and hasattr(value, "name"):
            import os
            ctx["widget"]["file_basename"] = os.path.basename(value.name)
        return ctx


class ContractProposalRegistrationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        parts = [obj.short_uid or ""]
        type_label = getattr(obj, "type_short_display", "") or ""
        if type_label:
            parts.append(type_label)
        if obj.name:
            parts.append(obj.name)
        return " ".join(part for part in parts if part).strip() or str(obj)


def _next_contract_project_number():
    current_max = ContractProjectRegistration.objects.aggregate(max_number=Max("number")).get("max_number")
    if current_max is None:
        return 3333
    return 9999 if current_max >= 9999 else current_max + 1


class ContractProjectRegistrationForm(BootstrapMixin, forms.ModelForm):
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
    proposal_registration = ContractProposalRegistrationChoiceField(
        label="ТКП ID",
        queryset=ProposalRegistration.objects.none(),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "contracts-proposal-registration-select",
            }
        ),
    )
    group_member = forms.ModelChoiceField(
        label="Группа",
        queryset=GroupMember.objects.none(),
        required=True,
        widget=forms.Select(attrs={"id": "registration-group-select"}),
    )
    sub_number = forms.IntegerField(
        label="№",
        required=False,
        min_value=0,
        max_value=9,
        initial=0,
        widget=forms.NumberInput(
            attrs={
                "id": "contracts-sub-number-input",
                "class": "form-control",
                "min": 0,
                "max": 9,
                "step": 1,
                "autocomplete": "off",
            }
        ),
    )
    contract_number = forms.CharField(
        label="Номер договора",
        required=False,
        widget=forms.TextInput(
            attrs={
                "id": "contracts-contract-number-input",
                "class": "form-control",
                "autocomplete": "off",
            }
        ),
    )
    contract_date = forms.DateField(
        label="Дата договора",
        required=False,
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={
                "type": "text",
                "class": "form-control js-date",
                "autocomplete": "off",
            },
        ),
        input_formats=DATE_INPUT_FORMATS,
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "reg-country-select"}),
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
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        required=False,
        widget=forms.Select(attrs={"id": "reg-region-select"}),
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
    asset_owner_matches_customer = forms.BooleanField(
        label="Совпадает с Заказчиком",
        required=False,
        initial=True,
    )
    proposal_project_name = forms.CharField(
        label="Наименование проекта",
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
    evaluation_date = forms.DateField(
        label="Дата оценки",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    source_data_term = forms.DecimalField(
        label="Исходные данные",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1"}),
    )
    source_data_term_unit = forms.ChoiceField(
        label="Единица срока предоставления исходных данных",
        required=False,
        choices=ContractProjectRegistration.SourceDataTermUnit.choices,
        initial=ContractProjectRegistration.SourceDataTermUnit.WEEKS,
    )
    source_data_date = forms.DateField(
        label="Дата предоставления данных",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    service_term_months = forms.DecimalField(
        label="Предварительный отчёт",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1"}),
    )
    preliminary_report_term_unit = forms.ChoiceField(
        label="Единица срока подготовки Предварительного отчёта",
        required=False,
        choices=ContractProjectRegistration.PreliminaryReportTermUnit.choices,
        initial=ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS,
    )
    preliminary_report_date = forms.DateField(
        label="Дата Предварительного отчёта",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
    )
    final_report_term_weeks = forms.DecimalField(
        label="Итоговый отчёт",
        required=False,
        min_value=0,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1"}),
    )
    final_report_term_unit = forms.ChoiceField(
        label="Единица срока подготовки Итогового отчёта",
        required=False,
        choices=ContractProjectRegistration.FinalReportTermUnit.choices,
        initial=ContractProjectRegistration.FinalReportTermUnit.WEEKS,
    )
    final_report_date = forms.DateField(
        label="Дата Итогового отчёта",
        required=False,
        widget=_date_input_widget(),
        input_formats=DATE_INPUT_FORMATS,
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
    payment_schedule_common = forms.BooleanField(
        label="Общий для всех этапов",
        required=False,
        initial=True,
    )
    project_manager = forms.ChoiceField(
        label="Руководитель проекта",
        required=False,
        choices=(),
        widget=forms.Select(),
    )
    type_ids = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ContractProjectRegistration
        fields = [
            "number", "proposal_registration", "sub_number", "contract_number", "contract_date",
            "group_member", "agreement_type", "name",
            "status", "year",
            "country", "customer", "identifier", "registration_number", "registration_region",
            "registration_date",
            "asset_owner", "asset_owner_country", "asset_owner_region", "asset_owner_identifier",
            "asset_owner_registration_number", "asset_owner_registration_date", "asset_owner_matches_customer",
            "proposal_project_name", "purpose",
            "service_composition", "service_composition_customer_tz", "service_composition_mode",
            "project_manager",
            "evaluation_date", "source_data_term", "source_data_term_unit", "source_data_date",
            "service_term_months", "preliminary_report_term_unit", "preliminary_report_date",
            "final_report_term_weeks", "final_report_term_unit", "final_report_date",
            "advance_percent", "advance_term_days", "preliminary_report_percent",
            "preliminary_report_term_days", "final_report_percent", "final_report_term_days",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
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
        self.fields["project_manager"].widget = forms.HiddenInput()
        if not self.data:
            self.initial["project_manager"] = current_manager
            self.fields["project_manager"].initial = current_manager

        current_region = (
            self.data.get("registration_region")
            if self.data
            else getattr(self.instance, "registration_region", "")
        )
        current_country_id = (
            self.data.get("country")
            if self.data
            else getattr(self.instance, "country_id", "")
        )
        current_registration_date = (
            self.data.get("registration_date")
            if self.data
            else getattr(self.instance, "registration_date", None)
        )
        region_choices = [("", "---------")]
        region_choices.extend(
            (name, name)
            for name in _project_region_choices_for_country(
                current_country_id,
                current_region,
                as_of=current_registration_date,
            )
        )
        self.fields["registration_region"].choices = region_choices

        asset_owner_country_id = (
            self.data.get("asset_owner_country")
            if self.data
            else getattr(self.instance, "asset_owner_country_id", None)
        )
        asset_owner_region = (
            self.data.get("asset_owner_region")
            if self.data
            else getattr(self.instance, "asset_owner_region", "")
        )
        asset_owner_registration_date = (
            _parse_contract_form_date(self.data.get("asset_owner_registration_date"))
            if self.data
            else getattr(self.instance, "asset_owner_registration_date", None)
        )
        asset_owner_region_choices = [("", "---------")]
        asset_owner_region_choices.extend(
            (name, name)
            for name in _project_region_choices_for_country(
                asset_owner_country_id,
                asset_owner_region,
                as_of=asset_owner_registration_date,
            )
        )
        self.fields["asset_owner_region"].choices = asset_owner_region_choices

        proposal_product_prefetch = Prefetch(
            "product_links",
            queryset=ProposalRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
        )
        self.fields["proposal_registration"].queryset = (
            ProposalRegistration.objects
            .prefetch_related(proposal_product_prefetch)
            .order_by("position", "id")
        )
        self.fields["proposal_registration"].empty_label = "— Не выбрано —"
        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and (self.instance.country_id or self.instance.asset_owner_country_id):
            country_ids = [
                value
                for value in [self.instance.country_id, self.instance.asset_owner_country_id]
                if value
            ]
            country_qs = (
                country_qs | OKSMCountry.objects.filter(pk__in=country_ids)
            ).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["asset_owner_country"].queryset = country_qs
        self.fields["asset_owner_country"].label_from_instance = lambda obj: obj.short_name
        if self.instance and self.instance.pk and self.instance.identifier:
            self.fields["identifier"].initial = self.instance.identifier
        if self.instance and self.instance.pk and self.instance.asset_owner_identifier:
            self.fields["asset_owner_identifier"].initial = self.instance.asset_owner_identifier

        self._bootstrapify()
        self.fields["asset_owner_matches_customer"].widget.attrs["class"] = "form-check-input"
        if not self.instance.pk and "asset_owner_matches_customer" not in self.data:
            self.fields["asset_owner_matches_customer"].initial = True
        if not self.instance.pk and "sub_number" not in self.data:
            self.fields["sub_number"].initial = 0
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
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year
        if not self.instance.pk and "number" not in self.data:
            self.fields["number"].initial = _next_contract_project_number()
        if not self.instance.pk and not self.data:
            self.initial.setdefault("advance_percent", 40)
            self.initial.setdefault("advance_term_days", 10)
            self.initial.setdefault("preliminary_report_percent", 40)
            self.initial.setdefault("preliminary_report_term_days", 7)
            self.initial.setdefault("final_report_percent", 20)
            self.initial.setdefault("final_report_term_days", 15)

        self.payment_schedule_common_enabled = self._is_payment_schedule_common_enabled()
        self.fields["payment_schedule_common"].widget.attrs["class"] = "form-check-input"
        self.fields["payment_schedule_common"].initial = self.payment_schedule_common_enabled
        if not self.payment_schedule_common_enabled:
            for field_name in (
                "advance_percent",
                "advance_term_days",
                "preliminary_report_percent",
                "preliminary_report_term_days",
                "final_report_percent",
                "final_report_term_days",
            ):
                self.fields[field_name].widget.attrs["disabled"] = True
        try:
            self.initial["final_report_percent"] = self._calculate_final_report_percent(
                advance_percent=self._payment_field_initial_value(
                    "advance_percent",
                    fallback=getattr(self.instance, "advance_percent", None),
                ),
                preliminary_report_percent=self._payment_field_initial_value(
                    "preliminary_report_percent",
                    fallback=getattr(self.instance, "preliminary_report_percent", None),
                ),
            )
        except (forms.ValidationError, TypeError, ValueError):
            self.initial["final_report_percent"] = self.initial.get(
                "final_report_percent",
                getattr(self.instance, "final_report_percent", None),
            )

        members_qs = list(GroupMember.objects.only("id", "country_order_number", "country_alpha2"))
        self.group_order_map = {
            str(member.pk): int(member.country_order_number or 0) for member in members_qs
        }
        self.group_alpha2_map = {
            str(member.pk): (member.country_alpha2 or "").strip().upper() for member in members_qs
        }
        self.proposal_sub_number_map = {
            str(proposal.pk): int(proposal.sub_number or 0)
            for proposal in self.fields["proposal_registration"].queryset
        }

        self.stage_rows = self._build_contract_stage_rows()

    def _payment_field_initial_value(self, field_name, *, fallback=None):
        if not self.is_bound:
            return self.initial.get(field_name, fallback)
        if not self.payment_schedule_common_enabled:
            values = _contract_request_list(self.data, field_name)
            if values:
                return values[-1] or fallback
        return self.data.get(field_name, fallback)

    def _is_payment_schedule_common_enabled(self):
        if self.is_bound:
            if "payment_schedule_common" not in self.data:
                return True
            enabled = self.fields["payment_schedule_common"].widget.value_from_datadict(
                self.data,
                self.files,
                "payment_schedule_common",
            )
            if enabled:
                type_ids = _contract_request_list(self.data, "type_id")
                preliminary_flags = _contract_request_list(self.data, "service_term_months_enabled")
                row_count = max(len(type_ids), len(preliminary_flags), 1)
                preliminary_states = [
                    _contract_stage_enabled_value(
                        preliminary_flags[index] if index < len(preliminary_flags) else None
                    )
                    for index in range(row_count)
                ]
                if row_count > 1 and any(state != preliminary_states[0] for state in preliminary_states):
                    return False
            return enabled
        stored_stages = list(getattr(self.instance, "stage_payloads_json", None) or [])
        if any(isinstance(payload, dict) and payload.get("payment_schedule_common") is False for payload in stored_stages):
            return False
        return True

    @staticmethod
    def _contract_stage_display_value(value, default=""):
        if value in (None, ""):
            value = default
        return "" if value is None else str(value)

    def _empty_contract_stage_row(self, rank=1, product_id="", product_short_label=""):
        return {
            "rank": rank,
            "product_id": product_id,
            "product_short_label": product_short_label,
            "service_sections_payload": "[]",
            "service_sections_editor_state": "[]",
            "service_customer_tz_editor_state": "",
            "service_composition_customer_tz": "",
            "service_composition_mode": "sections",
            "service_composition": "",
            "evaluation_date": _format_contract_stage_date(
                self.initial.get("evaluation_date") or _default_contract_evaluation_date()
            ),
            "evaluation_date_enabled": True,
            "source_data_term_enabled": True,
            "source_data_term": "",
            "source_data_date_enabled": True,
            "source_data_term_unit": ContractProjectRegistration.SourceDataTermUnit.WEEKS.value,
            "source_data_date": "",
            "service_term_months_enabled": True,
            "service_term_months": "",
            "preliminary_report_term_unit": ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value,
            "preliminary_report_date_enabled": True,
            "preliminary_report_date": "",
            "final_report_term_weeks": "",
            "final_report_term_unit": ContractProjectRegistration.FinalReportTermUnit.WEEKS.value,
            "final_report_date_enabled": True,
            "final_report_date": "",
            "next_stage_delay_days": "",
            "advance_percent": str(self.fields["advance_percent"].initial or ""),
            "advance_term_days": str(self.fields["advance_term_days"].initial or ""),
            "preliminary_report_percent": str(self.fields["preliminary_report_percent"].initial or ""),
            "preliminary_report_term_days": str(self.fields["preliminary_report_term_days"].initial or ""),
            "final_report_percent": str(self.initial.get("final_report_percent") or ""),
            "final_report_term_days": str(self.fields["final_report_term_days"].initial or ""),
        }

    def _product_typical_terms(self, product):
        if product is None:
            return {}
        term = (
            TypicalServiceTerm.objects
            .filter(product=product)
            .order_by("position", "id")
            .first()
        )
        if term is None:
            return {}
        return {
            "source_data_term": format(term.source_data_weeks, ".1f"),
            "source_data_term_unit": _normalize_source_data_term_unit(term.source_data_term_unit),
            "service_term_months": format(term.preliminary_report_months, ".1f"),
            "preliminary_report_term_unit": _normalize_preliminary_report_term_unit(
                term.preliminary_report_term_unit
            ),
            "final_report_term_weeks": format(term.final_report_weeks, ".1f"),
            "final_report_term_unit": _normalize_final_report_term_unit(term.final_report_term_unit),
        }

    def _contract_stage_row_from_payload(self, payload, *, rank, product_id, product, fallback=None, payment_fallback=None):
        payload = payload if isinstance(payload, dict) else {}
        fallback = fallback or {}
        payment_fallback = payment_fallback or {}
        terms = self._product_typical_terms(product)
        evaluation_date_enabled = _contract_stage_enabled_value(
            payload.get("evaluation_date_enabled", fallback.get("evaluation_date_enabled"))
        )
        source_data_term_enabled = _contract_stage_enabled_value(
            payload.get("source_data_term_enabled", fallback.get("source_data_term_enabled"))
        )
        source_data_date_enabled = _contract_stage_enabled_value(
            payload.get("source_data_date_enabled", fallback.get("source_data_date_enabled"))
        )
        service_term_months_enabled = _contract_stage_enabled_value(
            payload.get("service_term_months_enabled", fallback.get("service_term_months_enabled"))
        )
        preliminary_report_date_enabled = _contract_stage_enabled_value(
            payload.get("preliminary_report_date_enabled", fallback.get("preliminary_report_date_enabled"))
        )
        final_report_date_enabled = _contract_stage_enabled_value(
            payload.get("final_report_date_enabled", fallback.get("final_report_date_enabled"))
        )
        return {
            "rank": rank,
            "product_id": product_id,
            "product_short_label": (getattr(product, "short_name", "") or "").strip(),
            "service_sections_payload": json.dumps(
                payload.get("service_sections_json")
                if isinstance(payload.get("service_sections_json"), list)
                else fallback.get("service_sections_json") or [],
                ensure_ascii=False,
            ),
            "service_sections_editor_state": json.dumps(
                payload.get("service_sections_editor_state")
                if isinstance(payload.get("service_sections_editor_state"), list)
                else fallback.get("service_sections_editor_state") or [],
                ensure_ascii=False,
            ),
            "service_customer_tz_editor_state": json.dumps(
                payload.get("service_customer_tz_editor_state")
                if isinstance(payload.get("service_customer_tz_editor_state"), dict)
                else fallback.get("service_customer_tz_editor_state") or {},
                ensure_ascii=False,
            )
            if (
                payload.get("service_customer_tz_editor_state")
                or fallback.get("service_customer_tz_editor_state")
            )
            else "",
            "service_composition_customer_tz": str(
                payload.get("service_composition_customer_tz")
                or fallback.get("service_composition_customer_tz")
                or ""
            ),
            "service_composition_mode": str(
                payload.get("service_composition_mode")
                or fallback.get("service_composition_mode")
                or "sections"
            )
            or "sections",
            "service_composition": str(
                payload.get("service_composition")
                or fallback.get("service_composition")
                or ""
            ),
            "evaluation_date_enabled": evaluation_date_enabled,
            "evaluation_date": str(
                payload.get("evaluation_date") or fallback.get("evaluation_date") or ""
            ) if evaluation_date_enabled else "",
            "source_data_term_enabled": source_data_term_enabled,
            "source_data_term": str(
                payload.get("source_data_term")
                or fallback.get("source_data_term")
                or (terms.get("source_data_term") if source_data_term_enabled else "")
                or ""
            ),
            "source_data_date_enabled": source_data_date_enabled,
            "source_data_term_unit": _normalize_source_data_term_unit(
                payload.get("source_data_term_unit")
                or fallback.get("source_data_term_unit")
                or terms.get("source_data_term_unit")
            ),
            "source_data_date": str(payload.get("source_data_date") or fallback.get("source_data_date") or ""),
            "service_term_months_enabled": service_term_months_enabled,
            "service_term_months": str(
                payload.get("service_term_months")
                or fallback.get("service_term_months")
                or (terms.get("service_term_months") if service_term_months_enabled else "")
                or ""
            ),
            "preliminary_report_term_unit": _normalize_preliminary_report_term_unit(
                payload.get("preliminary_report_term_unit")
                or fallback.get("preliminary_report_term_unit")
                or terms.get("preliminary_report_term_unit")
            ),
            "preliminary_report_date_enabled": preliminary_report_date_enabled,
            "preliminary_report_date": str(
                payload.get("preliminary_report_date") or fallback.get("preliminary_report_date") or ""
            ),
            "final_report_term_weeks": str(
                payload.get("final_report_term_weeks")
                or fallback.get("final_report_term_weeks")
                or terms.get("final_report_term_weeks")
                or ""
            ),
            "final_report_term_unit": _normalize_final_report_term_unit(
                payload.get("final_report_term_unit")
                or fallback.get("final_report_term_unit")
                or terms.get("final_report_term_unit")
            ),
            "final_report_date_enabled": final_report_date_enabled,
            "final_report_date": str(
                payload.get("final_report_date") or fallback.get("final_report_date") or ""
            ) if final_report_date_enabled else "",
            "next_stage_delay_days": str(payload.get("next_stage_delay_days") or ""),
            "advance_percent": self._contract_stage_display_value(
                payload.get("advance_percent"),
                payment_fallback.get("advance_percent"),
            ),
            "advance_term_days": self._contract_stage_display_value(
                payload.get("advance_term_days"),
                payment_fallback.get("advance_term_days"),
            ),
            "preliminary_report_percent": self._contract_stage_display_value(
                payload.get("preliminary_report_percent"),
                payment_fallback.get("preliminary_report_percent"),
            ),
            "preliminary_report_term_days": self._contract_stage_display_value(
                payload.get("preliminary_report_term_days"),
                payment_fallback.get("preliminary_report_term_days"),
            ),
            "final_report_percent": self._contract_stage_display_value(
                payload.get("final_report_percent"),
                payment_fallback.get("final_report_percent"),
            ),
            "final_report_term_days": self._contract_stage_display_value(
                payload.get("final_report_term_days"),
                payment_fallback.get("final_report_term_days"),
            ),
        }

    def _build_contract_stage_rows_from_bound_data(self):
        field_names = (
            "service_sections_payload",
            "service_sections_editor_state",
            "service_customer_tz_editor_state",
            "service_composition_customer_tz",
            "service_composition_mode",
            "service_composition",
            "evaluation_date",
            "evaluation_date_enabled",
            "source_data_term_enabled",
            "source_data_term",
            "source_data_term_unit",
            "source_data_date_enabled",
            "source_data_date",
            "service_term_months_enabled",
            "service_term_months",
            "preliminary_report_term_unit",
            "preliminary_report_date_enabled",
            "preliminary_report_date",
            "final_report_term_weeks",
            "final_report_term_unit",
            "final_report_date_enabled",
            "final_report_date",
            "next_stage_delay_days",
            "advance_percent",
            "advance_term_days",
            "preliminary_report_percent",
            "preliminary_report_term_days",
            "final_report_percent",
            "final_report_term_days",
        )
        rows_map = {name: _contract_request_list(self.data, name) for name in field_names}
        type_ids = _contract_request_list(self.data, "type_id")
        product_ids = {
            int(raw)
            for raw in type_ids
            if str(raw or "").strip().isdigit()
        }
        product_map = {
            str(product.pk): product
            for product in Product.objects.filter(pk__in=product_ids)
        }
        row_count = max(len(type_ids), max((len(values) for values in rows_map.values()), default=0), 1)
        rows = []
        for index in range(row_count):
            product_id = (type_ids[index] if index < len(type_ids) else "").strip()
            product = product_map.get(product_id)
            row = {
                "rank": len(rows) + 1,
                "product_id": product_id,
                "product_short_label": (getattr(product, "short_name", "") or "").strip(),
                "service_sections_payload": (
                    rows_map["service_sections_payload"][index]
                    if index < len(rows_map["service_sections_payload"])
                    else "[]"
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
                    rows_map["service_composition"][index]
                    if index < len(rows_map["service_composition"])
                    else ""
                ),
                "evaluation_date": (
                    rows_map["evaluation_date"][index] if index < len(rows_map["evaluation_date"]) else ""
                ).strip(),
                "evaluation_date_enabled": _contract_stage_enabled_value(
                    rows_map["evaluation_date_enabled"][index]
                    if index < len(rows_map["evaluation_date_enabled"])
                    else None
                ),
                "source_data_term_enabled": _contract_stage_enabled_value(
                    rows_map["source_data_term_enabled"][index]
                    if index < len(rows_map["source_data_term_enabled"])
                    else None
                ),
                "source_data_term": (
                    rows_map["source_data_term"][index] if index < len(rows_map["source_data_term"]) else ""
                ).strip(),
                "source_data_term_unit": _normalize_source_data_term_unit(
                    rows_map["source_data_term_unit"][index]
                    if index < len(rows_map["source_data_term_unit"])
                    else ""
                ),
                "source_data_date_enabled": _contract_stage_enabled_value(
                    rows_map["source_data_date_enabled"][index]
                    if index < len(rows_map["source_data_date_enabled"])
                    else None
                ),
                "source_data_date": (
                    rows_map["source_data_date"][index] if index < len(rows_map["source_data_date"]) else ""
                ).strip(),
                "service_term_months_enabled": _contract_stage_enabled_value(
                    rows_map["service_term_months_enabled"][index]
                    if index < len(rows_map["service_term_months_enabled"])
                    else None
                ),
                "service_term_months": (
                    rows_map["service_term_months"][index] if index < len(rows_map["service_term_months"]) else ""
                ).strip(),
                "preliminary_report_term_unit": _normalize_preliminary_report_term_unit(
                    rows_map["preliminary_report_term_unit"][index]
                    if index < len(rows_map["preliminary_report_term_unit"])
                    else ""
                ),
                "preliminary_report_date_enabled": _contract_stage_enabled_value(
                    rows_map["preliminary_report_date_enabled"][index]
                    if index < len(rows_map["preliminary_report_date_enabled"])
                    else None
                ),
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
                "final_report_term_unit": _normalize_final_report_term_unit(
                    rows_map["final_report_term_unit"][index]
                    if index < len(rows_map["final_report_term_unit"])
                    else ""
                ),
                "final_report_date_enabled": _contract_stage_enabled_value(
                    rows_map["final_report_date_enabled"][index]
                    if index < len(rows_map["final_report_date_enabled"])
                    else None
                ),
                "final_report_date": (
                    rows_map["final_report_date"][index] if index < len(rows_map["final_report_date"]) else ""
                ).strip(),
                "next_stage_delay_days": (
                    rows_map["next_stage_delay_days"][index]
                    if index < len(rows_map["next_stage_delay_days"])
                    else ""
                ).strip(),
                "advance_percent": (
                    rows_map["advance_percent"][index] if index < len(rows_map["advance_percent"]) else ""
                ).strip(),
                "advance_term_days": (
                    rows_map["advance_term_days"][index] if index < len(rows_map["advance_term_days"]) else ""
                ).strip(),
                "preliminary_report_percent": (
                    rows_map["preliminary_report_percent"][index]
                    if index < len(rows_map["preliminary_report_percent"])
                    else ""
                ).strip(),
                "preliminary_report_term_days": (
                    rows_map["preliminary_report_term_days"][index]
                    if index < len(rows_map["preliminary_report_term_days"])
                    else ""
                ).strip(),
                "final_report_percent": (
                    rows_map["final_report_percent"][index] if index < len(rows_map["final_report_percent"]) else ""
                ).strip(),
                "final_report_term_days": (
                    rows_map["final_report_term_days"][index]
                    if index < len(rows_map["final_report_term_days"])
                    else ""
                ).strip(),
            }
            has_data = any(
                str(row.get(key) or "").strip()
                for key in row
                if key not in {
                    "rank",
                    "product_id",
                    "evaluation_date_enabled",
                    "source_data_term_enabled",
                    "source_data_term_unit",
                    "source_data_date_enabled",
                    "service_term_months_enabled",
                    "preliminary_report_term_unit",
                    "preliminary_report_date_enabled",
                    "final_report_term_unit",
                    "final_report_date_enabled",
                }
            )
            if product_id or has_data or row_count == 1:
                rows.append(row)
        return rows or [self._empty_contract_stage_row()]

    def _build_contract_stage_rows_from_instance(self):
        instance = self.instance
        if not instance or not instance.pk:
            return [self._empty_contract_stage_row()]

        ordered_products = list(instance.ordered_products())
        stored_stages = list(instance.stage_payloads_json or [])
        instance_fallback = {
            "service_sections_json": instance.service_sections_json or [],
            "service_sections_editor_state": instance.service_sections_editor_state or [],
            "service_customer_tz_editor_state": instance.service_customer_tz_editor_state or {},
            "service_composition_customer_tz": instance.service_composition_customer_tz or "",
            "service_composition_mode": instance.service_composition_mode or "sections",
            "service_composition": instance.service_composition or "",
            "evaluation_date_enabled": True,
            "evaluation_date": _format_contract_stage_date(instance.evaluation_date),
            "source_data_term_enabled": True,
            "source_data_term": (
                "" if instance.source_data_term is None else format(instance.source_data_term, ".1f")
            ),
            "source_data_term_unit": _normalize_source_data_term_unit(instance.source_data_term_unit),
            "source_data_date_enabled": True,
            "source_data_date": _format_contract_stage_date(instance.source_data_date),
            "service_term_months_enabled": True,
            "service_term_months": (
                "" if instance.service_term_months is None else format(instance.service_term_months, ".1f")
            ),
            "preliminary_report_term_unit": _normalize_preliminary_report_term_unit(
                instance.preliminary_report_term_unit
            ),
            "preliminary_report_date_enabled": True,
            "preliminary_report_date": _format_contract_stage_date(instance.preliminary_report_date),
            "final_report_term_weeks": (
                "" if instance.final_report_term_weeks is None else format(instance.final_report_term_weeks, ".1f")
            ),
            "final_report_term_unit": _normalize_final_report_term_unit(instance.final_report_term_unit),
            "final_report_date_enabled": True,
            "final_report_date": _format_contract_stage_date(instance.final_report_date),
        }
        payment_fallback = {
            "advance_percent": instance.advance_percent,
            "advance_term_days": instance.advance_term_days,
            "preliminary_report_percent": instance.preliminary_report_percent,
            "preliminary_report_term_days": instance.preliminary_report_term_days,
            "final_report_percent": instance.final_report_percent,
            "final_report_term_days": instance.final_report_term_days,
        }
        if stored_stages:
            rows = []
            for index, payload in enumerate(stored_stages, start=1):
                product_id = str(payload.get("product_id") or "")
                product = next(
                    (item for item in ordered_products if str(item.pk) == product_id),
                    ordered_products[index - 1] if index - 1 < len(ordered_products) else None,
                )
                rows.append(
                    self._contract_stage_row_from_payload(
                        payload,
                        rank=index,
                        product_id=product_id or str(getattr(product, "pk", "") or ""),
                        product=product,
                        fallback=instance_fallback if index == 1 else None,
                        payment_fallback=payment_fallback,
                    )
                )
            if rows:
                return rows

        if not ordered_products:
            return [
                self._contract_stage_row_from_payload(
                    {},
                    rank=1,
                    product_id="",
                    product=None,
                    fallback=instance_fallback,
                    payment_fallback=payment_fallback,
                )
            ]

        rows = []
        for index, product in enumerate(ordered_products, start=1):
            rows.append(
                self._contract_stage_row_from_payload(
                    {},
                    rank=index,
                    product_id=str(product.pk),
                    product=product,
                    fallback=instance_fallback if index == 1 else None,
                    payment_fallback=payment_fallback,
                )
            )
        return rows

    def _build_contract_stage_rows(self):
        if self.is_bound:
            return self._build_contract_stage_rows_from_bound_data()
        rows = self._build_contract_stage_rows_from_instance()
        return rows or [self._empty_contract_stage_row()]

    def _parse_contract_stage_date(self, value, *, row_index, field_label):
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = _parse_contract_form_date(raw)
        if parsed is None:
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")
        return parsed

    def _parse_contract_stage_decimal(self, value, *, row_index, field_label):
        raw = str(value or "").strip().replace(",", ".")
        if not raw:
            return None
        try:
            parsed = Decimal(raw)
        except (TypeError, ValueError, ArithmeticError):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")
        if parsed < 0:
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть не меньше 0.")
        return parsed

    def _parse_contract_stage_signed_integer(self, value, *, row_index, field_label, default=0):
        raw = str(value or "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")

    def _parse_contract_stage_integer(self, value, *, row_index, field_label):
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» заполнено некорректно.")
        if parsed < 0:
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть не меньше 0.")
        return parsed

    def _parse_contract_stage_percent(self, value, *, row_index, field_label):
        parsed = self._parse_contract_stage_decimal(value, row_index=row_index, field_label=field_label)
        if parsed is not None and (parsed < 0 or parsed > 100):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть в диапазоне от 0% до 100%.")
        return parsed

    def _parse_contract_stage_preliminary_report_term_unit(self, value, *, row_index):
        raw = str(value or "").strip()
        if not raw:
            return ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value
        valid_units = {choice[0] for choice in ContractProjectRegistration.PreliminaryReportTermUnit.choices}
        if raw not in valid_units:
            raise forms.ValidationError(
                f"Этап {row_index}: поле «Единица срока подготовки Предварительного отчёта» заполнено некорректно."
            )
        return raw

    def _parse_contract_stage_preliminary_report_term(self, value, *, unit, row_index, field_label):
        parsed = self._parse_contract_stage_decimal(value, row_index=row_index, field_label=field_label)
        if (
            unit == ContractProjectRegistration.PreliminaryReportTermUnit.DAYS.value
            and parsed is not None
            and parsed != parsed.to_integral_value()
        ):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть целым числом.")
        return parsed.to_integral_value() if unit == ContractProjectRegistration.PreliminaryReportTermUnit.DAYS.value and parsed is not None else parsed

    def _parse_contract_stage_source_data_term_unit(self, value, *, row_index):
        raw = str(value or "").strip()
        if not raw:
            return ContractProjectRegistration.SourceDataTermUnit.WEEKS.value
        valid_units = {choice[0] for choice in ContractProjectRegistration.SourceDataTermUnit.choices}
        if raw not in valid_units:
            raise forms.ValidationError(
                f"Этап {row_index}: поле «Единица срока предоставления исходных данных» заполнено некорректно."
            )
        return raw

    def _parse_contract_stage_source_data_term(self, value, *, unit, row_index, field_label):
        parsed = self._parse_contract_stage_decimal(value, row_index=row_index, field_label=field_label)
        if (
            unit == ContractProjectRegistration.SourceDataTermUnit.DAYS.value
            and parsed is not None
            and parsed != parsed.to_integral_value()
        ):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть целым числом.")
        return parsed.to_integral_value() if unit == ContractProjectRegistration.SourceDataTermUnit.DAYS.value and parsed is not None else parsed

    def _parse_contract_stage_final_report_term_unit(self, value, *, row_index):
        raw = str(value or "").strip()
        if not raw:
            return ContractProjectRegistration.FinalReportTermUnit.WEEKS.value
        valid_units = {choice[0] for choice in ContractProjectRegistration.FinalReportTermUnit.choices}
        if raw not in valid_units:
            raise forms.ValidationError(
                f"Этап {row_index}: поле «Единица срока подготовки Итогового отчёта» заполнено некорректно."
            )
        return raw

    def _parse_contract_stage_final_report_term(self, value, *, unit, row_index, field_label):
        parsed = self._parse_contract_stage_decimal(value, row_index=row_index, field_label=field_label)
        if (
            unit == ContractProjectRegistration.FinalReportTermUnit.DAYS.value
            and parsed is not None
            and parsed != parsed.to_integral_value()
        ):
            raise forms.ValidationError(f"Этап {row_index}: поле «{field_label}» должно быть целым числом.")
        return parsed.to_integral_value() if unit == ContractProjectRegistration.FinalReportTermUnit.DAYS.value and parsed is not None else parsed

    @staticmethod
    def _serialize_contract_payload_decimal(value):
        if value is None:
            return ""
        return str(value)

    def _load_contract_stage_json(self, raw, *, row_index, field_label, expected_type, default):
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

    def _prepend_system_dsc_service_section(self, items, product):
        dsc_payload = _contract_system_dsc_payload(product)
        filtered = []
        seen = set()
        for item in items:
            if _contract_is_dsc_payload_item(item, product):
                continue
            key = (str(item.get("code") or "").strip() or str(item.get("service_name") or "").strip()).lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            filtered.append(item)
        return ([dsc_payload] if dsc_payload else []) + filtered

    def _normalize_editor_state_for_sections(self, items, product, service_sections):
        dsc_payload = _contract_system_dsc_payload(product)
        stored_by_key = {}
        dsc_saved = {}
        for item in items:
            if _contract_is_dsc_payload_item(item, product):
                dsc_saved = item
                continue
            key = str(item.get("code") or item.get("service_name") or "").strip()
            if key and key not in stored_by_key:
                stored_by_key[key] = item

        normalized = []
        if dsc_payload:
            normalized.append(
                {
                    "code": dsc_payload["code"],
                    "service_name": dsc_payload["service_name"],
                    "html": str(dsc_saved.get("html") or "").strip(),
                    "plain_text": str(dsc_saved.get("plain_text") or "").strip(),
                }
            )

        for section in service_sections:
            if _contract_is_dsc_payload_item(section, product):
                continue
            key = str(section.get("code") or section.get("service_name") or "").strip()
            saved = stored_by_key.get(key) or stored_by_key.get(str(section.get("service_name") or "").strip()) or {}
            normalized.append(
                {
                    "code": str(section.get("code") or "").strip(),
                    "service_name": str(section.get("service_name") or "").strip(),
                    "html": str(saved.get("html") or "").strip(),
                    "plain_text": str(saved.get("plain_text") or "").strip(),
                }
            )
        return normalized

    def _normalize_contract_stage_service_sections(self, raw, *, row_index, product=None):
        items = self._load_contract_stage_json(
            raw,
            row_index=row_index,
            field_label="Состав услуг / техническое задание",
            expected_type=list,
            default=[],
        )
        sections_by_name = {}
        if product is not None:
            ensure_system_dsc_section(product)
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
                    "code": code or sections_by_name.get(service_name, ""),
                    **(
                        {"merge_without_code": True}
                        if (
                            not _contract_is_dsc_payload_item(item, product)
                            and _contract_payload_bool(item.get("merge_without_code"))
                        )
                        else {}
                    ),
                }
            )
        return self._prepend_system_dsc_service_section(normalized, product)

    def _normalize_contract_stage_editor_state(self, raw, *, row_index, product=None, service_sections=None):
        items = self._load_contract_stage_json(
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
        if product is not None and service_sections is not None:
            return self._normalize_editor_state_for_sections(normalized, product, service_sections)
        return normalized

    def _normalize_contract_stage_customer_tz_state(self, raw, *, row_index):
        value = self._load_contract_stage_json(
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

    def _collect_contract_stage_payloads(self):
        stage_payloads = []
        type_ids = getattr(self, "cleaned_type_ids", [])
        product_map = {
            product.pk: product
            for product in Product.objects.filter(pk__in=set(type_ids))
        }
        rows = self.stage_rows or []
        for index, product_id in enumerate(type_ids, start=1):
            row = rows[index - 1] if index - 1 < len(rows) else {}
            product = product_map.get(product_id)
            if product is not None:
                ensure_system_dsc_section(product)
            service_composition_mode = str(row.get("service_composition_mode") or "sections").strip() or "sections"
            if service_composition_mode not in {"sections", "customer_tz"}:
                service_composition_mode = "sections"
            service_composition_customer_tz = str(row.get("service_composition_customer_tz") or "").strip()
            source_data_term_enabled = _contract_stage_enabled_value(row.get("source_data_term_enabled"))
            evaluation_date_enabled = _contract_stage_enabled_value(row.get("evaluation_date_enabled"))
            source_data_date_enabled = _contract_stage_enabled_value(row.get("source_data_date_enabled"))
            service_term_months_enabled = _contract_stage_enabled_value(row.get("service_term_months_enabled"))
            preliminary_report_date_enabled = _contract_stage_enabled_value(
                row.get("preliminary_report_date_enabled")
            )
            final_report_date_enabled = _contract_stage_enabled_value(row.get("final_report_date_enabled"))
            if self.payment_schedule_common_enabled:
                advance_percent = self.cleaned_data.get("advance_percent")
                advance_term_days = self.cleaned_data.get("advance_term_days")
                preliminary_report_percent = self.cleaned_data.get("preliminary_report_percent")
                preliminary_report_term_days = self.cleaned_data.get("preliminary_report_term_days")
                final_report_term_days = self.cleaned_data.get("final_report_term_days")
            else:
                advance_percent = self._parse_contract_stage_percent(
                    row.get("advance_percent"),
                    row_index=index,
                    field_label="Размер предоплаты в процентах",
                )
                advance_term_days = self._parse_contract_stage_integer(
                    row.get("advance_term_days"),
                    row_index=index,
                    field_label="Срок предоплаты в календарных днях",
                )
                preliminary_report_percent = self._parse_contract_stage_percent(
                    row.get("preliminary_report_percent"),
                    row_index=index,
                    field_label="Размер оплаты Предварительного отчёта в процентах",
                )
                preliminary_report_term_days = self._parse_contract_stage_integer(
                    row.get("preliminary_report_term_days"),
                    row_index=index,
                    field_label="Срок оплаты Предварительного отчёта в календарных днях",
                )
                final_report_term_days = self._parse_contract_stage_integer(
                    row.get("final_report_term_days"),
                    row_index=index,
                    field_label="Срок оплаты Итогового отчёта в календарных днях",
                )
            if not service_term_months_enabled:
                preliminary_report_percent = Decimal("0")
                preliminary_report_term_days = 0
            final_report_percent = self._calculate_final_report_percent(
                advance_percent=advance_percent,
                preliminary_report_percent=preliminary_report_percent,
            )
            if final_report_percent < 0 or final_report_percent > 100:
                raise forms.ValidationError(
                    f"Этап {index}: рассчитанный размер оплаты Итогового отчёта должен быть в диапазоне от 0% до 100%."
                )
            source_data_term_unit = self._parse_contract_stage_source_data_term_unit(
                row.get("source_data_term_unit"),
                row_index=index,
            )
            source_data_term = (
                self._parse_contract_stage_source_data_term(
                    row.get("source_data_term"),
                    row_index=index,
                    field_label=self.fields["source_data_term"].label,
                    unit=source_data_term_unit,
                )
                if source_data_term_enabled
                else None
            )
            preliminary_report_term_unit = self._parse_contract_stage_preliminary_report_term_unit(
                row.get("preliminary_report_term_unit"),
                row_index=index,
            )
            service_term_months = (
                self._parse_contract_stage_preliminary_report_term(
                    row.get("service_term_months"),
                    row_index=index,
                    field_label=self.fields["service_term_months"].label,
                    unit=preliminary_report_term_unit,
                )
                if service_term_months_enabled
                else None
            )
            final_report_term_unit = self._parse_contract_stage_final_report_term_unit(
                row.get("final_report_term_unit"),
                row_index=index,
            )
            final_report_term_weeks = self._parse_contract_stage_final_report_term(
                row.get("final_report_term_weeks"),
                row_index=index,
                field_label=self.fields["final_report_term_weeks"].label,
                unit=final_report_term_unit,
            )
            service_sections_json = self._normalize_contract_stage_service_sections(
                row.get("service_sections_payload"),
                row_index=index,
                product=product,
            )
            service_sections_editor_state = self._normalize_contract_stage_editor_state(
                row.get("service_sections_editor_state"),
                row_index=index,
                product=product,
                service_sections=service_sections_json,
            )
            stage_payloads.append(
                {
                    "rank": index,
                    "product_id": product_id,
                    "service_sections_json": service_sections_json,
                    "service_sections_editor_state": service_sections_editor_state,
                    "service_customer_tz_editor_state": self._normalize_contract_stage_customer_tz_state(
                        row.get("service_customer_tz_editor_state"),
                        row_index=index,
                    ),
                    "service_composition_customer_tz": service_composition_customer_tz,
                    "service_composition_mode": service_composition_mode,
                    "service_composition": (
                        service_composition_customer_tz
                        if service_composition_mode == "customer_tz"
                        else str(row.get("service_composition") or "").strip()
                    ),
                    "evaluation_date_enabled": evaluation_date_enabled,
                    "evaluation_date": (
                        self._parse_contract_stage_date(
                            row.get("evaluation_date"),
                            row_index=index,
                            field_label=self.fields["evaluation_date"].label,
                        )
                        if evaluation_date_enabled
                        else None
                    ),
                    "source_data_term_enabled": source_data_term_enabled,
                    "source_data_term": source_data_term,
                    "source_data_term_unit": source_data_term_unit,
                    "source_data_date_enabled": source_data_date_enabled,
                    "source_data_date": (
                        self._parse_contract_stage_date(
                            row.get("source_data_date"),
                            row_index=index,
                            field_label=self.fields["source_data_date"].label,
                        )
                        if source_data_date_enabled
                        else None
                    ),
                    "service_term_months_enabled": service_term_months_enabled,
                    "service_term_months": service_term_months,
                    "preliminary_report_term_unit": preliminary_report_term_unit,
                    "preliminary_report_date_enabled": preliminary_report_date_enabled,
                    "preliminary_report_date": (
                        self._parse_contract_stage_date(
                            row.get("preliminary_report_date"),
                            row_index=index,
                            field_label=self.fields["preliminary_report_date"].label,
                        )
                        if preliminary_report_date_enabled
                        else None
                    ),
                    "final_report_term_weeks": final_report_term_weeks,
                    "final_report_term_unit": final_report_term_unit,
                    "final_report_date_enabled": final_report_date_enabled,
                    "final_report_date": (
                        self._parse_contract_stage_date(
                            row.get("final_report_date"),
                            row_index=index,
                            field_label=self.fields["final_report_date"].label,
                        )
                        if final_report_date_enabled
                        else None
                    ),
                    "next_stage_delay_days": self._parse_contract_stage_signed_integer(
                        row.get("next_stage_delay_days"),
                        row_index=index,
                        field_label="Задержка между этапами",
                        default=0,
                    ),
                    "advance_percent": advance_percent,
                    "advance_term_days": advance_term_days,
                    "preliminary_report_percent": preliminary_report_percent,
                    "preliminary_report_term_days": preliminary_report_term_days,
                    "final_report_percent": final_report_percent,
                    "final_report_term_days": final_report_term_days,
                }
            )
        self.cleaned_stage_payloads = stage_payloads
        return stage_payloads

    def clean_group_member(self):
        member = self.cleaned_data.get("group_member")
        if member and not (member.country_alpha2 or "").strip():
            raise forms.ValidationError("Для выбранной строки состава группы не заполнен код Альфа-2.")
        return member

    def clean_registration_region(self):
        return (self.cleaned_data.get("registration_region") or "").strip()

    def clean_asset_owner_region(self):
        return (self.cleaned_data.get("asset_owner_region") or "").strip()

    def clean_project_manager(self):
        manager_name, manager_prs_id = _resolve_project_manager_choice(self.cleaned_data.get("project_manager"))
        self._cleaned_project_manager_prs_id = manager_prs_id
        return manager_name

    def _calculate_final_report_percent(self, *, advance_percent, preliminary_report_percent):
        def to_decimal(value):
            if value in (None, ""):
                return Decimal("0")
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value).replace(",", "."))
            except (TypeError, ValueError, ArithmeticError):
                return Decimal("0")

        advance = to_decimal(advance_percent)
        preliminary = to_decimal(preliminary_report_percent)
        return (Decimal("100") - advance - preliminary).quantize(Decimal("0.01"))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.project_manager_prs_id = getattr(self, "_cleaned_project_manager_prs_id", "") or ""
        stage_payloads = list(getattr(self, "cleaned_stage_payloads", []) or [])
        if stage_payloads:
            instance.stage_payloads_json = [
                {
                    "rank": item["rank"],
                    "product_id": str(item["product_id"]),
                    "service_sections_json": [
                        {
                            "service_name": section.get("service_name") or "",
                            "code": section.get("code") or "",
                            **({"merge_without_code": True} if section.get("merge_without_code") else {}),
                        }
                        for section in item["service_sections_json"]
                    ],
                    "service_sections_editor_state": list(item["service_sections_editor_state"]),
                    "service_customer_tz_editor_state": dict(item["service_customer_tz_editor_state"]),
                    "service_composition_customer_tz": item["service_composition_customer_tz"],
                    "service_composition_mode": item["service_composition_mode"],
                    "service_composition": item["service_composition"],
                    "evaluation_date_enabled": item["evaluation_date_enabled"],
                    "evaluation_date": _format_contract_stage_date(item["evaluation_date"]),
                    "source_data_term_enabled": item["source_data_term_enabled"],
                    "source_data_term": (
                        "" if item["source_data_term"] is None else str(item["source_data_term"])
                    ),
                    "source_data_term_unit": item["source_data_term_unit"],
                    "source_data_date_enabled": item["source_data_date_enabled"],
                    "source_data_date": _format_contract_stage_date(item["source_data_date"]),
                    "service_term_months_enabled": item["service_term_months_enabled"],
                    "service_term_months": (
                        "" if item["service_term_months"] is None else str(item["service_term_months"])
                    ),
                    "preliminary_report_term_unit": item["preliminary_report_term_unit"],
                    "preliminary_report_date_enabled": item["preliminary_report_date_enabled"],
                    "preliminary_report_date": _format_contract_stage_date(item["preliminary_report_date"]),
                    "final_report_term_weeks": (
                        "" if item["final_report_term_weeks"] is None else str(item["final_report_term_weeks"])
                    ),
                    "final_report_term_unit": item["final_report_term_unit"],
                    "final_report_date_enabled": item["final_report_date_enabled"],
                    "final_report_date": _format_contract_stage_date(item["final_report_date"]),
                    "next_stage_delay_days": item["next_stage_delay_days"] or 0,
                    "payment_schedule_common": self.payment_schedule_common_enabled,
                    "advance_percent": self._serialize_contract_payload_decimal(item["advance_percent"]),
                    "advance_term_days": item["advance_term_days"],
                    "preliminary_report_percent": self._serialize_contract_payload_decimal(
                        item["preliminary_report_percent"]
                    ),
                    "preliminary_report_term_days": item["preliminary_report_term_days"],
                    "final_report_percent": self._serialize_contract_payload_decimal(item["final_report_percent"]),
                    "final_report_term_days": item["final_report_term_days"],
                }
                for item in stage_payloads
            ]
            last_stage = stage_payloads[-1]
            instance.service_sections_json = [
                {
                    "service_name": section.get("service_name") or "",
                    "code": section.get("code") or "",
                    **({"merge_without_code": True} if section.get("merge_without_code") else {}),
                }
                for section in last_stage["service_sections_json"]
            ]
            instance.service_sections_editor_state = list(last_stage["service_sections_editor_state"])
            instance.service_customer_tz_editor_state = dict(last_stage["service_customer_tz_editor_state"])
            instance.service_composition_customer_tz = last_stage["service_composition_customer_tz"]
            instance.service_composition_mode = last_stage["service_composition_mode"]
            instance.service_composition = last_stage["service_composition"]
            instance.evaluation_date = last_stage.get("evaluation_date")
            instance.source_data_term = last_stage.get("source_data_term")
            instance.source_data_term_unit = last_stage.get(
                "source_data_term_unit"
            ) or ContractProjectRegistration.SourceDataTermUnit.WEEKS.value
            instance.source_data_date = last_stage.get("source_data_date")
            instance.service_term_months = last_stage.get("service_term_months")
            instance.preliminary_report_term_unit = last_stage.get(
                "preliminary_report_term_unit"
            ) or ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value
            instance.preliminary_report_date = last_stage.get("preliminary_report_date")
            instance.final_report_term_weeks = last_stage.get("final_report_term_weeks")
            instance.final_report_term_unit = last_stage.get(
                "final_report_term_unit"
            ) or ContractProjectRegistration.FinalReportTermUnit.WEEKS.value
            instance.final_report_date = last_stage.get("final_report_date")
            if not self.payment_schedule_common_enabled:
                instance.advance_percent = last_stage.get("advance_percent")
                instance.advance_term_days = last_stage.get("advance_term_days")
                instance.preliminary_report_percent = last_stage.get("preliminary_report_percent")
                instance.preliminary_report_term_days = last_stage.get("preliminary_report_term_days")
                instance.final_report_percent = last_stage.get("final_report_percent")
                instance.final_report_term_days = last_stage.get("final_report_term_days")
        if instance.asset_owner_matches_customer:
            instance.asset_owner = instance.customer or ""
            instance.asset_owner_country = instance.country
            instance.asset_owner_region = instance.registration_region or ""
            instance.asset_owner_identifier = instance.identifier or ""
            instance.asset_owner_registration_number = instance.registration_number or ""
            instance.asset_owner_registration_date = instance.registration_date
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        if self.payment_schedule_common_enabled:
            if not self.errors.get("advance_percent") and not self.errors.get("preliminary_report_percent"):
                final_percent = self._calculate_final_report_percent(
                    advance_percent=cleaned_data.get("advance_percent"),
                    preliminary_report_percent=cleaned_data.get("preliminary_report_percent"),
                )
                if final_percent < 0 or final_percent > 100:
                    self.add_error(
                        "final_report_percent",
                        "Рассчитанный размер оплаты Итогового отчёта должен быть в диапазоне от 0% до 100%.",
                    )
                else:
                    cleaned_data["final_report_percent"] = final_percent
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

        valid_ids = list(
            Product.objects
            .filter(pk__in=set(product_ids))
            .order_by("position", "id")
            .values_list("pk", flat=True)
        )
        valid_set = set(valid_ids)
        ordered_valid_ids = [product_id for product_id in product_ids if product_id in valid_set]
        if not ordered_valid_ids:
            self.add_error("type_ids", "Укажите хотя бы один продукт.")
        elif not self.allow_multiple_products and len(ordered_valid_ids) > 1:
            self.add_error("type_ids", "Для строки проекта можно выбрать только один продукт.")
        self.cleaned_type_ids = ordered_valid_ids
        if ordered_valid_ids and not self.errors.get("type_ids"):
            try:
                self._collect_contract_stage_payloads()
            except forms.ValidationError as exc:
                if hasattr(exc, "error_list"):
                    for error in exc.error_list:
                        self.add_error(None, error)
                else:
                    self.add_error(None, exc)
        if cleaned_data.get("sub_number") in (None, ""):
            cleaned_data["sub_number"] = 0
        number = cleaned_data.get("number")
        sub_number = cleaned_data.get("sub_number")
        proposal_registration = cleaned_data.get("proposal_registration")
        group_member = cleaned_data.get("group_member")
        if (
            number is not None
            and sub_number is not None
            and group_member is not None
            and not self.errors.get("number")
            and not self.errors.get("sub_number")
            and not self.errors.get("proposal_registration")
            and not self.errors.get("group_member")
        ):
            proposal_sequence = int(getattr(proposal_registration, "sub_number", 0) or 0)
            duplicate_qs = ContractProjectRegistration.objects.filter(
                number=number,
                sub_number=sub_number,
                group_member=group_member,
            )
            if proposal_sequence:
                duplicate_qs = duplicate_qs.filter(
                    proposal_registration__sub_number=proposal_sequence,
                )
            else:
                duplicate_qs = duplicate_qs.filter(
                    Q(proposal_registration__isnull=True)
                    | Q(proposal_registration__sub_number=0)
                )
            if self.instance.pk:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                self.add_error(
                    "sub_number",
                    "Для строк с одинаковыми Номер, последовательностью ТКП и группой значение № должно быть уникальным.",
                )
        if getattr(self, "cleaned_stage_payloads", None) and not self.payment_schedule_common_enabled:
            last_stage = self.cleaned_stage_payloads[-1]
            cleaned_data["service_composition"] = last_stage["service_composition"]
            cleaned_data["service_composition_customer_tz"] = last_stage["service_composition_customer_tz"]
            cleaned_data["service_composition_mode"] = last_stage["service_composition_mode"]
            cleaned_data["advance_percent"] = last_stage["advance_percent"]
            cleaned_data["advance_term_days"] = last_stage["advance_term_days"]
            cleaned_data["preliminary_report_percent"] = last_stage["preliminary_report_percent"]
            cleaned_data["preliminary_report_term_days"] = last_stage["preliminary_report_term_days"]
            cleaned_data["final_report_percent"] = last_stage["final_report_percent"]
            cleaned_data["final_report_term_days"] = last_stage["final_report_term_days"]
        elif getattr(self, "cleaned_stage_payloads", None):
            last_stage = self.cleaned_stage_payloads[-1]
            cleaned_data["service_composition"] = last_stage["service_composition"]
            cleaned_data["service_composition_customer_tz"] = last_stage["service_composition_customer_tz"]
            cleaned_data["service_composition_mode"] = last_stage["service_composition_mode"]
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

    def _build_contract_stage_rows_from_proposal(self, proposal):
        ordered_products = list(proposal.ordered_products())
        stored_stages = list(getattr(proposal, "stage_payloads_json", None) or [])
        proposal_fallback = {
            "service_sections_json": proposal.service_sections_json or [],
            "service_sections_editor_state": proposal.service_sections_editor_state or [],
            "service_customer_tz_editor_state": proposal.service_customer_tz_editor_state or {},
            "service_composition_customer_tz": proposal.service_composition_customer_tz or "",
            "service_composition_mode": proposal.service_composition_mode or "sections",
            "service_composition": proposal.service_composition or "",
            "evaluation_date_enabled": True,
            "evaluation_date": _format_contract_stage_date(proposal.evaluation_date),
            "source_data_term_enabled": True,
            "source_data_term": "",
            "source_data_term_unit": ContractProjectRegistration.SourceDataTermUnit.WEEKS.value,
            "source_data_date_enabled": True,
            "source_data_date": "",
            "service_term_months_enabled": True,
            "service_term_months": (
                "" if proposal.service_term_months is None else format(proposal.service_term_months, ".1f")
            ),
            "preliminary_report_term_unit": ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value,
            "preliminary_report_date_enabled": True,
            "preliminary_report_date": _format_contract_stage_date(proposal.preliminary_report_date),
            "final_report_term_weeks": (
                "" if proposal.final_report_term_weeks is None else format(proposal.final_report_term_weeks, ".1f")
            ),
            "final_report_term_unit": ContractProjectRegistration.FinalReportTermUnit.WEEKS.value,
            "final_report_date_enabled": True,
            "final_report_date": _format_contract_stage_date(proposal.final_report_date),
        }
        payment_fallback = {
            "advance_percent": proposal.advance_percent,
            "advance_term_days": proposal.advance_term_days,
            "preliminary_report_percent": proposal.preliminary_report_percent,
            "preliminary_report_term_days": proposal.preliminary_report_term_days,
            "final_report_percent": proposal.final_report_percent,
            "final_report_term_days": proposal.final_report_term_days,
        }
        if stored_stages:
            rows = []
            for index, payload in enumerate(stored_stages, start=1):
                product_id = str(payload.get("product_id") or "")
                product = next(
                    (item for item in ordered_products if str(item.pk) == product_id),
                    ordered_products[index - 1] if index - 1 < len(ordered_products) else None,
                )
                rows.append(
                    self._contract_stage_row_from_payload(
                        payload,
                        rank=index,
                        product_id=product_id or str(getattr(product, "pk", "") or ""),
                        product=product,
                        fallback=proposal_fallback if index == 1 else None,
                        payment_fallback=payment_fallback,
                    )
                )
            if rows:
                return rows

        if not ordered_products:
            return [
                self._contract_stage_row_from_payload(
                    {},
                    rank=1,
                    product_id="",
                    product=None,
                    fallback=proposal_fallback,
                    payment_fallback=payment_fallback,
                )
            ]

        rows = []
        for index, product in enumerate(ordered_products, start=1):
            rows.append(
                self._contract_stage_row_from_payload(
                    {},
                    rank=index,
                    product_id=str(product.pk),
                    product=product,
                    fallback=proposal_fallback if index == 1 else None,
                    payment_fallback=payment_fallback,
                )
            )
        return rows


CONTRACT_PREFILL_FROM_PROPOSAL_FIELDS = [
    "sub_number",
    "group_member",
    "name",
    "year",
    "country",
    "customer",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "asset_owner",
    "asset_owner_matches_customer",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
    "proposal_project_name",
    "purpose",
    "service_composition",
    "service_composition_customer_tz",
    "service_composition_mode",
    "evaluation_date",
    "service_term_months",
    "preliminary_report_date",
    "final_report_term_weeks",
    "final_report_term_unit",
    "final_report_date",
    "advance_percent",
    "advance_term_days",
    "preliminary_report_percent",
    "preliminary_report_term_days",
    "final_report_percent",
    "final_report_term_days",
]

CONTRACT_PREFILL_PAYMENT_FIELDS = (
    "advance_percent",
    "advance_term_days",
    "preliminary_report_percent",
    "preliminary_report_term_days",
    "final_report_percent",
    "final_report_term_days",
)


def _ranked_products_from_proposal(proposal):
    products = list(proposal.ordered_products())
    if not products:
        return [{
            "rank": 1,
            "consulting_type": "",
            "service_category": "",
            "service_subtype": "",
            "product_id": "",
        }]
    return [
        {
            "rank": index,
            "consulting_type": (product.consulting_type_display or "").strip(),
            "service_category": (product.service_category_display or "").strip(),
            "service_subtype": (product.service_subtype_display or "").strip(),
            "product_id": str(product.pk),
        }
        for index, product in enumerate(products, start=1)
    ]


def _proposal_payment_schedule_common(proposal):
    stored_stages = list(getattr(proposal, "stage_payloads_json", None) or [])
    return not any(
        isinstance(payload, dict) and payload.get("payment_schedule_common") is False
        for payload in stored_stages
    )


def build_contract_project_form_from_proposal(proposal, *, registration=None):
    form = (
        ContractProjectRegistrationForm(instance=registration)
        if registration
        else ContractProjectRegistrationForm()
    )

    for field_name in CONTRACT_PREFILL_FROM_PROPOSAL_FIELDS:
        form.initial[field_name] = getattr(proposal, field_name, None)
    form.initial["proposal_registration"] = proposal.pk

    if registration:
        form.initial["number"] = registration.number
        form.initial["status"] = registration.status
        form.initial["contract_number"] = registration.contract_number
        form.initial["contract_date"] = registration.contract_date
        form.initial["agreement_type"] = registration.agreement_type
    else:
        form.initial["number"] = proposal.number

    payment_schedule_common = _proposal_payment_schedule_common(proposal)
    form.payment_schedule_common_enabled = payment_schedule_common
    form.initial["payment_schedule_common"] = payment_schedule_common
    for field_name in CONTRACT_PREFILL_PAYMENT_FIELDS:
        if payment_schedule_common:
            form.fields[field_name].widget.attrs.pop("disabled", None)
        else:
            form.fields[field_name].widget.attrs["disabled"] = True

    try:
        form.initial["final_report_percent"] = form._calculate_final_report_percent(
            advance_percent=form.initial.get("advance_percent"),
            preliminary_report_percent=form.initial.get("preliminary_report_percent"),
        )
    except (forms.ValidationError, TypeError, ValueError):
        form.initial["final_report_percent"] = proposal.final_report_percent

    form.stage_rows = form._build_contract_stage_rows_from_proposal(proposal)
    form.prefill_ranked_products = _ranked_products_from_proposal(proposal)
    return form


PARTY_SHORT = {"individual": "ФЗЛ", "legal_entity": "ЮРЛ", "ip": "ИП"}
TYPE_SHORT = {"gph": "ГПХ", "smz": "СМЗ"}


class ContractEditForm(forms.ModelForm):
    final_payment = forms.DecimalField(
        label="Окон. платеж",
        required=False,
        disabled=True,
        widget=forms.NumberInput(attrs={
            "class": "form-control readonly-field",
            "readonly": True,
            "step": "1",
        }),
    )

    def __init__(self, *args, group_member_initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contract_group_member"].queryset = (
            GroupMember.objects
            .exclude(country_alpha2="")
            .order_by("position", "id")
        )
        self.fields["contract_group_member"].label_from_instance = lambda obj: obj.group_display_label
        self.fields["contract_group_member"].empty_label = "— Не выбрано —"
        if (
            not self.is_bound
            and self.instance
            and not self.instance.contract_group_member_id
            and group_member_initial
        ):
            self.fields["contract_group_member"].initial = group_member_initial.pk
        if not self.is_bound:
            if self.instance and self.instance.prepayment is not None:
                self.initial["prepayment"] = int(self.instance.prepayment)
            else:
                self.initial["prepayment"] = 50
            if self.instance and self.instance.final_payment is not None:
                self.initial["final_payment"] = int(self.instance.final_payment)
            else:
                self.initial["final_payment"] = 50

    class Meta:
        model = Performer
        fields = [
            "contract_group_member",
            "contract_number",
            "contract_date",
            "prepayment",
            "final_payment",
            "contract_file",
        ]
        widgets = {
            "contract_group_member": forms.Select(attrs={"class": "form-select", "id": "contracts-group-select"}),
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
            "contract_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "prepayment": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "1",
                "min": "0",
                "max": "100",
            }),
            "contract_file": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_prepayment(self):
        value = self.cleaned_data.get("prepayment")
        if value is None:
            if self.instance and self.instance.prepayment is not None:
                return self.instance.prepayment
            return 50
        return value


class ContractSigningForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance is None:
            return
        self.fields["contract_employee_scan"].widget.attrs.update(
            {
                "cloud_current_url": getattr(instance, "contract_employee_scan_link", "") or "",
                "cloud_current_name": getattr(instance, "contract_scan_document", "") or "",
            }
        )
        self.fields["contract_signed_scan_file"].widget.attrs.update(
            {
                "cloud_current_url": getattr(instance, "contract_signed_scan_link", "") or "",
                "cloud_current_name": getattr(instance, "contract_signed_scan", "") or "",
            }
        )

    class Meta:
        model = Performer
        fields = [
            "contract_employee_scan",
            "contract_signed_scan_file",
        ]
        widgets = {
            "contract_employee_scan": _ContractFileInput(attrs={"class": "form-control"}),
            "contract_signed_scan_file": _ContractFileInput(attrs={"class": "form-control"}),
        }


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name")


def _group_member_order_map():
    counters = {}
    result = {}
    for m in GroupMember.objects.all():
        key = m.country_code or m.country_name or ""
        idx = counters.get(key, 0)
        result[m.pk] = idx
        counters[key] = idx + 1
    return result


def _group_member_label(member, order):
    alpha2 = member.country_alpha2 or ""
    prefix = f"{alpha2}-{order}" if order else alpha2
    return f"{prefix} {member.short_name}"


def _group_member_short(member, order):
    alpha2 = member.country_alpha2 or ""
    return f"{alpha2}-{order}" if order else alpha2


class ContractTemplateForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ContractTemplate
        fields = [
            "contract_type", "party",
            "sample_name", "version", "file",
            "act_sample_name", "act_version", "act_file",
        ]
        widgets = {
            "contract_type": forms.Select(attrs={"class": "form-select"}),
            "party": forms.Select(attrs={"class": "form-select"}),
            "sample_name": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "version": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "file": _ContractFileInput(attrs={"class": "form-control"}),
            "act_sample_name": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "act_version": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "act_file": _ContractFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._orig_sample_name = ""
        self._orig_version = ""
        self._orig_act_sample_name = ""
        self._orig_act_version = ""
        if self.instance and self.instance.pk:
            self._orig_sample_name = self.instance.sample_name or ""
            self._orig_version = self.instance.version or ""
            self._orig_act_sample_name = self.instance.act_sample_name or ""
            self._orig_act_version = self.instance.act_version or ""

        order_map = _group_member_order_map()
        members_qs = list(GroupMember.objects.all())
        products_qs = list(Product.objects.order_by("position", "id"))

        self.fields["file"].required = not (self.instance and self.instance.pk and self.instance.file)
        self.fields["act_file"].required = False
        self.fields["sample_name"].required = False
        self.fields["version"].required = False
        self.fields["act_sample_name"].required = False
        self.fields["act_version"].required = False

        self.group_short_map = {
            str(m.pk): _group_member_short(m, order_map.get(m.pk, 0)) for m in members_qs
        }
        self.group_options = [
            {
                "id": member.pk,
                "label": _group_member_label(member, order_map.get(member.pk, 0)),
            }
            for member in members_qs
        ]
        selected_group_ids, self.is_all_groups_selected = self._selected_group_ids()
        self.selected_group_ids = {str(value) for value in selected_group_ids}
        self.product_short_map = {
            str(product.pk): (product.short_name or "").strip()
            for product in products_qs
        }
        self.product_options = [
            {
                "id": product.pk,
                "label": product.short_name or str(product),
            }
            for product in products_qs
        ]
        selected_product_ids, self.is_all_products_selected = self._selected_product_ids()
        self.selected_product_ids = {str(value) for value in selected_product_ids}

        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_code:
            qs = (qs | OKSMCountry.objects.filter(code=self.instance.country_code)).distinct().order_by("short_name")
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: f"{obj.alpha3} {obj.short_name}"

        if self.instance and self.instance.pk and self.instance.country_code:
            try:
                self.initial["country"] = OKSMCountry.objects.get(code=self.instance.country_code).pk
            except OKSMCountry.DoesNotExist:
                pass
        elif not self.instance.pk:
            try:
                self.initial["country"] = qs.get(alpha3="RUS").pk
            except OKSMCountry.DoesNotExist:
                pass

        self.country_alpha3 = {
            str(c.pk): c.alpha3 for c in self.fields["country"].queryset
        }

        sections = (
            TypicalSection.objects
            .select_related("product")
            .order_by("product__position", "position", "id")
        )
        self.section_options = [
            {
                "id": s.id,
                "code": s.code,
                "short_name": s.short_name,
                "short_name_ru": s.short_name_ru,
                "label": f"{s.product.short_name}:{s.code} {s.short_name_ru}",
            }
            for s in sections
        ]

        self.is_all_selected = True
        self.selected_section_codes = set()
        if self.instance and self.instance.pk:
            self.is_all_selected = self.instance.is_all_sections
            if not self.is_all_selected:
                self.selected_section_codes = {
                    entry.get("code") for entry in (self.instance.typical_sections_json or [])
                }

        existing = ContractTemplate.objects.all()
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        version_map = {}
        act_version_map = {}
        for t in existing:
            base = t.sample_name.rsplit("_v", 1)[0] if t.sample_name else ""
            try:
                v = int(t.version)
            except (ValueError, TypeError):
                v = 0
            version_map[base] = max(version_map.get(base, 0), v)
            act_base = t.act_sample_name.rsplit("_v", 1)[0] if t.act_sample_name else ""
            try:
                act_v = int(t.act_version)
            except (ValueError, TypeError):
                act_v = 0
            if act_base:
                act_version_map[act_base] = max(act_version_map.get(act_base, 0), act_v)
        self.version_map = version_map
        self.act_version_map = act_version_map

        self.current_base = ""
        self.current_version = ""
        self.current_act_base = ""
        self.current_act_version = ""
        if self.instance and self.instance.pk and self.instance.sample_name:
            self.current_base = self.instance.sample_name.rsplit("_v", 1)[0]
            self.current_version = self.instance.version or ""
        if self.instance and self.instance.pk and self.instance.act_sample_name:
            self.current_act_base = self.instance.act_sample_name.rsplit("_v", 1)[0]
            self.current_act_version = self.instance.act_version or ""

    def _posted_values(self, name):
        if not self.is_bound:
            return None
        if hasattr(self.data, "getlist"):
            return self.data.getlist(name)
        value = self.data.get(name)
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _selected_group_ids(self):
        posted = self._posted_values("group_member_ids")
        if posted is not None:
            if GROUP_ALL_VALUE in posted or not posted:
                return [], True
            return [int(value) for value in posted if str(value).isdigit()], False

        try:
            existing_ids = list(self.instance.group_members.values_list("pk", flat=True))
        except ValueError:
            existing_ids = []
        if self.instance and self.instance.pk:
            if existing_ids:
                return existing_ids, False
            if self.instance.group_member_id:
                return [self.instance.group_member_id], False
        return [], True

    def _selected_product_ids(self):
        posted = self._posted_values("product_ids")
        if posted is not None:
            if GROUP_ALL_VALUE in posted or not posted:
                return [], True
            return [int(value) for value in posted if str(value).isdigit()], False

        try:
            existing_ids = list(self.instance.products.values_list("pk", flat=True))
        except ValueError:
            existing_ids = []
        if self.instance and self.instance.pk:
            if existing_ids:
                return existing_ids, False
            if self.instance.product_id:
                return [self.instance.product_id], False
        return [], True

    def clean(self):
        cleaned = super().clean()
        for field_name, model, label in (
            ("group_member_ids", GroupMember, "Группа"),
            ("product_ids", Product, "Продукт"),
        ):
            values = self._posted_values(field_name) or []
            if GROUP_ALL_VALUE in values or not values:
                cleaned[field_name] = []
                continue

            selected_ids = [int(value) for value in values if str(value).isdigit()]
            existing_ids = set(model.objects.filter(pk__in=selected_ids).values_list("pk", flat=True))
            if existing_ids != set(selected_ids):
                raise forms.ValidationError(f"В поле «{label}» выбраны несуществующие значения.")
            cleaned[field_name] = selected_ids
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        group_ids = self.cleaned_data.get("group_member_ids") or []
        product_ids = self.cleaned_data.get("product_ids") or []
        groups = list(GroupMember.objects.filter(pk__in=group_ids))
        products = list(Product.objects.filter(pk__in=product_ids).order_by("position", "id"))
        groups_by_id = {group.pk: group for group in groups}
        products_by_id = {product.pk: product for product in products}
        groups = [groups_by_id[group_id] for group_id in group_ids if group_id in groups_by_id]
        products = [products_by_id[product_id] for product_id in product_ids if product_id in products_by_id]
        instance.group_member = groups[0] if groups else None
        instance.product = products[0] if products else None

        country = self.cleaned_data.get("country")
        if country:
            instance.country_name = country.short_name
            instance.country_code = country.code
        else:
            instance.country_name = ""
            instance.country_code = ""

        section_values = self._posted_values("section_ids") or []
        if SECTION_ALL_VALUE in section_values or not section_values:
            instance.is_all_sections = True
            instance.typical_sections_json = []
        else:
            instance.is_all_sections = False
            selected_ids = {int(v) for v in section_values if v.isdigit()}
            chosen = (
                TypicalSection.objects
                .filter(pk__in=selected_ids)
                .order_by("product__position", "position", "id")
            )
            instance.typical_sections_json = [
                {"code": s.code, "short_name": s.short_name}
                for s in chosen
            ]

        party_short = PARTY_SHORT.get(instance.party, "")
        type_short = TYPE_SHORT.get(instance.contract_type, "")
        alpha3 = country.alpha3 if country else ""
        product_name = "-".join(
            (product.short_name or "").strip()
            for product in products
            if product.short_name
        ) or "Все"
        if instance.is_all_sections:
            sections_part = "Общий"
        else:
            codes = [e.get("code", "") for e in instance.typical_sections_json or [] if e.get("code")]
            sections_part = "-".join(codes) if codes else "Общий"
        order_map = _group_member_order_map()
        group_prefix = "-".join(
            _group_member_short(group, order_map.get(group.pk, 0))
            for group in groups
        ) or "Все"
        group_prefix = f"{group_prefix} "
        name_suffix = f"{party_short} {type_short} {alpha3}_{product_name}-{sections_part}"
        base_name = f"{group_prefix}Шаблон договора {name_suffix}"
        act_base_name = f"{group_prefix}Шаблон акта {name_suffix}"

        existing = ContractTemplate.objects.all()
        if instance.pk:
            orig_base = self._orig_sample_name.rsplit("_v", 1)[0] if self._orig_sample_name else ""
            if orig_base == base_name:
                version = self._orig_version or "1"
            else:
                existing = existing.exclude(pk=instance.pk)
                version = str(self._next_version(existing, base_name))
        else:
            version = str(self._next_version(existing, base_name))

        instance.version = version
        instance.sample_name = f"{base_name}_v{version}"

        act_existing = ContractTemplate.objects.all()
        if instance.pk:
            orig_act_base = self._orig_act_sample_name.rsplit("_v", 1)[0] if self._orig_act_sample_name else ""
            if orig_act_base == act_base_name:
                act_version = self._orig_act_version or "1"
            else:
                act_existing = act_existing.exclude(pk=instance.pk)
                act_version = str(self._next_version(act_existing, act_base_name, "act_sample_name", "act_version"))
        else:
            act_version = str(self._next_version(act_existing, act_base_name, "act_sample_name", "act_version"))

        instance.act_version = act_version
        instance.act_sample_name = f"{act_base_name}_v{act_version}"

        self._apply_template_file_name(instance, "file", instance.sample_name, self.cleaned_data.get("file"))
        self._apply_template_file_name(instance, "act_file", instance.act_sample_name, self.cleaned_data.get("act_file"))

        if commit:
            instance.save()
            instance.group_members.set(groups)
            instance.products.set(products)
        return instance

    @staticmethod
    def _apply_template_file_name(instance, field_name, sample_name, uploaded):
        import os

        field_file = getattr(instance, field_name)
        if isinstance(uploaded, UploadedFile):
            ext = os.path.splitext(uploaded.name)[1]
            field_file.name = sample_name + ext
            return
        if not (instance.pk and field_file):
            return
        old_path = field_file.name
        ext = os.path.splitext(old_path)[1]
        new_name = "contract_templates/" + sample_name + ext
        if old_path == new_name:
            return
        storage = field_file.storage
        if storage.exists(old_path):
            old_full = storage.path(old_path)
            new_full = storage.path(new_name)
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            os.rename(old_full, new_full)
            field_file.name = new_name

    @staticmethod
    def _next_version(qs, base_name, sample_attr="sample_name", version_attr="version"):
        max_v = 0
        for t in qs:
            sample_name = getattr(t, sample_attr, "") or ""
            t_base = sample_name.rsplit("_v", 1)[0] if sample_name else ""
            if t_base == base_name:
                try:
                    v = int(getattr(t, version_attr, ""))
                except (ValueError, TypeError):
                    v = 0
                max_v = max(max_v, v)
        return max_v + 1


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

        self.is_computed = bool(
            self.instance and self.instance.pk and self.instance.is_computed
        )

        if self.is_computed:
            locked_style = "background-color:#f8f9fa; color:#6c757d;"
            self.fields["key"].widget.attrs.update({
                "readonly": True, "tabindex": "-1", "style": locked_style,
            })
            for fname in ("source_section", "source_table", "source_column"):
                self.fields[fname].widget.attrs.update({
                    "disabled": True, "style": locked_style,
                })

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
            return cleaned
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


class ContractSubjectForm(forms.ModelForm):
    class Meta:
        model = ContractSubject
        fields = ["product", "subject_text"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "subject_text": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Предмет договора",
                "rows": 4,
                "style": "resize: vertical;",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.order_by("position", "id")
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
