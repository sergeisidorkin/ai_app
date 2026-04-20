import json
from datetime import date as date_type
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from classifiers_app.models import PhysicalEntityIdentifier
from classifiers_app.numcap import lookup_ru_landline

from .forms import (
    CitizenshipRecordForm,
    EmailRecordForm,
    PersonRecordForm,
    PhoneRecordForm,
    PositionRecordForm,
    ResidenceAddressRecordForm,
)
from .models import CitizenshipRecord, EmailRecord, PersonRecord, PhoneRecord, PositionRecord, ResidenceAddressRecord

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
ADR_TABLE_TEMPLATE = "contacts_app/adr_table_partial.html"
ADR_FORM_TEMPLATE = "contacts_app/adr_form.html"
CONTACTS_PAGE_SIZE = 50
PRS_TABLE_URL = "/contacts/prs/table/"
CTZ_TABLE_URL = "/contacts/ctz/table/"
PSN_TABLE_URL = "/contacts/psn/table/"
TEL_TABLE_URL = "/contacts/tel/table/"
EML_TABLE_URL = "/contacts/eml/table/"
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
    keys = ("prs_ids", "prs_page", "ctz_page", "adr_page", "psn_page", "tel_page", "eml_page")
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


def _normalize_adr_positions():
    items = ResidenceAddressRecord.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ResidenceAddressRecord.objects.filter(pk=item.pk).update(position=idx)


def _prs_context(request):
    queryset = PersonRecord.objects.select_related("citizenship").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(pk__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
        item_key="prs_items",
        page_param="prs_page",
        partial_url=PRS_TABLE_URL,
        target="#contacts-persons-table-wrap",
    )


def _psn_context(request):
    queryset = PositionRecord.objects.select_related("person").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
        item_key="psn_items",
        page_param="psn_page",
        partial_url=PSN_TABLE_URL,
        target="#contacts-positions-table-wrap",
    )


def _ctz_context(request):
    queryset = CitizenshipRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
        item_key="ctz_items",
        page_param="ctz_page",
        partial_url=CTZ_TABLE_URL,
        target="#contacts-citizenships-table-wrap",
    )


def _tel_context(request):
    queryset = PhoneRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
        item_key="tel_items",
        page_param="tel_page",
        partial_url=TEL_TABLE_URL,
        target="#contacts-phones-table-wrap",
    )


def _eml_context(request):
    queryset = EmailRecord.objects.select_related("person").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
        item_key="eml_items",
        page_param="eml_page",
        partial_url=EML_TABLE_URL,
        target="#contacts-emails-table-wrap",
    )


def _adr_context(request):
    queryset = ResidenceAddressRecord.objects.select_related("person", "country").order_by("position", "id")
    person_ids = _selected_person_ids(request)
    if person_ids:
        queryset = queryset.filter(person_id__in=person_ids)
    return _paginate_queryset(
        request,
        queryset,
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
@require_http_methods(["GET"])
def tel_table_partial(request):
    return render(request, TEL_TABLE_TEMPLATE, _tel_context(request))


@login_required
@require_http_methods(["GET"])
def eml_table_partial(request):
    return render(request, EML_TABLE_TEMPLATE, _eml_context(request))


@login_required
@require_http_methods(["GET"])
def adr_table_partial(request):
    return render(request, ADR_TABLE_TEMPLATE, _adr_context(request))


@login_required
@require_http_methods(["GET"])
def ctz_table_partial(request):
    return render(request, CTZ_TABLE_TEMPLATE, _ctz_context(request))


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
