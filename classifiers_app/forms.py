from datetime import date as date_type, datetime
from decimal import Decimal, InvalidOperation
import re

from django import forms
from django.db.models import Max, Q

from .models import (
    OKSMCountry,
    OKVCurrency,
    LegalEntityIdentifier,
    TerritorialDivision,
    LivingWage,
    LegalEntityRecord,
    RussianFederationSubjectCode,
    BusinessEntityRecord,
    BusinessEntityIdentifierRecord,
    BusinessEntityAttributeRecord,
    BusinessEntityReorganizationEvent,
    BusinessEntityRelationRecord,
    detect_legal_entity_region_by_identifier,
)


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    )


def _territorial_division_region_choices(current_value=""):
    choices = []
    seen = set()
    for region_name in TerritorialDivision.objects.order_by("region_name", "position", "id").values_list("region_name", flat=True):
        if not region_name or region_name in seen:
            continue
        seen.add(region_name)
        choices.append((region_name, region_name))
    if current_value and current_value not in seen:
        choices.append((current_value, current_value))
    return choices


def _format_bsn_id(obj):
    return f"{obj.pk:05d}-BSN"


def _format_idn_id(obj):
    return f"{obj.pk:05d}-IDN"


def _resolve_idn_record_from_autocomplete(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    match = re.match(r"^(?P<pk>\d+)-IDN(?:\s|$)", value, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return BusinessEntityIdentifierRecord.objects.filter(pk=int(match.group("pk"))).first()
    except (TypeError, ValueError):
        return None


def _next_bsn_preview_id(offset=1):
    next_id = (BusinessEntityRecord.objects.aggregate(mx=Max("id")).get("mx") or 0) + offset
    return f"{next_id:05d}-BSN"


def _next_reorganization_event_uid_preview():
    max_number = 0
    for raw in BusinessEntityReorganizationEvent.objects.exclude(reorganization_event_uid="").values_list(
        "reorganization_event_uid",
        flat=True,
    ):
        value = (raw or "").strip()
        if not value.endswith("-REO"):
            continue
        number_part = value[:-4]
        if number_part.isdigit():
            max_number = max(max_number, int(number_part))
    return f"{max_number + 1:05d}-REO"


def _legal_entity_identifier_choices_for_country(country_id, current_value=""):
    choices = [("", "---------")]
    seen = set()
    if country_id:
        for value in (
            LegalEntityIdentifier.objects.filter(country_id=country_id)
            .order_by("position", "id")
            .values_list("identifier", flat=True)
        ):
            if not value or value in seen:
                continue
            seen.add(value)
            choices.append((value, value))
    if current_value and current_value not in seen:
        choices.append((current_value, current_value))
    return choices


def _territorial_division_region_choices_for_country(country_id, current_value="", as_of=None):
    choices = []
    seen = set()
    if country_id:
        qs = TerritorialDivision.objects.filter(country_id=country_id)
        if as_of:
            qs = qs.filter(
                effective_date__lte=as_of,
            ).filter(
                Q(abolished_date__isnull=True) | Q(abolished_date__gte=as_of),
            )
        for region_name in qs.order_by("region_name", "id").values_list("region_name", flat=True):
            if not region_name or region_name in seen:
                continue
            seen.add(region_name)
            choices.append(region_name)
    if current_value and current_value not in seen:
        choices.append(current_value)
    return choices


def _parse_form_date(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_guillemets(value):
    text = value or ""
    if '"' not in text:
        return text
    out = []
    for char in text:
        if char == '"':
            prev = out[-1] if out else ""
            out.append("\u00AB" if (not prev or re.match(r"[\s(\[{\u00AB]", prev)) else "\u00BB")
        else:
            out.append(char)
    return "".join(out)


def _resolve_territorial_division_by_region_name(region_name):
    if not region_name:
        return None
    russian_match = TerritorialDivision.objects.filter(
        region_name__iexact=region_name,
        country__short_name="Россия",
    ).order_by("position", "id").first()
    if russian_match:
        return russian_match
    return TerritorialDivision.objects.filter(
        region_name__iexact=region_name,
    ).order_by("position", "id").first()


def _period_order_is_invalid(valid_from, valid_to, *, exclusive_end):
    if valid_from is None or valid_to is None:
        return False
    return valid_to <= valid_from if exclusive_end else valid_to < valid_from


def _periods_overlap(valid_from, valid_to, other_from, other_to, *, exclusive_end):
    if exclusive_end:
        if valid_to is not None and other_from is not None and valid_to <= other_from:
            return False
        if other_to is not None and valid_from is not None and other_to <= valid_from:
            return False
        return True
    if valid_to is not None and other_from is not None and valid_to < other_from:
        return False
    if other_to is not None and valid_from is not None and other_to < valid_from:
        return False
    return True


def _find_period_overlap(queryset, *, valid_from, valid_to, start_field, end_field, exclusive_end):
    for item in queryset.only("pk", start_field, end_field):
        if _periods_overlap(
            valid_from,
            valid_to,
            getattr(item, start_field),
            getattr(item, end_field),
            exclusive_end=exclusive_end,
        ):
            return item
    return None


def _format_overlap_date(value):
    return value.strftime("%d.%m.%Y") if value else "—"


def _format_registry_overlap_message(*, registry_label, item_suffix, overlap, start_field, end_field, relation_label):
    start_value = _format_overlap_date(getattr(overlap, start_field))
    end_value = _format_overlap_date(getattr(overlap, end_field))
    return (
        f'Период пересекается с записью «{overlap.pk:05d}-{item_suffix}» '
        f'(«Действ. от» = {start_value}, «Действ. до» = {end_value}) '
        f'в «{registry_label}» для этого {relation_label}.'
    )


class OKSMCountryForm(forms.ModelForm):
    class Meta:
        model = OKSMCountry
        fields = ["number", "code", "short_name", "full_name", "alpha2", "alpha3", "approval_date", "expiry_date", "source"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Порядковый номер"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "000", "maxlength": "3"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое наименование страны"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Полное наименование страны"}),
            "alpha2": forms.TextInput(attrs={"class": "form-control", "placeholder": "AA", "maxlength": "2", "style": "text-transform:uppercase"}),
            "alpha3": forms.TextInput(attrs={"class": "form-control", "placeholder": "AAA", "maxlength": "3", "style": "text-transform:uppercase"}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_alpha2(self):
        return (self.cleaned_data.get("alpha2") or "").upper()

    def clean_alpha3(self):
        return (self.cleaned_data.get("alpha3") or "").upper()

    def clean_code(self):
        val = self.cleaned_data.get("code") or ""
        if not val.isdigit() or len(val) != 3:
            raise forms.ValidationError("Код должен состоять из трёх цифр.")
        return val


class OKVCurrencyForm(forms.ModelForm):
    countries = forms.ModelMultipleChoiceField(
        label="Страны использования",
        queryset=OKSMCountry.objects.none(),
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "size": "8",
            "style": "font-family: monospace; font-size: 0.78rem;",
        }),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["short_name"].required = True
        qs = _active_countries_qs()
        if self.instance and self.instance.pk:
            qs = (qs | self.instance.countries.all()).distinct()
        self.fields["countries"].queryset = qs.order_by("short_name")
        self.fields["countries"].label_from_instance = lambda obj: f"{obj.code}  {obj.short_name}"

    class Meta:
        model = OKVCurrency
        fields = ["code_numeric", "code_alpha", "name", "abbreviation", "symbol", "countries", "approval_date", "expiry_date", "source"]
        widgets = {
            "code_numeric": forms.TextInput(attrs={"class": "form-control", "placeholder": "000", "maxlength": "3"}),
            "code_alpha": forms.TextInput(attrs={"class": "form-control", "placeholder": "AAA", "maxlength": "3", "style": "text-transform:uppercase"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование валюты"}),
            "abbreviation": forms.TextInput(attrs={"class": "form-control", "placeholder": "Сокр. обозначение"}),
            "symbol": forms.TextInput(attrs={"class": "form-control", "placeholder": "₽, $, € ..."}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_code_numeric(self):
        val = self.cleaned_data.get("code_numeric") or ""
        if not val.isdigit() or len(val) != 3:
            raise forms.ValidationError("Код должен состоять из трёх цифр.")
        return val

    def clean_code_alpha(self):
        return (self.cleaned_data.get("code_alpha") or "").upper()


class LegalEntityIdentifierForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "lei-country-select"}),
        required=False,
    )
    code = forms.CharField(
        label="Код",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "readonly": True,
            "tabindex": "-1",
            "style": "background-color:#e9ecef; color:#6c757d;",
            "id": "lei-code-field",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = OKSMCountry.objects.all().order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["country"].label = "Страна (наименование краткое)"
        if self.instance and self.instance.pk and self.instance.country_id:
            self.fields["code"].initial = self.instance.country.code if self.instance.country else ""

    class Meta:
        model = LegalEntityIdentifier
        fields = ["identifier", "full_name", "country", "code"]
        widgets = {
            "identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Идентификатор"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование идентификатора (полное)"}),
        }


class TerritorialDivisionForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Наименование страны (краткое)",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct()
        self.fields["country"].queryset = qs.order_by("short_name")
        self.fields["country"].label_from_instance = lambda obj: obj.short_name

    class Meta:
        model = TerritorialDivision
        fields = ["country", "region_name", "region_code", "effective_date", "abolished_date", "source"]
        widgets = {
            "region_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование региона"}),
            "region_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код региона"}),
            "effective_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "abolished_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }


class RussianFederationSubjectCodeForm(forms.ModelForm):
    subject_name = forms.ChoiceField(
        label="Наименование субъекта Российской Федерации",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    oktmo_code = forms.CharField(
        label="Код региона ОКТМО",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "readonly": True,
            "tabindex": "-1",
            "style": "background-color:#f8f9fa; color:#6c757d;",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_subject = ""
        if self.is_bound:
            current_subject = self.data.get("subject_name") or ""
        elif self.instance and self.instance.pk:
            current_subject = self.instance.subject_name or ""
        self.fields["subject_name"].choices = [("", "---------")] + _territorial_division_region_choices(current_subject)

    def clean(self):
        cleaned_data = super().clean()
        subject_name = cleaned_data.get("subject_name") or ""
        division = _resolve_territorial_division_by_region_name(subject_name)
        cleaned_data["oktmo_code"] = division.region_code if division else ""
        return cleaned_data

    class Meta:
        model = RussianFederationSubjectCode
        fields = ["subject_name", "oktmo_code", "fns_code", "source"]
        widgets = {
            "fns_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код ФНС России"}),
            "source": forms.TextInput(attrs={"class": "form-control", "placeholder": "Источник"}),
        }


class BusinessEntityRecordForm(forms.ModelForm):
    def clean_name(self):
        return _normalize_guillemets(self.cleaned_data.get("name"))

    class Meta:
        model = BusinessEntityRecord
        fields = ["name", "comment"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование"}),
            "comment": forms.TextInput(attrs={"class": "form-control", "placeholder": "Комментарий"}),
        }


class BusinessEntityIdentifierRecordForm(forms.ModelForm):
    business_entity = forms.ModelChoiceField(
        label="ID-BSN",
        queryset=BusinessEntityRecord.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    identifier_type = forms.ChoiceField(
        label="Тип идентификатора",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    registration_country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    is_active = forms.CharField(
        label="Актуален",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control", "readonly": True, "tabindex": "-1", "style": "background-color:#f8f9fa; color:#6c757d;"}),
    )
    registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        input_formats=["%d.%m.%Y", "%Y-%m-%d"],
        widget=forms.DateInput(
            format="%d.%m.%Y",
            attrs={
                "class": "form-control js-date",
                "placeholder": "дд.мм.гггг",
                "autocomplete": "off",
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        entity_qs = BusinessEntityRecord.objects.order_by("position", "id")
        self.fields["business_entity"].queryset = entity_qs
        self.fields["business_entity"].label_from_instance = _format_bsn_id
        entity_map = {str(obj.pk): _format_bsn_id(obj) for obj in entity_qs}
        if self.is_bound:
            business_entity_value = (self.data.get("business_entity") or "").strip()
            business_entity_label = (self.data.get("business_entity_autocomplete") or "").strip()
            if not business_entity_label and business_entity_value:
                business_entity_label = entity_map.get(business_entity_value, business_entity_value)
        elif self.instance and self.instance.pk and self.instance.business_entity_id:
            business_entity_value = str(self.instance.business_entity_id)
            business_entity_label = entity_map.get(business_entity_value, business_entity_value)
        else:
            business_entity_value = ""
            business_entity_label = ""
        self.business_entity_autocomplete_value = business_entity_value
        self.business_entity_autocomplete_label = business_entity_label
        country_qs = OKSMCountry.objects.order_by("short_name")
        if self.instance and self.instance.pk and self.instance.registration_country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.registration_country_id)).distinct().order_by("short_name")
        self.fields["registration_country"].queryset = country_qs
        self.fields["registration_country"].label_from_instance = (
            lambda obj: obj.short_name
        )
        default_country = None
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.registration_country_id):
            default_country = country_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["registration_country"].initial = default_country.pk

        country_id = None
        if self.is_bound:
            country_id = self.data.get("registration_country")
        elif self.instance and self.instance.pk:
            country_id = self.instance.registration_country_id
        elif default_country is not None:
            country_id = default_country.pk
        registration_date = None
        if self.is_bound:
            registration_date = _parse_form_date(self.data.get("registration_date"))
        elif self.instance and self.instance.pk:
            registration_date = self.instance.registration_date

        current_value = ""
        if self.is_bound:
            current_value = self.data.get("identifier_type") or ""
        elif self.instance and self.instance.pk:
            current_value = self.instance.identifier_type or ""
        self.fields["identifier_type"].choices = _legal_entity_identifier_choices_for_country(country_id, current_value)

        current_region = ""
        if self.is_bound:
            current_region = self.data.get("registration_region") or ""
        elif self.instance and self.instance.pk:
            current_region = self.instance.registration_region or ""
        region_suggestions = _territorial_division_region_choices_for_country(
            country_id,
            current_value=current_region,
            as_of=registration_date,
        )
        self.fields["registration_region"].choices = [("", "---------")] + [(name, name) for name in region_suggestions]
        valid_to_value = None
        if self.is_bound:
            valid_to_value = self.data.get("valid_to") or None
        elif self.instance and self.instance.pk:
            valid_to_value = self.instance.valid_to
        self.fields["is_active"].initial = "true" if not valid_to_value else "false"

    def clean(self):
        cleaned_data = super().clean()
        registration_country = cleaned_data.get("registration_country")
        identifier_type = cleaned_data.get("identifier_type") or ""
        business_entity = cleaned_data.get("business_entity")
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        if registration_country and identifier_type:
            if not LegalEntityIdentifier.objects.filter(
                country=registration_country,
                identifier=identifier_type,
            ).exists():
                self.add_error(
                    "identifier_type",
                    "Значение должно соответствовать выбранной стране регистрации из классификатора идентификаторов юрлиц.",
                )
        if _period_order_is_invalid(valid_from, valid_to, exclusive_end=False):
            self.add_error("valid_to", "Дата \"Действ. до\" не может быть раньше даты \"Действ. от\".")
        if business_entity and not self.errors:
            overlap = _find_period_overlap(
                BusinessEntityIdentifierRecord.objects.filter(business_entity=business_entity).exclude(pk=self.instance.pk),
                valid_from=valid_from,
                valid_to=valid_to,
                start_field="valid_from",
                end_field="valid_to",
                exclusive_end=False,
            )
            if overlap is not None:
                self.add_error(
                    None,
                    _format_registry_overlap_message(
                        registry_label="Реестр идентификаторов",
                        item_suffix="IDN",
                        overlap=overlap,
                        start_field="valid_from",
                        end_field="valid_to",
                        relation_label="ID-BSN",
                    ),
                )
        cleaned_data["registration_code"] = registration_country.code if registration_country else ""
        cleaned_data["is_active"] = cleaned_data.get("valid_to") is None
        return cleaned_data

    class Meta:
        model = BusinessEntityIdentifierRecord
        fields = [
            "business_entity", "registration_country", "registration_region",
            "identifier_type", "number", "registration_date", "valid_from", "valid_to", "is_active",
        ]
        widgets = {
            "number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Номер"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class BusinessEntityAttributeRecordForm(forms.ModelForm):
    class Meta:
        model = BusinessEntityAttributeRecord
        fields = ["attribute_name", "subsection_name"]
        widgets = {
            "attribute_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование атрибута"}),
            "subsection_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование подраздела"}),
        }


class BusinessEntityLegalAddressRecordForm(forms.ModelForm):
    identifier_record = forms.ModelChoiceField(
        label="ID-IDN",
        queryset=BusinessEntityIdentifierRecord.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    registration_country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    is_active = forms.CharField(
        label="Актуален",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control", "readonly": True, "tabindex": "-1", "style": "background-color:#f8f9fa; color:#6c757d;"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        identifier_qs = BusinessEntityIdentifierRecord.objects.select_related("business_entity").order_by("position", "id")
        self.fields["identifier_record"].queryset = identifier_qs
        self.fields["identifier_record"].label_from_instance = _format_idn_id
        identifier_map = {str(obj.pk): _format_idn_id(obj) for obj in identifier_qs}
        if self.is_bound:
            identifier_record_value = (self.data.get("identifier_record") or "").strip()
            identifier_record_label = (self.data.get("identifier_record_autocomplete") or "").strip()
            if not identifier_record_label and identifier_record_value:
                identifier_record_label = identifier_map.get(identifier_record_value, identifier_record_value)
        elif self.instance and self.instance.pk and self.instance.identifier_record_id:
            identifier_record_value = str(self.instance.identifier_record_id)
            identifier_record_label = identifier_map.get(identifier_record_value, identifier_record_value)
        else:
            identifier_record_value = ""
            identifier_record_label = ""
        self.identifier_record_autocomplete_value = identifier_record_value
        self.identifier_record_autocomplete_label = identifier_record_label

        country_qs = OKSMCountry.objects.order_by("short_name")
        if self.instance and self.instance.pk and self.instance.registration_country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.registration_country_id)).distinct().order_by("short_name")
        self.fields["registration_country"].queryset = country_qs
        self.fields["registration_country"].label_from_instance = lambda obj: obj.short_name
        default_country = None
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.registration_country_id):
            default_country = country_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["registration_country"].initial = default_country.pk
        country_id = None
        if self.is_bound:
            country_id = self.data.get("registration_country")
        elif self.instance and self.instance.pk:
            country_id = self.instance.registration_country_id
        elif default_country is not None:
            country_id = default_country.pk
        valid_from_date = None
        if self.is_bound:
            valid_from_date = _parse_form_date(self.data.get("valid_from"))
        elif self.instance and self.instance.pk:
            valid_from_date = self.instance.valid_from
        current_region = ""
        if self.is_bound:
            current_region = self.data.get("registration_region") or ""
        elif self.instance and self.instance.pk:
            current_region = self.instance.registration_region or ""
        region_suggestions = _territorial_division_region_choices_for_country(
            country_id,
            current_value=current_region,
            as_of=valid_from_date,
        )
        region_choices = [("", "---------")]
        region_choices.extend((name, name) for name in region_suggestions)
        self.fields["registration_region"].choices = region_choices
        valid_to_value = None
        if self.is_bound:
            valid_to_value = self.data.get("valid_to") or None
        elif self.instance and self.instance.pk:
            valid_to_value = self.instance.valid_to
        self.fields["is_active"].initial = "true" if not valid_to_value else "false"

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        identifier_record = cleaned_data.get("identifier_record")
        if identifier_record is None:
            identifier_record = _resolve_idn_record_from_autocomplete(
                self.data.get("identifier_record_autocomplete")
            )
            if identifier_record is not None:
                cleaned_data["identifier_record"] = identifier_record
        if identifier_record is None:
            self.add_error("identifier_record", "Выберите значение для поля «ID-IDN».")
        if _period_order_is_invalid(valid_from, valid_to, exclusive_end=False):
            self.add_error("valid_to", "Дата \"Действ. до\" не может быть раньше даты \"Действ. от\".")
        if identifier_record and not self.errors:
            overlap = _find_period_overlap(
                LegalEntityRecord.objects.filter(
                    attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
                    identifier_record=identifier_record,
                ).exclude(pk=self.instance.pk),
                valid_from=valid_from,
                valid_to=valid_to,
                start_field="valid_from",
                end_field="valid_to",
                exclusive_end=False,
            )
            if overlap is not None:
                self.add_error(
                    None,
                    _format_registry_overlap_message(
                        registry_label="Реестр юридических адресов",
                        item_suffix="ATR",
                        overlap=overlap,
                        start_field="valid_from",
                        end_field="valid_to",
                        relation_label="ID-IDN",
                    ),
                )
        cleaned_data["is_active"] = cleaned_data.get("valid_to") is None
        return cleaned_data

    class Meta:
        model = LegalEntityRecord
        fields = [
            "identifier_record", "registration_country", "registration_region", "postal_code", "municipality",
            "settlement", "locality", "district", "street", "building",
            "premise", "premise_part", "valid_from", "valid_to", "is_active",
        ]
        widgets = {
            "postal_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Индекс"}),
            "municipality": forms.TextInput(attrs={"class": "form-control", "placeholder": "Муниципальное образование"}),
            "settlement": forms.TextInput(attrs={"class": "form-control", "placeholder": "Поселение"}),
            "locality": forms.TextInput(attrs={"class": "form-control", "placeholder": "Населенный пункт"}),
            "district": forms.TextInput(attrs={"class": "form-control", "placeholder": "Квартал / район"}),
            "street": forms.TextInput(attrs={"class": "form-control", "placeholder": "Улица"}),
            "building": forms.TextInput(attrs={"class": "form-control", "placeholder": "Здание"}),
            "premise": forms.TextInput(attrs={"class": "form-control", "placeholder": "Помещение"}),
            "premise_part": forms.TextInput(attrs={"class": "form-control", "placeholder": "Часть помещения"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class BusinessEntityRelationRecordForm(forms.ModelForm):
    SPLIT_LIKE_RELATION_TYPES = {"Разделение", "Выделение"}
    RELATION_TYPE_CHOICES = [
        ("", "---------"),
        ("Слияние", "Слияние"),
        ("Присоединение", "Присоединение"),
        ("Разделение", "Разделение"),
        ("Выделение", "Выделение"),
    ]

    from_business_entity_ids = forms.MultipleChoiceField(
        label="От ID-BSN",
        choices=[],
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "d-none"}),
    )
    to_business_entity_ids = forms.MultipleChoiceField(
        label="К ID-BSN",
        choices=[],
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "d-none"}),
    )
    relation_type = forms.ChoiceField(
        label="Тип связи",
        choices=RELATION_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    event_date = forms.DateField(
        label="Дата события",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "placeholder": "Комментарий", "rows": 3}),
    )
    reorganization_event_uid_display = forms.CharField(
        label="ID-REO",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "readonly": True,
                "tabindex": "-1",
                "style": "background-color:#f8f9fa; color:#6c757d;",
            }
        ),
    )
    merge_target_preview = forms.CharField(
        label="К ID-BSN",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "readonly": True,
                "tabindex": "-1",
                "style": "background-color:#f8f9fa; color:#6c757d;",
            }
        ),
    )
    merge_target_name = forms.CharField(
        label="Наименование",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование"}),
    )
    split_target_name = forms.CharField(
        label="Наименование",
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        entity_qs = BusinessEntityRecord.objects.order_by("position", "id")
        entity_choices = [("", "---------")] + [
            (str(obj.pk), _format_bsn_id(obj))
            for obj in entity_qs
        ]
        self.fields["from_business_entity_ids"].choices = entity_choices
        self.fields["to_business_entity_ids"].choices = entity_choices

        event = getattr(self.instance, "event", None) if self.instance and self.instance.pk else None
        event_relations = []
        if event and event.pk:
            event_relations = list(
                event.relations.select_related("to_business_entity").order_by("position", "id")
            )

        def unique_ids(values):
            seen = set()
            result = []
            for value in values:
                if not value or value in seen:
                    continue
                seen.add(value)
                result.append(value)
            return result

        if self.is_bound:
            relation_type_value = (self.data.get("relation_type") or "").strip()
            from_ids = [value for value in self.data.getlist("from_business_entity_ids") if value]
            to_ids = [value for value in self.data.getlist("to_business_entity_ids") if value]
            merge_target_name = (self.data.get("merge_target_name") or "").strip()
            split_existing_ids = self.data.getlist("split_target_existing_ids")
            split_names = self.data.getlist("split_target_names")
        elif self.instance and self.instance.pk:
            relation_type_value = ((event.relation_type if event else "") or "").strip()
            if event_relations:
                from_ids = unique_ids([str(rel.from_business_entity_id) for rel in event_relations])
                to_ids = unique_ids([str(rel.to_business_entity_id) for rel in event_relations])
            else:
                from_ids = [str(self.instance.from_business_entity_id)]
                to_ids = [str(self.instance.to_business_entity_id)]
            merge_target_name = (
                event_relations[0].to_business_entity.name
                if relation_type_value == "Слияние" and event_relations
                else ""
            )
            split_existing_ids = (
                [str(rel.to_business_entity_id) for rel in event_relations]
                if relation_type_value in self.SPLIT_LIKE_RELATION_TYPES
                else []
            )
            split_names = (
                [rel.to_business_entity.name for rel in event_relations]
                if relation_type_value in self.SPLIT_LIKE_RELATION_TYPES
                else []
            )
        else:
            relation_type_value = ""
            from_ids = [""]
            to_ids = [""]
            merge_target_name = ""
            split_existing_ids = []
            split_names = []

        entity_map = {str(obj.pk): _format_bsn_id(obj) for obj in entity_qs}
        self.from_business_entity_rows = [
            {"id": value, "label": entity_map.get(value, value)}
            for value in (from_ids or [""])
        ]
        if relation_type_value == "Присоединение":
            to_ids = to_ids[:1] or [""]
        self.to_business_entity_rows = [
            {"id": value, "label": entity_map.get(value, value)}
            for value in (to_ids or [""])
        ]
        self.merge_target_entity_id = None
        merge_target_preview = _next_bsn_preview_id()
        if relation_type_value == "Слияние" and event_relations:
            self.merge_target_entity_id = str(event_relations[0].to_business_entity_id)
            merge_target_preview = _format_bsn_id(event_relations[0].to_business_entity)
        self.fields["merge_target_preview"].initial = merge_target_preview
        self.fields["merge_target_name"].initial = merge_target_name
        self.fields["relation_type"].initial = relation_type_value
        self.fields["event_date"].initial = event.event_date if event else None
        self.fields["comment"].initial = event.comment if event else ""
        self.is_merge_mode = relation_type_value == "Слияние"
        self.is_split_mode = relation_type_value in self.SPLIT_LIKE_RELATION_TYPES
        self.fields["reorganization_event_uid_display"].initial = (
            (event.reorganization_event_uid or "").strip()
            if event and event.pk
            else _next_reorganization_event_uid_preview()
        )

        row_count = max(len(split_existing_ids), len(split_names), 1)
        preview_offset = 1
        split_target_rows = []
        for idx in range(row_count):
            existing_id = (split_existing_ids[idx] if idx < len(split_existing_ids) else "").strip()
            name = (split_names[idx] if idx < len(split_names) else "").strip()
            if existing_id and existing_id in entity_map:
                preview = entity_map[existing_id]
            else:
                preview = _next_bsn_preview_id(preview_offset)
                preview_offset += 1
            split_target_rows.append({"existing_id": existing_id, "preview": preview, "name": name})
        self.split_target_rows = split_target_rows
        self.split_next_preview_number = (
            (BusinessEntityRecord.objects.aggregate(mx=Max("id")).get("mx") or 0) + preview_offset
        )

    def clean(self):
        cleaned_data = super().clean()
        relation_type = (cleaned_data.get("relation_type") or "").strip()
        from_ids = [value for value in self.data.getlist("from_business_entity_ids") if value]
        to_ids = [value for value in self.data.getlist("to_business_entity_ids") if value]
        merge_target_name = (cleaned_data.get("merge_target_name") or "").strip()
        split_existing_ids = self.data.getlist("split_target_existing_ids")
        split_names = self.data.getlist("split_target_names")
        valid_ids = {
            str(pk)
            for pk in BusinessEntityRecord.objects.values_list("pk", flat=True)
        }

        invalid_from = [value for value in from_ids if value not in valid_ids]
        invalid_to = [value for value in to_ids if value not in valid_ids]

        if invalid_from:
            self.add_error("from_business_entity_ids", "Выберите корректные значения для поля «От ID-BSN».")
        if not from_ids:
            self.add_error("from_business_entity_ids", "Добавьте хотя бы одно значение для поля «От ID-BSN».")
        if relation_type == "Слияние":
            unique_from_ids = list(dict.fromkeys(from_ids))
            if len(unique_from_ids) < 2:
                self.add_error("from_business_entity_ids", "Для типа связи «Слияние» выберите минимум два значения в поле «От ID-BSN».")
            if not merge_target_name:
                self.add_error("merge_target_name", "Заполните поле «Наименование».")
            to_ids = [self.merge_target_entity_id] if self.merge_target_entity_id else []
        else:
            if invalid_to:
                self.add_error("to_business_entity_ids", "Выберите корректные значения для поля «К ID-BSN».")
            if relation_type == "Присоединение" and len(list(dict.fromkeys(to_ids))) > 1:
                self.add_error("to_business_entity_ids", "Для типа связи «Присоединение» выберите только одно значение в поле «К ID-BSN».")
                to_ids = to_ids[:1]
            if relation_type in self.SPLIT_LIKE_RELATION_TYPES and len(list(dict.fromkeys(from_ids))) > 1:
                self.add_error("from_business_entity_ids", f"Для типа связи «{relation_type}» выберите только одно значение в поле «От ID-BSN».")
            if relation_type in self.SPLIT_LIKE_RELATION_TYPES:
                row_count = max(len(split_existing_ids), len(split_names), 1)
                split_rows = []
                invalid_split_ids = []
                missing_split_name = False
                for idx in range(row_count):
                    existing_id = (split_existing_ids[idx] if idx < len(split_existing_ids) else "").strip()
                    name = (split_names[idx] if idx < len(split_names) else "").strip()
                    if existing_id and existing_id not in valid_ids:
                        invalid_split_ids.append(existing_id)
                    if not name:
                        missing_split_name = True
                    split_rows.append({"existing_id": existing_id, "name": name})
                if invalid_split_ids:
                    self.add_error("to_business_entity_ids", "Выберите корректные значения для поля «К ID-BSN».")
                if not split_rows:
                    self.add_error("to_business_entity_ids", "Добавьте хотя бы одно значение для поля «К ID-BSN».")
                if missing_split_name:
                    self.add_error("split_target_name", "Заполните все поля «Наименование».")
                to_ids = [row["existing_id"] for row in split_rows if row["existing_id"]]
                cleaned_data["split_target_rows"] = split_rows
            if not to_ids and relation_type not in self.SPLIT_LIKE_RELATION_TYPES:
                self.add_error("to_business_entity_ids", "Добавьте хотя бы одно значение для поля «К ID-BSN».")

        cleaned_data["from_business_entity_ids"] = from_ids
        cleaned_data["to_business_entity_ids"] = to_ids
        cleaned_data["merge_target_name"] = merge_target_name
        cleaned_data["merge_target_entity_id"] = self.merge_target_entity_id
        cleaned_data["merge_requires_new_target"] = relation_type == "Слияние" and not self.merge_target_entity_id
        cleaned_data.setdefault("split_target_rows", [])
        return cleaned_data

    class Meta:
        model = BusinessEntityRelationRecord
        fields = []


class LivingWageForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Наименование страны (краткое)",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "lw-country-select"}),
    )
    region = forms.ModelChoiceField(
        label="Регион",
        queryset=TerritorialDivision.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "lw-region-select"}),
    )
    amount = forms.CharField(
        label="Величина прожиточного минимума",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "0,00",
            "inputmode": "decimal",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = _active_countries_qs().filter(
            pk__in=TerritorialDivision.objects.values_list("country_id", flat=True).distinct()
        )
        if self.instance and self.instance.pk and self.instance.country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct()
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["region"].label_from_instance = lambda obj: obj.region_name
        if self.instance and self.instance.pk:
            self.fields["region"].queryset = TerritorialDivision.objects.filter(
                country=self.instance.country
            )
        elif "country" in self.data:
            try:
                country_id = int(self.data.get("country"))
                self.fields["region"].queryset = TerritorialDivision.objects.filter(
                    country_id=country_id
                )
            except (ValueError, TypeError):
                pass

    class Meta:
        model = LivingWage
        fields = ["country", "region", "amount", "currency", "approval_date", "expiry_date", "source"]
        widgets = {
            "currency": forms.TextInput(attrs={"class": "form-control", "placeholder": "Валюта", "readonly": True, "tabindex": "-1", "style": "background-color:#f8f9fa; color:#6c757d;"}),
            "approval_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.Textarea(attrs={"class": "form-control", "placeholder": "Источник", "rows": 3}),
        }

    def clean_amount(self):
        raw = self.data.get("amount", "")
        cleaned = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Введите корректное числовое значение.")


class LegalEntityRecordForm(forms.ModelForm):
    identifier_record = forms.ModelChoiceField(
        label="ID-IDN",
        queryset=BusinessEntityIdentifierRecord.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    registration_country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    registration_region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        identifier_qs = BusinessEntityIdentifierRecord.objects.select_related("business_entity").order_by("position", "id")
        self.fields["identifier_record"].queryset = identifier_qs
        self.fields["identifier_record"].label_from_instance = _format_idn_id
        identifier_map = {str(obj.pk): _format_idn_id(obj) for obj in identifier_qs}
        if self.is_bound:
            identifier_record_value = (self.data.get("identifier_record") or "").strip()
            identifier_record_label = (self.data.get("identifier_record_autocomplete") or "").strip()
            if not identifier_record_label and identifier_record_value:
                identifier_record_label = identifier_map.get(identifier_record_value, identifier_record_value)
        elif self.instance and self.instance.pk and self.instance.identifier_record_id:
            identifier_record_value = str(self.instance.identifier_record_id)
            identifier_record_label = identifier_map.get(identifier_record_value, identifier_record_value)
        else:
            identifier_record_value = ""
            identifier_record_label = ""
        self.identifier_record_autocomplete_value = identifier_record_value
        self.identifier_record_autocomplete_label = identifier_record_label

        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.registration_country_id:
            qs = (qs | OKSMCountry.objects.filter(pk=self.instance.registration_country_id)).distinct()
        self.fields["registration_country"].queryset = qs.order_by("short_name")
        self.fields["registration_country"].label_from_instance = lambda obj: obj.short_name

        country_id = None
        if self.is_bound:
            country_id = self.data.get("registration_country")
        elif self.instance and self.instance.pk:
            country_id = self.instance.registration_country_id

        region_suggestions = []
        if country_id:
            seen_names = set()
            for region_name in (
                TerritorialDivision.objects.filter(country_id=country_id)
                .order_by("region_name", "id")
                .values_list("region_name", flat=True)
            ):
                if region_name in seen_names:
                    continue
                seen_names.add(region_name)
                region_suggestions.append(region_name)

        current_region = ""
        if self.is_bound:
            current_region = self.data.get("registration_region") or ""
        elif self.instance and self.instance.pk:
            current_region = self.instance.registration_region or ""
        if current_region and current_region not in region_suggestions:
            region_suggestions.append(current_region)
        region_choices = [("", "---------")]
        region_choices.extend((name, name) for name in region_suggestions)
        self.fields["registration_region"].choices = region_choices

    def clean(self):
        cleaned_data = super().clean()
        identifier_record = cleaned_data.get("identifier_record")
        if identifier_record is None:
            identifier_record = _resolve_idn_record_from_autocomplete(
                self.data.get("identifier_record_autocomplete")
            )
            if identifier_record is not None:
                cleaned_data["identifier_record"] = identifier_record
        if not identifier_record:
            self.add_error("identifier_record", "Выберите значение для поля «ID-IDN».")
        else:
            cleaned_data["identifier"] = identifier_record.identifier_type or ""
            cleaned_data["registration_number"] = identifier_record.number or ""
            cleaned_data["registration_date"] = identifier_record.registration_date
            cleaned_data["registration_country"] = identifier_record.registration_country
        region = (cleaned_data.get("registration_region") or "").strip()
        if region:
            cleaned_data["registration_region"] = region
        elif identifier_record:
            cleaned_data["registration_region"] = (identifier_record.registration_region or "").strip()
        else:
            cleaned_data["registration_region"] = detect_legal_entity_region_by_identifier(
                cleaned_data.get("identifier") or "",
                cleaned_data.get("registration_number") or "",
            )
        valid_from = cleaned_data.get("name_received_date")
        valid_to = cleaned_data.get("name_changed_date")
        if _period_order_is_invalid(valid_from, valid_to, exclusive_end=True):
            self.add_error("name_changed_date", "Дата \"Действ. до\" должна быть позже даты \"Действ. от\".")
        identifier_record_id = identifier_record.pk if identifier_record else None
        if identifier_record_id and not self.errors:
            overlap = _find_period_overlap(
                LegalEntityRecord.objects.filter(
                    attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                    identifier_record_id=identifier_record_id,
                ).exclude(pk=self.instance.pk),
                valid_from=valid_from,
                valid_to=valid_to,
                start_field="name_received_date",
                end_field="name_changed_date",
                exclusive_end=True,
            )
            if overlap is not None:
                self.add_error(
                    None,
                    _format_registry_overlap_message(
                        registry_label="Реестр наименований",
                        item_suffix="ATR",
                        overlap=overlap,
                        start_field="name_received_date",
                        end_field="name_changed_date",
                        relation_label="ID-IDN",
                    ),
                )
        return cleaned_data

    class Meta:
        model = LegalEntityRecord
        fields = [
            "identifier_record", "short_name", "full_name", "identifier", "registration_number",
            "registration_date", "registration_country", "registration_region",
            "name_received_date", "name_changed_date",
        ]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое наименование"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Полное наименование"}),
            "identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Идентификатор"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Регистрационный номер"}),
            "registration_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "name_received_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "name_changed_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
