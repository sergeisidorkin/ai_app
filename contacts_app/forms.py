import json
from datetime import date as date_type

from django import forms
from django.db.models import Q
from phonenumbers import (
    AsYouTypeFormatter,
    NumberParseException,
    PhoneNumberFormat,
    PhoneNumberType,
    country_code_for_region,
    example_number_for_type,
    format_number,
    is_possible_number,
    national_significant_number,
    parse,
)

from classifiers_app.models import LegalEntityRecord, OKSMCountry, PhysicalEntityIdentifier, TerritorialDivision
from classifiers_app.numcap import lookup_ru_landline
from group_app.models import GroupMember

from .models import (
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    ResidenceAddressRecord,
    USER_KIND_EMPLOYEE,
    USER_KIND_EXTERNAL,
)


class LegacyCompatibleTypedChoiceField(forms.TypedChoiceField):
    def clean(self, value):
        if value == "on":
            value = "True"
        return super().clean(value)


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
    return f"{_format_prs_id(obj)} {display_name}"


def _physical_identifier_for_country(country_id):
    if not country_id:
        return ""
    return (
        PhysicalEntityIdentifier.objects
        .filter(country_id=country_id)
        .order_by("position", "id")
        .values_list("identifier", flat=True)
        .first()
        or ""
    )


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


def _country_region(country):
    return str(getattr(country, "alpha2", "") or "").strip().upper()


def _dial_code_for_country(country):
    region = _country_region(country)
    if not region:
        return ""
    dial_code = country_code_for_region(region)
    return f"+{dial_code}" if dial_code else ""


def _phone_placeholder_for_country(country):
    return _phone_placeholder_for_country_by_type(country, PhoneRecord.PHONE_TYPE_MOBILE)


def _phone_placeholder_for_country_by_type(country, phone_type):
    region = _country_region(country)
    if not region:
        return ""
    if phone_type == PhoneRecord.PHONE_TYPE_LANDLINE:
        if region == "RU":
            return "(495) 123-45-67"
        example_number = example_number_for_type(region, PhoneNumberType.FIXED_LINE) or example_number_for_type(
            region,
            PhoneNumberType.FIXED_LINE_OR_MOBILE,
        )
        if not example_number:
            return ""
        try:
            formatted = format_number(example_number, PhoneNumberFormat.NATIONAL)
            if region == "RU" and formatted.startswith("8"):
                return formatted[1:].strip()
            return formatted
        except Exception:
            return ""
    example_number = example_number_for_type(region, PhoneNumberType.MOBILE) or example_number_for_type(
        region,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
    )
    if not example_number:
        return ""
    try:
        return _format_local_phone_number(example_number, region)
    except Exception:
        return ""


def _strip_phone_country_code(phone_number, dial_code):
    value = str(phone_number or "").strip()
    code = str(dial_code or "").strip()
    if not value or not code:
        return value
    compact_value = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    compact_code = code.replace(" ", "")
    digits_code = compact_code.lstrip("+")
    if compact_value.startswith(compact_code):
        return value[len(code):].strip(" -()")
    if not digits_code or not compact_value.startswith(digits_code):
        return value
    # Leading digits match the dial code, but they might also be the first
    # digit(s) of a local number (e.g. "705 186-10-36" for +7 RU). Reparse the
    # compact value as an international number: only treat the prefix as a
    # country code when the remainder forms a plausible national number for
    # that country — otherwise we'd truncate a valid local number and leave
    # digit-only international input (e.g. "14155551234" for +1 US) unstripped.
    remaining_digits = compact_value[len(digits_code):]
    if not remaining_digits:
        return value
    try:
        parsed_number = parse(f"+{digits_code}{remaining_digits}", None)
    except NumberParseException:
        return value
    if not is_possible_number(parsed_number):
        return value
    if f"+{parsed_number.country_code}" != compact_code:
        return value
    return value[len(digits_code):].strip(" -()")


def _strip_phone_national_prefix(phone_number, region):
    value = str(phone_number or "").strip()
    normalized_region = str(region or "").strip().upper()
    if normalized_region != "RU":
        return value
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        return digits[1:]
    return value


def _format_ru_local_number(raw_value):
    digits = "".join(char for char in str(raw_value or "") if char.isdigit())
    if len(digits) >= 11 and digits[0] in {"7", "8"}:
        digits = digits[1:]
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) <= 3:
        return f"({digits}"
    if len(digits) <= 6:
        return f"({digits[:3]}) {digits[3:]}"
    if len(digits) <= 8:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"


def _format_local_phone_number(parsed_number, region):
    normalized_region = str(region or "").strip().upper()
    if normalized_region == "RU":
        return _format_ru_local_number(national_significant_number(parsed_number))
    formatter = AsYouTypeFormatter(normalized_region)
    formatted = ""
    for digit in national_significant_number(parsed_number):
        formatted = formatter.input_digit(digit)
    return formatted or format_number(parsed_number, PhoneNumberFormat.NATIONAL)


def _position_organization_meta(short_name):
    value = str(short_name or "").strip()
    if not value:
        return {"identifier": "", "registration_number": ""}
    group_member = (
        GroupMember.objects
        .filter(short_name=value)
        .order_by("position", "id")
        .first()
    )
    if group_member:
        return {
            "identifier": str(group_member.identifier or "").strip(),
            "registration_number": str(group_member.registration_number or "").strip(),
        }
    name_record = (
        LegalEntityRecord.objects.select_related("identifier_record")
        .filter(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            short_name=value,
        )
        .order_by("-is_active", "position", "id")
        .first()
    )
    if not name_record:
        return {"identifier": "", "registration_number": ""}
    identifier = (
        (getattr(name_record.identifier_record, "identifier_type", "") if getattr(name_record, "identifier_record_id", None) else "")
        or name_record.identifier
        or ""
    )
    registration_number = (
        (getattr(name_record.identifier_record, "number", "") if getattr(name_record, "identifier_record_id", None) else "")
        or name_record.registration_number
        or ""
    )
    return {
        "identifier": str(identifier).strip(),
        "registration_number": str(registration_number).strip(),
    }


class PersonRecordForm(forms.ModelForm):
    birth_date = forms.DateField(
        label="Дата рождения",
        required=False,
        input_formats=["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"],
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            },
            format="%Y-%m-%d",
        ),
    )

    MANAGED_PERSON_KINDS = {USER_KIND_EMPLOYEE, USER_KIND_EXTERNAL}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_kind in self.MANAGED_PERSON_KINDS:
            for field_name in ("last_name", "first_name", "middle_name"):
                field = self.fields[field_name]
                field.disabled = True
                field.widget.attrs["readonly"] = True
                field.widget.attrs["tabindex"] = "-1"
                field.widget.attrs["class"] = field.widget.attrs.get("class", "") + " readonly-field"

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk and self.instance.user_kind in self.MANAGED_PERSON_KINDS:
            cleaned_data["last_name"] = self.instance.last_name
            cleaned_data["first_name"] = self.instance.first_name
            cleaned_data["middle_name"] = self.instance.middle_name
        return cleaned_data

    class Meta:
        model = PersonRecord
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "full_name_genitive",
            "gender",
            "birth_date",
        ]
        widgets = {
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Фамилия"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Имя"}),
            "middle_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отчество"}),
            "full_name_genitive": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "ФИО (полное) в родительном падеже"}
            ),
            "gender": forms.Select(attrs={"class": "form-select"}),
        }


class PositionRecordForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.HiddenInput(),
    )
    organization_short_name = forms.CharField(
        label="Наименование организации (краткое)",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "psn-organization-input",
                "placeholder": "Искать по наименованию и регистрационному номеру",
                "autocomplete": "off",
            }
        ),
        required=False,
    )
    organization_identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control readonly-field",
                "id": "psn-organization-identifier-field",
                "placeholder": "Идентификатор",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )
    organization_registration_number = forms.CharField(
        label="Регистрационный номер",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control readonly-field",
                "id": "psn-organization-registration-number-field",
                "placeholder": "Регистрационный номер",
                "readonly": True,
                "tabindex": "-1",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.valid_from):
            self.fields["valid_from"].initial = date_type.today()
        if self.instance and self.instance.pk and self.instance.is_user_managed:
            self.fields["organization_short_name"].widget.attrs["readonly"] = True
            self.fields["organization_short_name"].widget.attrs["tabindex"] = "-1"
            self.fields["organization_short_name"].widget.attrs["class"] += " readonly-field"
            self.fields["job_title"].widget.attrs["readonly"] = True
            self.fields["job_title"].widget.attrs["tabindex"] = "-1"
            self.fields["job_title"].widget.attrs["class"] += " readonly-field"

        current_value = ""
        if self.is_bound:
            current_value = (self.data.get("organization_short_name") or "").strip()
        elif self.instance:
            current_value = self.instance.organization_short_name or ""
        organization_meta = _position_organization_meta(current_value)
        if self.is_bound:
            self.initial["organization_identifier"] = (self.data.get("organization_identifier") or organization_meta["identifier"]).strip()
            self.initial["organization_registration_number"] = (
                self.data.get("organization_registration_number") or organization_meta["registration_number"]
            ).strip()
        else:
            self.initial["organization_identifier"] = organization_meta["identifier"]
            self.initial["organization_registration_number"] = organization_meta["registration_number"]

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk and self.instance.is_user_managed:
            cleaned_data["person"] = self.instance.person
            cleaned_data["organization_short_name"] = self.instance.organization_short_name
            cleaned_data["job_title"] = self.instance.job_title
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


class PhoneRecordForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.HiddenInput(),
    )
    phone_type = forms.ChoiceField(
        label="Тип связи",
        choices=PhoneRecord.PHONE_TYPE_CHOICES,
        required=False,
        initial=PhoneRecord.PHONE_TYPE_MOBILE,
        widget=forms.Select(attrs={"class": "form-select", "id": "tel-type-select"}),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "tel-country-select"}),
        required=False,
    )
    extension = forms.CharField(
        label="Добавочный номер",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "tel-extension-field",
                "placeholder": "Добавочный номер",
                "inputmode": "numeric",
            }
        ),
    )
    region = forms.CharField(
        label="Регион",
        required=False,
        widget=forms.TextInput(
            attrs={
                        "class": "form-control readonly-field",
                "id": "tel-region-field",
                "placeholder": "Регион",
                        "readonly": True,
                        "tabindex": "-1",
            }
        ),
    )
    is_primary = LegacyCompatibleTypedChoiceField(
        label="Основной",
        required=False,
        initial=True,
        choices=((True, "Да"), (False, "Нет")),
        coerce=lambda value: value in (True, "True", "true", "1", 1, "on"),
        empty_value=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = date_type.today()
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label

        countries_qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_id:
            countries_qs = (countries_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by(
                "short_name", "position", "id"
            )
        self.fields["country"].queryset = countries_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.country_id):
            default_country = countries_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["country"].initial = default_country.pk
        self.country_meta_json = json.dumps(
            {
                str(obj.pk): {
                    "iso2": str(obj.alpha2 or "").strip().lower(),
                    "dialCode": _dial_code_for_country(obj),
                    "mobilePlaceholder": _phone_placeholder_for_country_by_type(obj, PhoneRecord.PHONE_TYPE_MOBILE),
                    "landlinePlaceholder": _phone_placeholder_for_country_by_type(obj, PhoneRecord.PHONE_TYPE_LANDLINE),
                }
                for obj in countries_qs
                if getattr(obj, "pk", None)
            },
            ensure_ascii=False,
        )
        selected_country_id = None
        if self.is_bound:
            selected_country_id = self.data.get("country")
        elif self.instance and self.instance.pk and self.instance.country_id:
            selected_country_id = self.instance.country_id
        else:
            selected_country_id = self.fields["country"].initial
        try:
            selected_country = countries_qs.filter(pk=selected_country_id).first()
        except (TypeError, ValueError):
            selected_country = None
        selected_meta = json.loads(self.country_meta_json).get(str(selected_country_id), {})
        self.show_region_field = _country_region(selected_country) == "RU"
        self.initial_country_iso2 = str(selected_meta.get("iso2", "") or "").strip().lower()
        if (
            not self.is_bound
            and self.instance
            and self.instance.pk
            and self.show_region_field
            and not (self.instance.region or "").strip()
            and (self.instance.phone_number or "").strip()
        ):
            lookup = lookup_ru_landline(self.instance.phone_number)
            if lookup.exact and lookup.region:
                self.initial["region"] = lookup.region
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.code):
            self.fields["code"].initial = selected_meta.get("dialCode", "")
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.valid_from):
            self.fields["valid_from"].initial = today
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.fields["is_primary"].initial = True

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        country = cleaned_data.get("country")
        phone_type = cleaned_data.get("phone_type") or PhoneRecord.PHONE_TYPE_MOBILE
        phone_number = str(cleaned_data.get("phone_number") or "").strip()
        if not (self.instance and self.instance.pk) and "is_primary" not in self.data:
            cleaned_data["is_primary"] = True
        cleaned_data["phone_type"] = phone_type
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", 'Дата "Действ. до" не может быть раньше даты "Действ. от".')
        cleaned_data["code"] = _dial_code_for_country(country)
        if phone_type != PhoneRecord.PHONE_TYPE_LANDLINE:
            cleaned_data["extension"] = ""
            cleaned_data["region"] = ""
        else:
            cleaned_data["region"] = ""
        if phone_number:
            phone_number = _strip_phone_country_code(phone_number, cleaned_data["code"])
            if phone_type == PhoneRecord.PHONE_TYPE_LANDLINE:
                region = _country_region(country)
                if region == "RU":
                    lookup = lookup_ru_landline(phone_number)
                    if not lookup.exact:
                        self.add_error(
                            "phone_number",
                            "Для стационарного номера РФ нужен полный номер с однозначно определяемым регионом.",
                        )
                        cleaned_data["phone_number"] = phone_number
                        cleaned_data["region"] = ""
                        return cleaned_data
                    cleaned_data["phone_number"] = lookup.formatted_number
                    cleaned_data["region"] = lookup.region
                    return cleaned_data
                cleaned_data["phone_number"] = phone_number
                cleaned_data["region"] = ""
                return cleaned_data
            region = _country_region(country)
            phone_number = _strip_phone_national_prefix(phone_number, region)
            cleaned_data["phone_number"] = phone_number
            if not region:
                return cleaned_data
            if region == "RU":
                lookup = lookup_ru_landline(phone_number)
                if lookup.exact:
                    cleaned_data["region"] = lookup.region
            try:
                parsed_number = parse(phone_number, region)
            except NumberParseException:
                return cleaned_data
            if not is_possible_number(parsed_number):
                return cleaned_data
            cleaned_data["code"] = f"+{parsed_number.country_code}"
            cleaned_data["phone_number"] = _format_local_phone_number(parsed_number, region)
        return cleaned_data

    class Meta:
        model = PhoneRecord
        fields = [
            "person",
            "phone_type",
            "country",
            "code",
            "region",
            "phone_number",
            "is_primary",
            "extension",
            "valid_from",
            "valid_to",
        ]
        widgets = {
            "code": forms.TextInput(attrs={
                "class": "form-control readonly-field",
                "placeholder": "Код",
                "id": "tel-code-field",
                "readonly": True,
                "tabindex": "-1",
            }),
            "phone_number": forms.TextInput(attrs={"class": "form-control", "id": "tel-phone-field", "autocomplete": "tel"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class EmailRecordForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.HiddenInput(),
    )
    email = forms.EmailField(
        label="Электронная почта",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@example.com", "autocomplete": "email"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.valid_from):
            self.fields["valid_from"].initial = date_type.today()
        if self.instance and self.instance.pk and self.instance.is_user_managed:
            self.fields["email"].widget.attrs["readonly"] = True
            self.fields["email"].widget.attrs["tabindex"] = "-1"
            self.fields["email"].widget.attrs["class"] += " readonly-field"

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk and self.instance.is_user_managed:
            cleaned_data["person"] = self.instance.person
            cleaned_data["email"] = self.instance.email
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", 'Дата "Действ. до" не может быть раньше даты "Действ. от".')
        return cleaned_data

    class Meta:
        model = EmailRecord
        fields = [
            "person",
            "email",
            "valid_from",
            "valid_to",
        ]
        widgets = {
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class ResidenceAddressRecordForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.HiddenInput(),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "adr-country-select"}),
        required=False,
    )
    region = forms.ChoiceField(
        label="Регион",
        choices=[("", "---------")],
        widget=forms.Select(attrs={"class": "form-select", "id": "adr-region-select"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label

        countries_qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_id:
            countries_qs = (countries_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by(
                "short_name", "position", "id"
            )
        self.fields["country"].queryset = countries_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.country_id):
            default_country = countries_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["country"].initial = default_country.pk

        country_id = None
        if self.is_bound:
            country_id = self.data.get("country")
        elif self.instance and self.instance.pk and self.instance.country_id:
            country_id = self.instance.country_id
        else:
            country_id = self.fields["country"].initial

        current_region = ""
        if self.is_bound:
            current_region = self.data.get("region") or ""
        elif self.instance and self.instance.pk:
            current_region = self.instance.region or ""
        self.fields["region"].choices = [("", "---------")] + _territorial_division_region_choices_for_country(
            country_id,
            current_value=current_region,
        )

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        country = cleaned_data.get("country")
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", 'Дата "Действ. до" не может быть раньше даты "Действ. от".')
        if not country:
            cleaned_data["region"] = ""
        return cleaned_data

    class Meta:
        model = ResidenceAddressRecord
        fields = [
            "person",
            "country",
            "region",
            "postal_code",
            "locality",
            "street",
            "building",
            "premise",
            "premise_part",
            "valid_from",
            "valid_to",
        ]
        widgets = {
            "postal_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Индекс"}),
            "locality": forms.TextInput(attrs={"class": "form-control", "placeholder": "Населенный пункт"}),
            "street": forms.TextInput(attrs={"class": "form-control", "placeholder": "Улица"}),
            "building": forms.TextInput(attrs={"class": "form-control", "placeholder": "Здание"}),
            "premise": forms.TextInput(attrs={"class": "form-control", "placeholder": "Помещение"}),
            "premise_part": forms.TextInput(attrs={"class": "form-control", "placeholder": "Часть помещения"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


class CitizenshipRecordForm(forms.ModelForm):
    STATUS_TEMPORARY_STAY = "Временное пребывание"
    STATUS_RESIDENCE_PERMIT = "Вид на жительство"
    STATUS_CITIZENSHIP = "Гражданство"
    STATUS_CHOICES = [
        ("", "---------"),
        (STATUS_TEMPORARY_STAY, STATUS_TEMPORARY_STAY),
        (STATUS_RESIDENCE_PERMIT, STATUS_RESIDENCE_PERMIT),
        (STATUS_CITIZENSHIP, STATUS_CITIZENSHIP),
    ]

    person = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        widget=forms.HiddenInput(),
    )
    birth_date = forms.DateField(
        label="Дата рождения",
        required=False,
        disabled=True,
        widget=forms.DateInput(
            attrs={
                "class": "form-control readonly-field",
                "type": "date",
                "readonly": True,
                "tabindex": "-1",
                "id": "ctz-birth-date-field",
            }
        ),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "ctz-country-select"}),
        required=False,
    )
    status = forms.ChoiceField(
        label="Статус",
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people_qs = PersonRecord.objects.order_by("position", "id")
        self.fields["person"].queryset = people_qs
        self.fields["person"].label_from_instance = _person_label
        selected_person_id = self._resolve_person_id()
        self.fields["birth_date"].initial = self._person_birth_date(selected_person_id)

        countries_qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_id:
            countries_qs = (countries_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by(
                "short_name", "position", "id"
            )
        self.fields["country"].queryset = countries_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.country_id):
            default_country = countries_qs.filter(code="643").order_by("position", "id").first()
            if default_country is not None:
                self.fields["country"].initial = default_country.pk
        selected_country_id = None
        if self.is_bound:
            selected_country_id = self.data.get("country")
        elif self.instance and self.instance.pk and self.instance.country_id:
            selected_country_id = self.instance.country_id
        else:
            selected_country_id = self.fields["country"].initial
        if not self.is_bound and not (self.instance and self.instance.pk and self.instance.identifier):
            self.fields["identifier"].initial = _physical_identifier_for_country(selected_country_id)

    def _resolve_person_id(self):
        if self.data:
            value = self.data.get("person")
            if value:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        if self.instance and self.instance.pk and self.instance.person_id:
            return self.instance.person_id
        value = self.initial.get("person")
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _person_birth_date(person_id):
        if not person_id:
            return None
        return (
            PersonRecord.objects
            .filter(pk=person_id)
            .values_list("birth_date", flat=True)
            .first()
        )

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")
        country = cleaned_data.get("country")
        if valid_from and valid_to and valid_to < valid_from:
            self.add_error("valid_to", 'Дата "Действ. до" не может быть раньше даты "Действ. от".')
        cleaned_data["identifier"] = _physical_identifier_for_country(getattr(country, "pk", None))
        return cleaned_data

    class Meta:
        model = CitizenshipRecord
        fields = [
            "person",
            "country",
            "status",
            "identifier",
            "number",
            "valid_from",
            "valid_to",
        ]
        widgets = {
            "identifier": forms.TextInput(attrs={
                "class": "form-control readonly-field",
                "placeholder": "Идентификатор",
                "readonly": True,
                "tabindex": "-1",
                "id": "ctz-identifier-field",
            }),
            "number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Номер"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
