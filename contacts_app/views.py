import csv
import io
import json
from datetime import date as date_type, datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from classifiers_app.models import OKSMCountry, PhysicalEntityIdentifier
from classifiers_app.numcap import lookup_ru_landline

from .forms import (
    CitizenshipRecordForm,
    EmailRecordForm,
    PersonRecordForm,
    PhoneRecordForm,
    PositionRecordForm,
    ResidenceAddressRecordForm,
    SpecialtyRecordForm,
    _dial_code_for_country,
    _physical_identifier_for_country,
)
from .models import (
    PERSON_GENDER_CHOICES,
    USER_KIND_CHOICES,
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    ResidenceAddressRecord,
    SpecialtyRecord,
)
from experts_app.models import ExpertSpecialty

PRS_TABLE_TEMPLATE = "contacts_app/prs_table_partial.html"
PRS_FORM_TEMPLATE = "contacts_app/prs_form.html"
CTZ_TABLE_TEMPLATE = "contacts_app/ctz_table_partial.html"
CTZ_FORM_TEMPLATE = "contacts_app/ctz_form.html"
PSN_TABLE_TEMPLATE = "contacts_app/psn_table_partial.html"
PSN_FORM_TEMPLATE = "contacts_app/psn_form.html"
TEL_TABLE_TEMPLATE = "contacts_app/tel_table_partial.html"
TEL_FORM_TEMPLATE = "contacts_app/tel_form.html"
EML_TABLE_TEMPLATE = "contacts_app/eml_table_partial.html"
EML_FORM_TEMPLATE = "contacts_app/eml_form.html"
SPC_TABLE_TEMPLATE = "contacts_app/spc_table_partial.html"
SPC_FORM_TEMPLATE = "contacts_app/spc_form.html"
ADR_TABLE_TEMPLATE = "contacts_app/adr_table_partial.html"
ADR_FORM_TEMPLATE = "contacts_app/adr_form.html"
CONTACTS_PAGE_SIZE = 50
PRS_CSV_HEADERS = [
    "ID-PRS",
    "Фамилия",
    "Имя",
    "Отчество",
    "ФИО (полное) в родительном падеже",
    "Пол",
    "Дата рождения",
    "Пользователь",
]
CTZ_CSV_HEADERS = [
    "ID-CTZ",
    "ID-PRS",
    "Страна",
    "Статус",
    "Идентификатор",
    "Номер",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
ADR_CSV_HEADERS = [
    "ID-ADR",
    "ID-PRS",
    "Страна",
    "Регион",
    "Индекс",
    "Населенный пункт",
    "Улица",
    "Здание",
    "Помещение",
    "Часть помещения",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
PSN_CSV_HEADERS = [
    "ID-PSN",
    "ID-PRS",
    "Наименование организации (краткое)",
    "Должность",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
TEL_CSV_HEADERS = [
    "ID-TEL",
    "ID-PRS",
    "Страна",
    "Тип",
    "Номер телефона",
    "Основной",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
EML_CSV_HEADERS = [
    "ID-EML",
    "ID-PRS",
    "Электронная почта",
    "Пользователь",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
SPC_CSV_HEADERS = [
    "ID-SPC",
    "ID-PRS",
    "Специальность",
    "Пользователь",
    "Действ. от",
    "Действ. до",
    "Запись",
    "Автор записи",
    "Источник",
]
PRS_TABLE_URL = "/contacts/prs/table/"
CTZ_TABLE_URL = "/contacts/ctz/table/"
PSN_TABLE_URL = "/contacts/psn/table/"
TEL_TABLE_URL = "/contacts/tel/table/"
EML_TABLE_URL = "/contacts/eml/table/"
SPC_TABLE_URL = "/contacts/spc/table/"
ADR_TABLE_URL = "/contacts/adr/table/"
PRS_FILTER_OPTIONS_URL = "/contacts/prs/filter-options/"
CONTACTS_HX_TRIGGER_HEADER = "HX-Trigger"
CONTACTS_HX_EVENT = "contacts-updated"


def staff_required(user):
    return user.is_authenticated and user.is_staff


def _contacts_record_author(user):
    full = f"{user.first_name} {user.last_name}".strip() if user else ""
    return full if full else getattr(user, "email", "") or getattr(user, "username", "")


def _set_contacts_trigger(response, *, source, affected=None):
    response[CONTACTS_HX_TRIGGER_HEADER] = json.dumps(
        {
            CONTACTS_HX_EVENT: {
                "source": source,
                "affected": affected or [],
            }
        },
        ensure_ascii=False,
    )
    return response


def _req_param(request, name):
    value = request.GET.get(name)
    if value is None:
        value = request.POST.get(name)
    return value


def _request_param_lists(request):
    keys = ("prs_ids", "prs_page", "ctz_page", "adr_page", "psn_page", "tel_page", "eml_page", "spc_page")
    data = {}
    for key in keys:
        values = request.GET.getlist(key)
        if not values:
            values = request.POST.getlist(key)
        if values:
            data[key] = values
    return data


def _req_list_param(request, name):
    values = []
    for raw in request.GET.getlist(name):
        values.extend(str(raw).split(","))
    for raw in request.POST.getlist(name):
        values.extend(str(raw).split(","))
    return [value.strip() for value in values if str(value).strip()]


def _selected_person_ids(request):
    result = []
    for raw in _req_list_param(request, "prs_ids"):
        if raw.isdigit():
            result.append(int(raw))
    return result


def _single_selected_person_id(request):
    person_ids = _selected_person_ids(request)
    return person_ids[0] if len(person_ids) == 1 else None


def _person_user_kind_display_by_id(person_id):
    if not person_id:
        return ""
    try:
        person_pk = int(person_id)
    except (TypeError, ValueError):
        return ""
    person = PersonRecord.objects.only("id", "user_kind").filter(pk=person_pk).first()
    return person.get_user_kind_display() if person else ""


def _build_partial_url(base_url, params):
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params, doseq=True)}"


def _paginate_queryset(request, queryset, *, item_key, page_param, partial_url, target):
    paginator = Paginator(queryset, CONTACTS_PAGE_SIZE)
    page_obj = paginator.get_page(_req_param(request, page_param))
    params = _request_param_lists(request)
    params.pop(page_param, None)

    def page_url(page_number):
        page_params = {key: list(values) for key, values in params.items()}
        page_params[page_param] = [str(page_number)]
        return _build_partial_url(partial_url, page_params)

    pages = []
    if paginator.num_pages > 1:
        for entry in paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1):
            if isinstance(entry, int):
                pages.append(
                    {
                        "number": entry,
                        "current": entry == page_obj.number,
                        "url": page_url(entry),
                    }
                )
            else:
                pages.append({"ellipsis": True})

    return {
        item_key: page_obj.object_list,
        "page_obj": page_obj,
        "pagination": {
            "show": paginator.num_pages > 1,
            "target": target,
            "swap": "innerHTML",
            "prev_url": page_url(page_obj.previous_page_number()) if page_obj.has_previous() else "",
            "next_url": page_url(page_obj.next_page_number()) if page_obj.has_next() else "",
            "pages": pages,
            "page_param": page_param,
            "page_input_id": page_param.replace("_page", "") + "-page-input",
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "start_index": page_obj.start_index() if paginator.count else 0,
            "end_index": page_obj.end_index() if paginator.count else 0,
        },
    }


def _serialize_person_filter_item(item):
    formatted_id = f"{item.pk:05d}-PRS"
    display_name = (item.display_name or "").strip()
    return {
        "id": item.pk,
        "formatted_id": formatted_id,
        "display_name": display_name,
        "summary_label": _person_summary_label(item),
        "label": f"{formatted_id} {display_name}".strip(),
        "last_name": (item.last_name or "").strip(),
        "first_name": (item.first_name or "").strip(),
        "middle_name": (item.middle_name or "").strip(),
    }


def _person_summary_label(item):
    last_name = str(getattr(item, "last_name", "") or "").strip()
    first_name = str(getattr(item, "first_name", "") or "").strip()
    middle_name = str(getattr(item, "middle_name", "") or "").strip()
    initials = ""
    if first_name:
        initials += first_name[:1] + "."
    if middle_name:
        initials += middle_name[:1] + "."
    summary = f"{last_name} {initials}".strip()
    return summary or f"{item.pk:05d}-PRS"


def _person_record_label(person_id):
    if not person_id:
        return ""
    try:
        person_id = int(person_id)
    except (TypeError, ValueError):
        return ""
    item = PersonRecord.objects.filter(pk=person_id).first()
    if item is None:
        return ""
    return f"{item.formatted_id} {item.display_name}".strip()


def _person_picker_context(person_id):
    return {
        "prs_filter_options_url": reverse("prs_filter_options"),
        "person_record_label": _person_record_label(person_id),
    }


def _person_filter_items(*, ids=None):
    items = []
    queryset = PersonRecord.objects.order_by("position", "id")
    if ids:
        queryset = queryset.filter(pk__in=ids)
    for item in queryset.iterator():
        items.append(_serialize_person_filter_item(item))
    return items


def _person_filter_search_items(query: str):
    query_normalized = (query or "").strip().lower()
    if not query_normalized:
        return []
    items = []
    queryset = PersonRecord.objects.order_by("position", "id")
    for item in queryset.iterator():
        formatted_id = f"{item.pk:05d}-PRS"
        display_name = (item.display_name or "").strip()
        haystack = f"{formatted_id} {display_name}".lower()
        if query_normalized not in haystack:
            continue
        items.append(
            {
                "id": item.pk,
                "formatted_id": formatted_id,
                "display_name": display_name,
                "summary_label": _person_summary_label(item),
                "label": f"{formatted_id} {display_name}".strip(),
                "last_name": (item.last_name or "").strip(),
                "first_name": (item.first_name or "").strip(),
                "middle_name": (item.middle_name or "").strip(),
            }
        )
    return items


def _validation_error(message: str, status: int = 409):
    return HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")


def _ctz_identifier_for_country(country_id):
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


def _prs_birth_date(person_id):
    if not person_id:
        return None
    return (
        PersonRecord.objects
        .filter(pk=person_id)
        .values_list("birth_date", flat=True)
        .first()
    )


def _expert_registration_address_payload(person_id, country_id):
    empty_payload = {
        "postal_code": "",
        "region": "",
        "locality": "",
        "street": "",
        "building": "",
        "premise": "",
        "premise_part": "",
        "valid_from": "",
    }
    if not person_id or not country_id:
        return empty_payload
    try:
        person_id = int(person_id)
        country_id = int(country_id)
    except (TypeError, ValueError):
        return empty_payload

    from experts_app.models import ExpertContractDetails

    item = (
        ExpertContractDetails.objects.select_related("citizenship_record")
        .filter(
            citizenship_record__person_id=person_id,
            citizenship_record__country_id=country_id,
        )
        .order_by("-citizenship_record__is_active", "citizenship_record__position", "citizenship_record__id", "id")
        .first()
    )
    if item is None:
        return empty_payload
    return {
        "postal_code": item.registration_postal_code or "",
        "region": item.registration_region or "",
        "locality": item.registration_locality or "",
        "street": item.registration_street or "",
        "building": item.registration_building or "",
        "premise": item.registration_premise or "",
        "premise_part": item.registration_premise_part or "",
        "valid_from": item.registration_date.isoformat() if item.registration_date else "",
    }


def _next_prs_position():
    return (PersonRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_psn_position():
    return (PositionRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_ctz_position():
    return (CitizenshipRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_tel_position():
    return (PhoneRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_eml_position():
    return (EmailRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_spc_position():
    return (SpecialtyRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_adr_position():
    return (ResidenceAddressRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _normalize_prs_positions():
    items = PersonRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            PersonRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_psn_positions():
    items = PositionRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            PositionRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_ctz_positions():
    items = CitizenshipRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            CitizenshipRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_tel_positions():
    items = PhoneRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            PhoneRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_eml_positions():
    items = EmailRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            EmailRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_spc_positions():
    items = SpecialtyRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            SpecialtyRecord.objects.filter(pk=item.pk).update(position=idx)


def _normalize_adr_positions():
    items = ResidenceAddressRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ResidenceAddressRecord.objects.filter(pk=item.pk).update(position=idx)


def _prs_queryset(request):
    queryset = PersonRecord.objects.order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(pk__in=person_ids)
    return queryset


def _prs_context(request):
    return _paginate_queryset(
        request,
        _prs_queryset(request),
        item_key="prs_items",
        page_param="prs_page",
        partial_url=PRS_TABLE_URL,
        target="#contacts-persons-table-wrap",
    )


def _psn_queryset(request):
    queryset = PositionRecord.objects.select_related("person").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _psn_context(request):
    return _paginate_queryset(
        request,
        _psn_queryset(request),
        item_key="psn_items",
        page_param="psn_page",
        partial_url=PSN_TABLE_URL,
        target="#contacts-positions-table-wrap",
    )


def _ctz_queryset(request):
    queryset = CitizenshipRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _ctz_context(request):
    return _paginate_queryset(
        request,
        _ctz_queryset(request),
        item_key="ctz_items",
        page_param="ctz_page",
        partial_url=CTZ_TABLE_URL,
        target="#contacts-citizenships-table-wrap",
    )


def _tel_queryset(request):
    queryset = PhoneRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _tel_context(request):
    return _paginate_queryset(
        request,
        _tel_queryset(request),
        item_key="tel_items",
        page_param="tel_page",
        partial_url=TEL_TABLE_URL,
        target="#contacts-phones-table-wrap",
    )


def _eml_queryset(request):
    queryset = EmailRecord.objects.select_related("person").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _eml_context(request):
    return _paginate_queryset(
        request,
        _eml_queryset(request),
        item_key="eml_items",
        page_param="eml_page",
        partial_url=EML_TABLE_URL,
        target="#contacts-emails-table-wrap",
    )


def _spc_queryset(request):
    queryset = SpecialtyRecord.objects.select_related("person", "specialty").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _spc_context(request):
    return _paginate_queryset(
        request,
        _spc_queryset(request),
        item_key="spc_items",
        page_param="spc_page",
        partial_url=SPC_TABLE_URL,
        target="#contacts-specialties-table-wrap",
    )


def _adr_queryset(request):
    queryset = ResidenceAddressRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return queryset


def _adr_context(request):
    return _paginate_queryset(
        request,
        _adr_queryset(request),
        item_key="adr_items",
        page_param="adr_page",
        partial_url=ADR_TABLE_URL,
        target="#contacts-addresses-table-wrap",
    )


def _render_prs_updated(request, *, affected=None):
    response = render(request, PRS_TABLE_TEMPLATE, _prs_context(request))
    return _set_contacts_trigger(response, source="prs-select", affected=affected)


def _render_ctz_updated(request, *, affected=None):
    response = render(request, CTZ_TABLE_TEMPLATE, _ctz_context(request))
    return _set_contacts_trigger(response, source="ctz-select", affected=affected)


def _render_psn_updated(request, *, affected=None):
    response = render(request, PSN_TABLE_TEMPLATE, _psn_context(request))
    return _set_contacts_trigger(response, source="psn-select", affected=affected)


def _render_tel_updated(request, *, affected=None):
    response = render(request, TEL_TABLE_TEMPLATE, _tel_context(request))
    return _set_contacts_trigger(response, source="tel-select", affected=affected)


def _render_eml_updated(request, *, affected=None):
    response = render(request, EML_TABLE_TEMPLATE, _eml_context(request))
    return _set_contacts_trigger(response, source="eml-select", affected=affected)


def _render_spc_updated(request, *, affected=None):
    response = render(request, SPC_TABLE_TEMPLATE, _spc_context(request))
    return _set_contacts_trigger(response, source="spc-select", affected=affected)


def _render_adr_updated(request, *, affected=None):
    response = render(request, ADR_TABLE_TEMPLATE, _adr_context(request))
    return _set_contacts_trigger(response, source="adr-select", affected=affected)


@login_required
@require_http_methods(["GET"])
def prs_autocomplete(request):
    query = str(request.GET.get("q") or "").strip()
    if not query:
        return JsonResponse({"results": [], "total_count": 0})

    queryset = (
        PersonRecord.objects
        .filter(Q(last_name__icontains=query))
        .order_by("last_name", "first_name", "middle_name", "position", "id")
    )
    results = [
        {
            "id": item.pk,
            "last_name": item.last_name or "",
            "first_name": item.first_name or "",
            "middle_name": item.middle_name or "",
            "display_name": item.display_name or item.last_name or "",
        }
        for item in queryset[:10]
    ]
    return JsonResponse({"results": results, "total_count": queryset.count()})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def prs_filter_options(request):
    q = (request.GET.get("q") or "").strip()
    ids = _req_list_param(request, "ids")
    if q:
        items = _person_filter_search_items(q)
    elif ids:
        items = _person_filter_items(ids=ids)
    else:
        items = _person_filter_items()
    return JsonResponse({"results": items, "total_count": len(items)})


def _refresh_person_position_sources(person: PersonRecord):
    for item in person.positions.all():
        new_source = item.resolve_source()
        if item.source != new_source:
            PositionRecord.objects.filter(pk=item.pk).update(source=new_source)


def _ensure_person_citizenship_record(person: PersonRecord, *, user=None):
    if person.citizenships.exists():
        return None
    item = person.citizenships.create(
        country=person.citizenship,
        status="",
        identifier="",
        number="",
        valid_from=None,
        valid_to=None,
        record_date=date_type.today(),
        record_author=_contacts_record_author(user) if user else "",
        source="",
        position=_next_ctz_position(),
    )
    return item


def _ensure_person_phone_record(person: PersonRecord, *, user=None):
    if person.phones.exists():
        return None
    today = date_type.today()
    item = person.phones.create(
        country=None,
        code="",
        phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
        region="",
        phone_number="",
        is_primary=True,
        extension="",
        valid_from=today,
        valid_to=None,
        record_date=today,
        record_author=_contacts_record_author(user) if user else "",
        source="",
        position=_next_tel_position(),
    )
    return item


def _ensure_person_email_record(person: PersonRecord, *, user=None):
    if person.emails.exists():
        return None
    today = date_type.today()
    item = person.emails.create(
        email="",
        valid_from=today,
        valid_to=None,
        record_date=today,
        record_author=_contacts_record_author(user) if user else "",
        source="",
        position=_next_eml_position(),
    )
    return item


def _ensure_person_residence_address_record(person: PersonRecord, *, user=None):
    if person.residence_addresses.exists():
        return None
    item = person.residence_addresses.create(
        country=person.citizenship,
        region="",
        postal_code="",
        locality="",
        street="",
        building="",
        premise="",
        premise_part="",
        valid_from=None,
        valid_to=None,
        record_date=date_type.today(),
        record_author=_contacts_record_author(user) if user else "",
        source="",
        position=_next_adr_position(),
    )
    return item


@login_required
@require_http_methods(["GET"])
def prs_table_partial(request):
    return render(request, PRS_TABLE_TEMPLATE, _prs_context(request))


def _prs_gender_lookup():
    lookup = {}
    for code, label in PERSON_GENDER_CHOICES:
        lookup[label.strip().lower()] = code
        lookup[code.strip().lower()] = code
    return lookup


def _prs_user_kind_lookup():
    lookup = {"": ""}
    for code, label in USER_KIND_CHOICES:
        lookup[label.strip().lower()] = code
        lookup[code.strip().lower()] = code
    return lookup


def _parse_prs_csv_gender(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""
    parsed = _prs_gender_lookup().get(value.lower())
    if parsed is None:
        raise ValueError(f"неизвестное значение пола «{value}»")
    return parsed


def _parse_prs_csv_user_kind(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""
    parsed = _prs_user_kind_lookup().get(value.lower())
    if parsed is None:
        raise ValueError(f"неизвестный тип пользователя «{value}»")
    return parsed


def _parse_prs_csv_birth_date(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"некорректная дата рождения «{value}»")


def _parse_prs_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-PRS"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _format_prs_csv_birth_date(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _parse_contact_csv_date(raw_value, *, field_label):
    value = (raw_value or "").strip()
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"некорректная дата «{value}» для поля «{field_label}»")


def _parse_ctz_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-CTZ"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _parse_adr_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-ADR"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _parse_psn_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-PSN"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _parse_tel_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-TEL"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _parse_eml_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-EML"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _parse_spc_csv_id(raw_value):
    value = (raw_value or "").strip().upper()
    if not value:
        return None
    if value.endswith("-SPC"):
        value = value[:-4]
    if value.isdigit():
        return int(value)
    return None


def _format_tel_csv_type(item):
    if item.phone_type == PhoneRecord.PHONE_TYPE_MOBILE:
        return "моб."
    if item.phone_type == PhoneRecord.PHONE_TYPE_LANDLINE:
        return "гор."
    return ""


def _format_tel_csv_phone(item):
    if not item.phone_number:
        return ""
    if item.code:
        result = f"{item.code} {item.phone_number}".strip()
    else:
        result = item.phone_number
    if item.extension:
        result = f"{result} доб. {item.extension}"
    return result


def _format_tel_csv_is_primary(item):
    return "Да" if item.is_primary else "Нет"


def _parse_tel_csv_phone_type(raw_value):
    value = (raw_value or "").strip().lower()
    if not value:
        return PhoneRecord.PHONE_TYPE_MOBILE
    if value in {"моб.", "моб", "mobile", "мобильный"}:
        return PhoneRecord.PHONE_TYPE_MOBILE
    if value in {"гор.", "гор", "landline", "стационарный"}:
        return PhoneRecord.PHONE_TYPE_LANDLINE
    raise ValueError(f"неизвестный тип телефона «{raw_value}»")


def _parse_tel_csv_is_primary(raw_value):
    value = (raw_value or "").strip().lower()
    if not value:
        return False
    if value in {"да", "true", "1", "yes", "on"}:
        return True
    if value in {"нет", "false", "0", "no", "off"}:
        return False
    raise ValueError(f"некорректное значение «{raw_value}» для поля «Основной»")


def _parse_tel_csv_phone_display(raw_value, *, country):
    value = (raw_value or "").strip()
    extension = ""
    if " доб. " in value:
        value, _, extension_part = value.partition(" доб. ")
        extension = extension_part.strip()
    dial_code = _dial_code_for_country(country) if country else ""
    phone_number = value
    if dial_code:
        normalized_code = dial_code.lstrip("+")
        if phone_number.startswith(dial_code):
            phone_number = phone_number[len(dial_code):].strip()
        elif phone_number.startswith("+" + normalized_code):
            phone_number = phone_number[len(normalized_code) + 1:].strip()
        elif phone_number.startswith(normalized_code):
            phone_number = phone_number[len(normalized_code):].strip()
    return dial_code, phone_number, extension


def _default_phone_country():
    return OKSMCountry.objects.filter(code="643").order_by("position", "id").first()


def _country_by_short_name(raw_value):
    name = (raw_value or "").strip()
    if not name:
        return None
    return OKSMCountry.objects.filter(short_name__iexact=name).order_by("position", "id").first()


def _parse_ctz_csv_status(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""
    valid_statuses = {label for _code, label in CitizenshipRecordForm.STATUS_CHOICES if label}
    if value not in valid_statuses:
        raise ValueError(f"неизвестный статус «{value}»")
    return value


@login_required
@user_passes_test(staff_required)
@require_POST
def prs_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 8:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 8: "
                "ID-PRS, Фамилия, Имя, Отчество, ФИО (полное) в родительном падеже, Пол, Дата рождения, Пользователь."
            )
            continue

        prs_id_raw = row[0].strip() if len(row) > 0 else ""
        last_name = row[1].strip() if len(row) > 1 else ""
        first_name = row[2].strip() if len(row) > 2 else ""
        middle_name = row[3].strip() if len(row) > 3 else ""
        full_name_genitive = row[4].strip() if len(row) > 4 else ""
        gender_raw = row[5].strip() if len(row) > 5 else ""
        birth_date_raw = row[6].strip() if len(row) > 6 else ""
        user_kind_raw = row[7].strip() if len(row) > 7 else ""

        parsed_id = _parse_prs_csv_id(prs_id_raw)
        if parsed_id and PersonRecord.objects.filter(pk=parsed_id).exists():
            existing_label = prs_id_raw or f"{parsed_id:05d}-PRS"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        if not last_name:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: Фамилия.")
            continue

        try:
            gender = _parse_prs_csv_gender(gender_raw)
            user_kind = _parse_prs_csv_user_kind(user_kind_raw)
            birth_date = _parse_prs_csv_birth_date(birth_date_raw)
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        item = PersonRecord.objects.create(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            full_name_genitive=full_name_genitive,
            gender=gender,
            birth_date=birth_date,
            user_kind=user_kind,
            position=_next_prs_position(),
        )
        _ensure_person_citizenship_record(item, user=request.user)
        _ensure_person_residence_address_record(item, user=request.user)
        _ensure_person_phone_record(item, user=request.user)
        _ensure_person_email_record(item, user=request.user)
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def prs_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(PRS_CSV_HEADERS)

    for item in _prs_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-PRS",
                item.last_name,
                item.first_name,
                item.middle_name,
                item.full_name_genitive,
                item.get_gender_display(),
                _format_prs_csv_birth_date(item.birth_date),
                item.get_user_kind_display(),
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="person_registry.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def prs_form_create(request):
    if request.method == "GET":
        return render(request, PRS_FORM_TEMPLATE, {"form": PersonRecordForm(), "action": "create"})
    form = PersonRecordForm(request.POST)
    if not form.is_valid():
        response = render(request, PRS_FORM_TEMPLATE, {"form": form, "action": "create"})
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    if not item.position:
        item.position = _next_prs_position()
    item.save()
    _ensure_person_citizenship_record(item, user=request.user)
    _ensure_person_residence_address_record(item, user=request.user)
    _ensure_person_phone_record(item, user=request.user)
    _ensure_person_email_record(item, user=request.user)
    return _render_prs_updated(request, affected=["ctz-select", "adr-select", "psn-select", "tel-select", "eml-select"])


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def prs_form_edit(request, pk: int):
    item = get_object_or_404(PersonRecord, pk=pk)
    if request.method == "GET":
        return render(request, PRS_FORM_TEMPLATE, {"form": PersonRecordForm(instance=item), "action": "edit", "item": item})
    form = PersonRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(request, PRS_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    saved_item = form.save()
    _refresh_person_position_sources(saved_item)
    _ensure_person_citizenship_record(saved_item, user=request.user)
    _ensure_person_residence_address_record(saved_item, user=request.user)
    _ensure_person_phone_record(saved_item, user=request.user)
    _ensure_person_email_record(saved_item, user=request.user)
    return _render_prs_updated(request, affected=["ctz-select", "adr-select", "psn-select", "tel-select", "eml-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def prs_delete(request, pk: int):
    get_object_or_404(PersonRecord, pk=pk).delete()
    return _render_prs_updated(request, affected=["ctz-select", "adr-select", "psn-select", "tel-select", "eml-select"])


@login_required
@require_http_methods(["POST", "GET"])
def prs_move_up(request, pk: int):
    _normalize_prs_positions()
    items = list(PersonRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        PersonRecord.objects.filter(pk=current.id).update(position=previous.position)
        PersonRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_prs_positions()
    return _render_prs_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def prs_move_down(request, pk: int):
    _normalize_prs_positions()
    items = list(PersonRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        PersonRecord.objects.filter(pk=current.id).update(position=next_item.position)
        PersonRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_prs_positions()
    return _render_prs_updated(request)


@login_required
@require_http_methods(["GET"])
def psn_table_partial(request):
    return render(request, PSN_TABLE_TEMPLATE, _psn_context(request))


@login_required
@user_passes_test(staff_required)
@require_POST
def psn_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 9:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 9: "
                "ID-PSN, ID-PRS, Наименование организации (краткое), Должность, Действ. от, Действ. до, "
                "Запись, Автор записи, Источник."
            )
            continue

        psn_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        organization_short_name = row[2].strip() if len(row) > 2 else ""
        job_title = row[3].strip() if len(row) > 3 else ""
        valid_from_raw = row[4].strip() if len(row) > 4 else ""
        valid_to_raw = row[5].strip() if len(row) > 5 else ""
        record_date_raw = row[6].strip() if len(row) > 6 else ""
        record_author_raw = row[7].strip() if len(row) > 7 else ""
        source_raw = row[8].strip() if len(row) > 8 else ""

        parsed_psn_id = _parse_psn_csv_id(psn_id_raw)
        if parsed_psn_id and PositionRecord.objects.filter(pk=parsed_psn_id).exists():
            existing_label = psn_id_raw or f"{parsed_psn_id:05d}-PSN"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        try:
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        item = PositionRecord(
            person=person,
            organization_short_name=organization_short_name,
            job_title=job_title,
            valid_from=valid_from,
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source_raw,
            position=_next_psn_position(),
        )
        if not item.source:
            item.source = item.resolve_source()
        item.save()
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def psn_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(PSN_CSV_HEADERS)

    for item in _psn_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-PSN",
                f"{item.person.pk:05d}-PRS",
                item.organization_short_name,
                item.job_title,
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="position_registry.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def tel_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 11:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 11: "
                "ID-TEL, ID-PRS, Страна, Тип, Номер телефона, Основной, Действ. от, Действ. до, "
                "Запись, Автор записи, Источник."
            )
            continue

        tel_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        country_raw = row[2].strip() if len(row) > 2 else ""
        phone_type_raw = row[3].strip() if len(row) > 3 else ""
        phone_display_raw = row[4].strip() if len(row) > 4 else ""
        is_primary_raw = row[5].strip() if len(row) > 5 else ""
        valid_from_raw = row[6].strip() if len(row) > 6 else ""
        valid_to_raw = row[7].strip() if len(row) > 7 else ""
        record_date_raw = row[8].strip() if len(row) > 8 else ""
        record_author_raw = row[9].strip() if len(row) > 9 else ""
        source_raw = row[10].strip() if len(row) > 10 else ""

        parsed_tel_id = _parse_tel_csv_id(tel_id_raw)
        if parsed_tel_id and PhoneRecord.objects.filter(pk=parsed_tel_id).exists():
            existing_label = tel_id_raw or f"{parsed_tel_id:05d}-TEL"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        if country_raw:
            country = _country_by_short_name(country_raw)
            if country is None:
                warnings.append(f"Строка {i}: страна «{country_raw}» не найдена.")
                continue
        else:
            country = _default_phone_country()

        try:
            phone_type = _parse_tel_csv_phone_type(phone_type_raw)
            is_primary = _parse_tel_csv_is_primary(is_primary_raw)
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        code, phone_number, extension = _parse_tel_csv_phone_display(phone_display_raw, country=country)
        if phone_type != PhoneRecord.PHONE_TYPE_LANDLINE:
            extension = ""
        region = ""

        item = PhoneRecord(
            person=person,
            country=country,
            code=code,
            phone_type=phone_type,
            region=region,
            phone_number=phone_number,
            is_primary=is_primary,
            extension=extension,
            valid_from=valid_from or date_type.today(),
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source_raw,
            position=_next_tel_position(),
        )
        item.save()
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def tel_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(TEL_CSV_HEADERS)

    for item in _tel_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-TEL",
                f"{item.person.pk:05d}-PRS",
                item.country.short_name if item.country else "",
                _format_tel_csv_type(item),
                _format_tel_csv_phone(item),
                _format_tel_csv_is_primary(item),
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="phone_registry.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def eml_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 9:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 9: "
                "ID-EML, ID-PRS, Электронная почта, Пользователь, Действ. от, Действ. до, "
                "Запись, Автор записи, Источник."
            )
            continue

        eml_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        email_raw = row[2].strip() if len(row) > 2 else ""
        user_kind_raw = row[3].strip() if len(row) > 3 else ""
        valid_from_raw = row[4].strip() if len(row) > 4 else ""
        valid_to_raw = row[5].strip() if len(row) > 5 else ""
        record_date_raw = row[6].strip() if len(row) > 6 else ""
        record_author_raw = row[7].strip() if len(row) > 7 else ""
        source_raw = row[8].strip() if len(row) > 8 else ""

        parsed_eml_id = _parse_eml_csv_id(eml_id_raw)
        if parsed_eml_id and EmailRecord.objects.filter(pk=parsed_eml_id).exists():
            existing_label = eml_id_raw or f"{parsed_eml_id:05d}-EML"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        if email_raw:
            try:
                validate_email(email_raw)
            except Exception:
                warnings.append(f"Строка {i}: некорректный адрес электронной почты «{email_raw}».")
                continue

        try:
            user_kind = _parse_prs_csv_user_kind(user_kind_raw) if user_kind_raw else person.user_kind
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        item = EmailRecord(
            person=person,
            email=email_raw,
            user_kind=user_kind,
            valid_from=valid_from or date_type.today(),
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source_raw,
            position=_next_eml_position(),
        )
        item.save()
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_POST
def spc_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    specialties_by_name = {
        " ".join((item.specialty or "").strip().lower().split()): item
        for item in ExpertSpecialty.objects.exclude(specialty="").all()
    }
    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 9:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 9: "
                "ID-SPC, ID-PRS, Специальность, Пользователь, Действ. от, Действ. до, "
                "Запись, Автор записи, Источник."
            )
            continue

        spc_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        specialty_raw = row[2].strip() if len(row) > 2 else ""
        user_kind_raw = row[3].strip() if len(row) > 3 else ""
        valid_from_raw = row[4].strip() if len(row) > 4 else ""
        valid_to_raw = row[5].strip() if len(row) > 5 else ""
        record_date_raw = row[6].strip() if len(row) > 6 else ""
        record_author_raw = row[7].strip() if len(row) > 7 else ""
        source_raw = row[8].strip() if len(row) > 8 else ""

        parsed_spc_id = _parse_spc_csv_id(spc_id_raw)
        if parsed_spc_id and SpecialtyRecord.objects.filter(pk=parsed_spc_id).exists():
            existing_label = spc_id_raw or f"{parsed_spc_id:05d}-SPC"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        specialty = specialties_by_name.get(" ".join(specialty_raw.lower().split()))
        if specialty is None:
            warnings.append(f"Строка {i}: специальность «{specialty_raw}» не найдена.")
            continue

        try:
            user_kind = _parse_prs_csv_user_kind(user_kind_raw) if user_kind_raw else person.user_kind
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        if valid_from and valid_to and valid_to < valid_from:
            warnings.append(f"Строка {i}: дата «Действ. до» не может быть раньше даты «Действ. от».")
            continue
        if SpecialtyRecord.objects.filter(
            person=person,
            specialty=specialty,
        ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=date_type.today())).exists():
            warnings.append(f"Строка {i}: у выбранного ID-PRS уже есть активная запись с этой специальностью.")
            continue

        item = SpecialtyRecord(
            person=person,
            specialty=specialty,
            user_kind=user_kind,
            valid_from=valid_from or date_type.today(),
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source_raw,
            position=_next_spc_position(),
        )
        item.save()
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def eml_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(EML_CSV_HEADERS)

    for item in _eml_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-EML",
                f"{item.person.pk:05d}-PRS",
                item.email,
                item.get_user_kind_display(),
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="email_registry.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def spc_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(SPC_CSV_HEADERS)

    for item in _spc_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-SPC",
                f"{item.person.pk:05d}-PRS",
                item.specialty.specialty if item.specialty else "",
                item.get_user_kind_display(),
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="specialty_registry.csv"'
    return response


@login_required
@require_http_methods(["GET"])
def tel_table_partial(request):
    return render(request, TEL_TABLE_TEMPLATE, _tel_context(request))


@login_required
@require_http_methods(["GET"])
def eml_table_partial(request):
    return render(request, EML_TABLE_TEMPLATE, _eml_context(request))


@login_required
@require_http_methods(["GET"])
def spc_table_partial(request):
    return render(request, SPC_TABLE_TEMPLATE, _spc_context(request))


@login_required
@require_http_methods(["GET"])
def adr_table_partial(request):
    return render(request, ADR_TABLE_TEMPLATE, _adr_context(request))


@login_required
@user_passes_test(staff_required)
@require_POST
def adr_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 15:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 15: "
                "ID-ADR, ID-PRS, Страна, Регион, Индекс, Населенный пункт, Улица, Здание, Помещение, "
                "Часть помещения, Действ. от, Действ. до, Запись, Автор записи, Источник."
            )
            continue

        adr_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        country_raw = row[2].strip() if len(row) > 2 else ""
        region = row[3].strip() if len(row) > 3 else ""
        postal_code = row[4].strip() if len(row) > 4 else ""
        locality = row[5].strip() if len(row) > 5 else ""
        street = row[6].strip() if len(row) > 6 else ""
        building = row[7].strip() if len(row) > 7 else ""
        premise = row[8].strip() if len(row) > 8 else ""
        premise_part = row[9].strip() if len(row) > 9 else ""
        valid_from_raw = row[10].strip() if len(row) > 10 else ""
        valid_to_raw = row[11].strip() if len(row) > 11 else ""
        record_date_raw = row[12].strip() if len(row) > 12 else ""
        record_author_raw = row[13].strip() if len(row) > 13 else ""
        source = row[14].strip() if len(row) > 14 else ""

        parsed_adr_id = _parse_adr_csv_id(adr_id_raw)
        if parsed_adr_id and ResidenceAddressRecord.objects.filter(pk=parsed_adr_id).exists():
            existing_label = adr_id_raw or f"{parsed_adr_id:05d}-ADR"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        country = _country_by_short_name(country_raw)
        if country is None:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: Страна.")
            continue

        try:
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        ResidenceAddressRecord.objects.create(
            person=person,
            country=country,
            region=region,
            postal_code=postal_code,
            locality=locality,
            street=street,
            building=building,
            premise=premise,
            premise_part=premise_part,
            valid_from=valid_from,
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source,
            position=_next_adr_position(),
        )
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def adr_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(ADR_CSV_HEADERS)

    for item in _adr_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-ADR",
                f"{item.person.pk:05d}-PRS",
                item.country.short_name if item.country_id and item.country else "",
                item.region,
                item.postal_code,
                item.locality,
                item.street,
                item.building,
                item.premise,
                item.premise_part,
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="residence_address_registry.csv"'
    return response


@login_required
@require_http_methods(["GET"])
def ctz_table_partial(request):
    return render(request, CTZ_TABLE_TEMPLATE, _ctz_context(request))


@login_required
@user_passes_test(staff_required)
@require_POST
def ctz_csv_upload(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse({"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."}, status=400)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 11:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 11: "
                "ID-CTZ, ID-PRS, Страна, Статус, Идентификатор, Номер, Действ. от, Действ. до, "
                "Запись, Автор записи, Источник."
            )
            continue

        ctz_id_raw = row[0].strip() if len(row) > 0 else ""
        prs_id_raw = row[1].strip() if len(row) > 1 else ""
        country_raw = row[2].strip() if len(row) > 2 else ""
        status_raw = row[3].strip() if len(row) > 3 else ""
        identifier_raw = row[4].strip() if len(row) > 4 else ""
        number = row[5].strip() if len(row) > 5 else ""
        valid_from_raw = row[6].strip() if len(row) > 6 else ""
        valid_to_raw = row[7].strip() if len(row) > 7 else ""
        record_date_raw = row[8].strip() if len(row) > 8 else ""
        record_author_raw = row[9].strip() if len(row) > 9 else ""
        source = row[10].strip() if len(row) > 10 else ""

        parsed_ctz_id = _parse_ctz_csv_id(ctz_id_raw)
        if parsed_ctz_id and CitizenshipRecord.objects.filter(pk=parsed_ctz_id).exists():
            existing_label = ctz_id_raw or f"{parsed_ctz_id:05d}-CTZ"
            warnings.append(f"Строка {i}: запись {existing_label} уже существует, пропущена.")
            continue

        parsed_prs_id = _parse_prs_csv_id(prs_id_raw)
        if not parsed_prs_id:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: ID-PRS.")
            continue
        person = PersonRecord.objects.filter(pk=parsed_prs_id).first()
        if person is None:
            warnings.append(f"Строка {i}: лицо {prs_id_raw or f'{parsed_prs_id:05d}-PRS'} не найдено.")
            continue

        country = _country_by_short_name(country_raw)
        if country is None:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: Страна.")
            continue

        try:
            status = _parse_ctz_csv_status(status_raw)
            valid_from = _parse_contact_csv_date(valid_from_raw, field_label="Действ. от")
            valid_to = _parse_contact_csv_date(valid_to_raw, field_label="Действ. до")
            record_date = _parse_contact_csv_date(record_date_raw, field_label="Запись")
        except ValueError as exc:
            warnings.append(f"Строка {i}: {exc}.")
            continue

        identifier = identifier_raw or _physical_identifier_for_country(country.pk)
        CitizenshipRecord.objects.create(
            person=person,
            country=country,
            status=status,
            identifier=identifier,
            number=number,
            valid_from=valid_from,
            valid_to=valid_to,
            record_date=record_date or date_type.today(),
            record_author=record_author_raw or _contacts_record_author(request.user),
            source=source,
            position=_next_ctz_position(),
        )
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def ctz_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(CTZ_CSV_HEADERS)

    for item in _ctz_queryset(request):
        writer.writerow(
            [
                f"{item.pk:05d}-CTZ",
                f"{item.person.pk:05d}-PRS",
                item.country.short_name if item.country_id and item.country else "",
                item.status,
                item.identifier,
                item.number,
                _format_prs_csv_birth_date(item.valid_from),
                _format_prs_csv_birth_date(item.valid_to),
                _format_prs_csv_birth_date(item.record_date),
                item.record_author,
                item.source,
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="citizenship_registry.csv"'
    return response


@login_required
@require_http_methods(["GET"])
def ctz_identifier_for_country(request):
    return JsonResponse({"identifier": _ctz_identifier_for_country(request.GET.get("country_id"))})


@login_required
@require_http_methods(["GET"])
def prs_birth_date(request):
    birth_date = _prs_birth_date(request.GET.get("person_id"))
    return JsonResponse({"birth_date": birth_date.isoformat() if birth_date else ""})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def adr_registration_autofill(request):
    return JsonResponse(
        _expert_registration_address_payload(
            request.GET.get("person_id"),
            request.GET.get("country_id"),
        )
    )


@login_required
@require_http_methods(["GET"])
def tel_ru_landline_lookup(request):
    lookup = lookup_ru_landline(request.GET.get("phone_number"))
    return JsonResponse(
        {
            "digits": lookup.digits,
            "area_code": lookup.area_code,
            "subscriber_length": lookup.subscriber_length,
            "region": lookup.region,
            "operator": lookup.operator,
            "formatted_number": lookup.formatted_number,
            "unique": lookup.unique,
            "exact": lookup.exact,
            "match_count": lookup.match_count,
        }
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ctz_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        return render(
            request,
            CTZ_FORM_TEMPLATE,
            {
                "form": CitizenshipRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
    form = CitizenshipRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            CTZ_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    if not item.position:
        item.position = _next_ctz_position()
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_ctz_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ctz_form_edit(request, pk: int):
    item = get_object_or_404(CitizenshipRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            CTZ_FORM_TEMPLATE,
            {
                "form": CitizenshipRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = CitizenshipRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            CTZ_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_ctz_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ctz_delete(request, pk: int):
    item = get_object_or_404(CitizenshipRecord, pk=pk)
    if not item.person.citizenships.exclude(pk=item.pk).exists():
        return _validation_error("У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре гражданств и идентификаторов.")
    item.delete()
    return _render_ctz_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def ctz_move_up(request, pk: int):
    _normalize_ctz_positions()
    items = list(CitizenshipRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        CitizenshipRecord.objects.filter(pk=current.id).update(position=previous.position)
        CitizenshipRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_ctz_positions()
    return _render_ctz_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def ctz_move_down(request, pk: int):
    _normalize_ctz_positions()
    items = list(CitizenshipRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        CitizenshipRecord.objects.filter(pk=current.id).update(position=next_item.position)
        CitizenshipRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_ctz_positions()
    return _render_ctz_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def adr_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        return render(
            request,
            ADR_FORM_TEMPLATE,
            {
                "form": ResidenceAddressRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
                "regions_as_of_iso": date_type.today().isoformat(),
            },
        )
    form = ResidenceAddressRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            ADR_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
                "regions_as_of_iso": date_type.today().isoformat(),
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    if not item.position:
        item.position = _next_adr_position()
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_adr_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def adr_form_edit(request, pk: int):
    item = get_object_or_404(ResidenceAddressRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            ADR_FORM_TEMPLATE,
            {
                "form": ResidenceAddressRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
                "regions_as_of_iso": date_type.today().isoformat(),
            },
        )
    form = ResidenceAddressRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            ADR_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
                "regions_as_of_iso": date_type.today().isoformat(),
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_adr_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def adr_delete(request, pk: int):
    item = get_object_or_404(ResidenceAddressRecord, pk=pk)
    if not item.person.residence_addresses.exclude(pk=item.pk).exists():
        return _validation_error("У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре адресов проживания.")
    item.delete()
    return _render_adr_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def adr_move_up(request, pk: int):
    _normalize_adr_positions()
    items = list(ResidenceAddressRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        ResidenceAddressRecord.objects.filter(pk=current.id).update(position=previous.position)
        ResidenceAddressRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_adr_positions()
    return _render_adr_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def adr_move_down(request, pk: int):
    _normalize_adr_positions()
    items = list(ResidenceAddressRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        ResidenceAddressRecord.objects.filter(pk=current.id).update(position=next_item.position)
        ResidenceAddressRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_adr_positions()
    return _render_adr_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def psn_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        return render(
            request,
            PSN_FORM_TEMPLATE,
            {
                "form": PositionRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
    form = PositionRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            PSN_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    if not item.position:
        item.position = _next_psn_position()
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.source = item.resolve_source()
    item.save()
    return _render_psn_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def psn_form_edit(request, pk: int):
    item = get_object_or_404(PositionRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            PSN_FORM_TEMPLATE,
            {
                "form": PositionRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = PositionRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            PSN_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.source = item.resolve_source()
    item.save()
    return _render_psn_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def psn_delete(request, pk: int):
    get_object_or_404(PositionRecord, pk=pk).delete()
    return _render_psn_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def psn_move_up(request, pk: int):
    _normalize_psn_positions()
    items = list(PositionRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        PositionRecord.objects.filter(pk=current.id).update(position=previous.position)
        PositionRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_psn_positions()
    return _render_psn_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def psn_move_down(request, pk: int):
    _normalize_psn_positions()
    items = list(PositionRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        PositionRecord.objects.filter(pk=current.id).update(position=next_item.position)
        PositionRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_psn_positions()
    return _render_psn_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def tel_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        return render(
            request,
            TEL_FORM_TEMPLATE,
            {
                "form": PhoneRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
    form = PhoneRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            TEL_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    today = date_type.today()
    if not item.position:
        item.position = _next_tel_position()
    item.record_date = today
    if not item.valid_from:
        item.valid_from = today
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_tel_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def tel_form_edit(request, pk: int):
    item = get_object_or_404(PhoneRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            TEL_FORM_TEMPLATE,
            {
                "form": PhoneRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = PhoneRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            TEL_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_tel_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def tel_delete(request, pk: int):
    item = get_object_or_404(PhoneRecord, pk=pk)
    if not item.person.phones.exclude(pk=item.pk).exists():
        return _validation_error("У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре телефонных номеров.")
    item.delete()
    return _render_tel_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def tel_move_up(request, pk: int):
    _normalize_tel_positions()
    items = list(PhoneRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        PhoneRecord.objects.filter(pk=current.id).update(position=previous.position)
        PhoneRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_tel_positions()
    return _render_tel_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def tel_move_down(request, pk: int):
    _normalize_tel_positions()
    items = list(PhoneRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        PhoneRecord.objects.filter(pk=current.id).update(position=next_item.position)
        PhoneRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_tel_positions()
    return _render_tel_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def eml_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        today = date_type.today()
        return render(
            request,
            EML_FORM_TEMPLATE,
            {
                "form": EmailRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "user_kind_display": _person_user_kind_display_by_id(initial_person_id),
                "record_date_display": today.strftime("%d.%m.%Y"),
                "record_author_display": "",
                "source_display": "",
            },
        )
    form = EmailRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            EML_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "user_kind_display": _person_user_kind_display_by_id(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    today = date_type.today()
    if not item.position:
        item.position = _next_eml_position()
    item.record_date = today
    if not item.valid_from:
        item.valid_from = today
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_eml_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def eml_form_edit(request, pk: int):
    item = get_object_or_404(EmailRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            EML_FORM_TEMPLATE,
            {
                "form": EmailRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "user_kind_display": item.get_user_kind_display(),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = EmailRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            EML_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "user_kind_display": item.get_user_kind_display(),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_eml_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def eml_delete(request, pk: int):
    item = get_object_or_404(EmailRecord, pk=pk)
    if not item.person.emails.exclude(pk=item.pk).exists():
        return _validation_error("У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре адресов электронной почты.")
    item.delete()
    return _render_eml_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def eml_move_up(request, pk: int):
    _normalize_eml_positions()
    items = list(EmailRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        EmailRecord.objects.filter(pk=current.id).update(position=previous.position)
        EmailRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_eml_positions()
    return _render_eml_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def eml_move_down(request, pk: int):
    _normalize_eml_positions()
    items = list(EmailRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        EmailRecord.objects.filter(pk=current.id).update(position=next_item.position)
        EmailRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_eml_positions()
    return _render_eml_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def spc_form_create(request):
    if request.method == "GET":
        initial_person_id = _single_selected_person_id(request)
        today = date_type.today()
        return render(
            request,
            SPC_FORM_TEMPLATE,
            {
                "form": SpecialtyRecordForm(initial={"person": initial_person_id} if initial_person_id else None),
                "action": "create",
                **_person_picker_context(initial_person_id),
                "user_kind_display": _person_user_kind_display_by_id(initial_person_id),
                "record_date_display": today.strftime("%d.%m.%Y"),
                "record_author_display": "",
                "source_display": "",
            },
        )
    form = SpecialtyRecordForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            SPC_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                **_person_picker_context(request.POST.get("person")),
                "user_kind_display": _person_user_kind_display_by_id(request.POST.get("person")),
                "record_date_display": "",
                "record_author_display": "",
                "source_display": "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    today = date_type.today()
    if not item.position:
        item.position = _next_spc_position()
    item.user_kind = item.person.user_kind if item.person_id else ""
    item.record_date = today
    if not item.valid_from:
        item.valid_from = today
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_spc_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def spc_form_edit(request, pk: int):
    item = get_object_or_404(SpecialtyRecord, pk=pk)
    if request.method == "GET":
        return render(
            request,
            SPC_FORM_TEMPLATE,
            {
                "form": SpecialtyRecordForm(instance=item),
                "action": "edit",
                "item": item,
                **_person_picker_context(item.person_id),
                "user_kind_display": item.get_user_kind_display(),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = SpecialtyRecordForm(request.POST, instance=item)
    if not form.is_valid():
        response = render(
            request,
            SPC_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                **_person_picker_context(request.POST.get("person") or item.person_id),
                "user_kind_display": item.get_user_kind_display(),
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        response["HX-Retarget"] = "#contacts-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response
    item = form.save(commit=False)
    item.user_kind = item.person.user_kind if item.person_id else ""
    item.record_date = date_type.today()
    item.record_author = _contacts_record_author(request.user)
    item.save()
    return _render_spc_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def spc_delete(request, pk: int):
    item = get_object_or_404(SpecialtyRecord, pk=pk)
    item.delete()
    return _render_spc_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def spc_move_up(request, pk: int):
    _normalize_spc_positions()
    items = list(SpecialtyRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        SpecialtyRecord.objects.filter(pk=current.id).update(position=previous.position)
        SpecialtyRecord.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_spc_positions()
    return _render_spc_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def spc_move_down(request, pk: int):
    _normalize_spc_positions()
    items = list(SpecialtyRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((index for index, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        SpecialtyRecord.objects.filter(pk=current.id).update(position=next_item.position)
        SpecialtyRecord.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_spc_positions()
    return _render_spc_updated(request)
