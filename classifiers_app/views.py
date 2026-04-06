import csv
import io
import json
import logging
from datetime import date as date_type, datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction
from django.db.models import Count, F, Max, Prefetch, Q
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)

from .models import (
    OKSMCountry,
    OKVCurrency,
    LegalEntityIdentifier,
    TerritorialDivision,
    LivingWage,
    LegalEntityRecord,
    RussianFederationSubjectCode,
    detect_legal_entity_region_by_identifier,
    BusinessEntityRecord,
    BusinessEntityIdentifierRecord,
    BusinessEntityAttributeRecord,
    BusinessEntityReorganizationEvent,
    BusinessEntityRelationRecord,
    resolve_territorial_division_region_code,
)
from .forms import (
    OKSMCountryForm,
    OKVCurrencyForm,
    LegalEntityIdentifierForm,
    TerritorialDivisionForm,
    LivingWageForm,
    LegalEntityRecordForm,
    RussianFederationSubjectCodeForm,
    BusinessEntityRecordForm,
    BusinessEntityIdentifierRecordForm,
    BusinessEntityAttributeRecordForm,
    BusinessEntityLegalAddressRecordForm,
    BusinessEntityRelationRecordForm,
)

PARTIAL_TEMPLATE = "classifiers_app/classifiers_partial.html"
OKSM_TABLE_TEMPLATE = "classifiers_app/oksm_table_partial.html"
OKSM_FORM_TEMPLATE = "classifiers_app/oksm_form.html"
KATD_TABLE_TEMPLATE = "classifiers_app/katd_table_partial.html"
KATD_FORM_TEMPLATE = "classifiers_app/katd_form.html"
RFS_TABLE_TEMPLATE = "classifiers_app/rfs_table_partial.html"
RFS_FORM_TEMPLATE = "classifiers_app/rfs_form.html"
OKV_TABLE_TEMPLATE = "classifiers_app/okv_table_partial.html"
OKV_FORM_TEMPLATE = "classifiers_app/okv_form.html"
LEI_TABLE_TEMPLATE = "classifiers_app/lei_table_partial.html"
LEI_FORM_TEMPLATE = "classifiers_app/lei_form.html"
LW_TABLE_TEMPLATE = "classifiers_app/lw_table_partial.html"
LW_FORM_TEMPLATE = "classifiers_app/lw_form.html"
LER_TABLE_TEMPLATE = "classifiers_app/ler_table_partial.html"
LER_FORM_TEMPLATE = "classifiers_app/ler_form.html"
BER_TABLE_TEMPLATE = "classifiers_app/ber_table_partial.html"
BER_FORM_TEMPLATE = "classifiers_app/ber_form.html"
BEI_TABLE_TEMPLATE = "classifiers_app/bei_table_partial.html"
BEI_FORM_TEMPLATE = "classifiers_app/bei_form.html"
BAT_TABLE_TEMPLATE = "classifiers_app/bat_table_partial.html"
BAT_FORM_TEMPLATE = "classifiers_app/bat_form.html"
BEA_TABLE_TEMPLATE = "classifiers_app/bea_table_partial.html"
BEA_FORM_TEMPLATE = "classifiers_app/bea_form.html"
BRL_TABLE_TEMPLATE = "classifiers_app/brl_table_partial.html"
BRL_FORM_TEMPLATE = "classifiers_app/brl_form.html"

BUSINESS_REGISTRY_PAGE_SIZE = 50
BER_TABLE_URL = "/classifiers/ber/table/"
BEI_TABLE_URL = "/classifiers/bei/table/"
LER_TABLE_URL = "/classifiers/ler/table/"
BEA_TABLE_URL = "/classifiers/bea/table/"
BRL_TABLE_URL = "/classifiers/brl/table/"
BUSINESS_ENTITY_SOURCE_BER = "[База юрлиц / Реестр бизнес-сущностей]"
BUSINESS_ENTITY_SOURCE_LER = "[База юрлиц / Реестр наименований]"
BUSINESS_ENTITY_SOURCE_BRL = "[База юрлиц / Реестр связей]"
PAGINATION_PRESERVED_PARAMS = {
    "business_entity_ids",
    "oksm_date",
    "okv_date",
    "date",
    "lw_date",
    "bei_date",
    "bei_duplicates",
    "bea_date",
    "ler_date",
    "ber_page",
    "bei_page",
    "ler_page",
    "bea_page",
    "brl_page",
}
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "classifiers-updated"
BUSINESS_REGISTRY_TRIGGER_GROUP = "business-registries"


def _set_registry_trigger(response, *, source, affected=None):
    response[HX_TRIGGER_HEADER] = json.dumps(
        {
            HX_EVENT: {
                "source": source,
                "group": BUSINESS_REGISTRY_TRIGGER_GROUP,
                "affected": affected or [],
            }
        },
        ensure_ascii=False,
    )
    return response


def staff_required(user):
    return user.is_authenticated and user.is_staff


# ---------------------------------------------------------------------------
#  Common date helpers
# ---------------------------------------------------------------------------

def _parse_date(raw: str | None) -> date_type | None:
    if not raw:
        return None
    value = (raw or "").strip()
    for parser in (
        lambda item: date_type.fromisoformat(item),
        lambda item: datetime.strptime(item, "%d.%m.%Y").date(),
    ):
        try:
            return parser(value)
        except (ValueError, TypeError):
            continue
    return None


def _get_katd_queryset(as_of: date_type | None = None):
    qs = TerritorialDivision.objects.select_related("country")
    if as_of is None:
        return qs
    return qs.filter(
        effective_date__lte=as_of,
    ).filter(
        Q(abolished_date__isnull=True) | Q(abolished_date__gte=as_of),
    )


def _req_param(request, name):
    """Read param from GET first, then POST (for form submissions that carry filter values)."""
    val = request.GET.get(name)
    if val is None:
        val = request.POST.get(name)
    return val


def _has_param(request, name):
    return name in request.GET or name in request.POST


def _req_list_param(request, name):
    values = request.GET.getlist(name)
    if not values:
        values = request.POST.getlist(name)
    if values:
        return values
    single = _req_param(request, name)
    if single is None:
        return []
    return [single]


def _selected_business_entity_ids(request):
    result = []
    seen = set()
    for raw in _req_list_param(request, "business_entity_ids"):
        for part in str(raw or "").split(","):
            value = part.strip()
            if not value:
                continue
            try:
                entity_id = int(value)
            except (TypeError, ValueError):
                continue
            if entity_id in seen:
                continue
            seen.add(entity_id)
            result.append(entity_id)
    return result


def _request_param_lists(request):
    data = {}
    keys = [
        key
        for key in dict.fromkeys(list(request.GET.keys()) + list(request.POST.keys()))
        if key in PAGINATION_PRESERVED_PARAMS
    ]
    for key in keys:
        values = request.GET.getlist(key)
        if not values:
            values = request.POST.getlist(key)
        if values:
            data[key] = values
    return data


def _build_partial_url(base_url, params):
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params, doseq=True)}"


def _paginate_queryset(request, queryset, *, item_key, page_param, partial_url, target):
    paginator = Paginator(queryset, BUSINESS_REGISTRY_PAGE_SIZE)
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

    pagination = {
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
    }
    return {
        item_key: page_obj.object_list,
        "page_obj": page_obj,
        "pagination": pagination,
    }


# ---------------------------------------------------------------------------
#  OKSM queryset helpers
# ---------------------------------------------------------------------------

def _get_oksm_queryset(as_of: date_type | None = None):
    qs = OKSMCountry.objects.all()
    if as_of is None:
        return qs
    return qs.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=as_of),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=as_of),
    )


def _get_active_oksm_queryset():
    """Countries valid as of today — used for dropdown lists in other forms."""
    today = date_type.today()
    return _get_oksm_queryset(today)


def _oksm_context(request):
    date_filter = _parse_date(_req_param(request, "oksm_date"))
    if date_filter is None and not _has_param(request, "oksm_date"):
        date_filter = date_type.today()
    return {
        "oksm_countries": _get_oksm_queryset(date_filter),
        "oksm_date_filter": date_filter.isoformat() if date_filter else "",
    }


# ---------------------------------------------------------------------------
#  OKV queryset helpers
# ---------------------------------------------------------------------------

def _get_okv_queryset(as_of: date_type | None = None):
    qs = OKVCurrency.objects.prefetch_related("countries").all()
    if as_of is None:
        return qs
    return qs.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=as_of),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=as_of),
    )


def _okv_context(request):
    date_filter = _parse_date(_req_param(request, "okv_date"))
    if date_filter is None and not _has_param(request, "okv_date"):
        date_filter = date_type.today()
    return {
        "okv_currencies": _get_okv_queryset(date_filter),
        "okv_date_filter": date_filter.isoformat() if date_filter else "",
    }


# ---------------------------------------------------------------------------
#  LEI (Классификатор идентификаторов юрлиц) queryset helpers
# ---------------------------------------------------------------------------

def _lei_context(request):
    return {
        "lei_items": LegalEntityIdentifier.objects.select_related("country").order_by("position", "id"),
    }


# ---------------------------------------------------------------------------
#  KATD queryset helpers
# ---------------------------------------------------------------------------

def _katd_context(request):
    date_filter = _parse_date(_req_param(request, "date"))
    if date_filter is None and not _has_param(request, "date"):
        date_filter = date_type.today()
    return {
        "katd_divisions": _get_katd_queryset(date_filter),
        "katd_date_filter": date_filter.isoformat() if date_filter else "",
    }


def _get_rfs_queryset():
    return RussianFederationSubjectCode.objects.order_by("position", "id")


def _rfs_context(request):
    return {
        "rfs_items": _get_rfs_queryset(),
    }


# ---------------------------------------------------------------------------
#  Living Wage queryset helpers
# ---------------------------------------------------------------------------

def _get_lw_queryset(as_of: date_type | None = None):
    qs = LivingWage.objects.select_related("country", "region")
    if as_of is None:
        return qs
    return qs.filter(
        approval_date__lte=as_of,
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=as_of),
    )


def _lw_context(request, param_name="lw_date"):
    date_filter = _parse_date(_req_param(request, param_name))
    if date_filter is None and not _has_param(request, param_name):
        date_filter = date_type.today()
    return {
        "lw_items": _get_lw_queryset(date_filter),
        "lw_date_filter": date_filter.isoformat() if date_filter else "",
    }


# ---------------------------------------------------------------------------
#  LER (База юридических лиц) queryset helpers
# ---------------------------------------------------------------------------

def _get_ler_queryset(as_of: date_type | None = None, business_entity_ids=None):
    qs = LegalEntityRecord.objects.select_related("registration_country", "identifier_record").filter(
        attribute=LegalEntityRecord.ATTRIBUTE_NAME
    )
    if business_entity_ids:
        qs = qs.filter(identifier_record__business_entity_id__in=business_entity_ids)
    if as_of is None:
        return qs
    return qs.filter(
        Q(name_received_date__lte=as_of),
    ).filter(
        Q(name_changed_date__isnull=True) | Q(name_changed_date__gt=as_of),
    )


def _get_last_prefetched_record(records):
    return records[-1] if records else None


def _active_name_record_prefetch():
    return Prefetch(
        "legal_entity_records",
        queryset=LegalEntityRecord.objects.filter(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            is_active=True,
        ).order_by("position", "id"),
        to_attr="active_name_records",
    )


def _active_legal_address_record_prefetch():
    return Prefetch(
        "legal_entity_records",
        queryset=LegalEntityRecord.objects.filter(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            is_active=True,
        ).order_by("position", "id"),
        to_attr="active_legal_address_records",
    )


def _serialize_autocomplete_identifier(identifier_record, name_record, address_record):
    country = identifier_record.registration_country
    return {
        "id": name_record.pk if name_record else identifier_record.pk,
        "identifier_record_id": identifier_record.pk,
        "name_record_id": name_record.pk if name_record else "",
        "legal_address_record_id": address_record.pk if address_record else "",
        "short_name": name_record.short_name or "",
        "full_name": name_record.full_name or "",
        "identifier": identifier_record.identifier_type or "",
        "identifier_type": identifier_record.identifier_type or "",
        "registration_number": identifier_record.number or "",
        "number": identifier_record.number or "",
        "country_id": identifier_record.registration_country_id or "",
        "country_name": country.short_name if country else "",
        "country_code": country.code if country else "",
        "registration_date": identifier_record.registration_date.isoformat() if identifier_record.registration_date else "",
        "region": address_record.registration_region or "",
    }


def _autocomplete_identifier_queryset(query: str):
    qs = BusinessEntityIdentifierRecord.objects.filter(is_active=True).select_related("registration_country")
    if query:
        qs = qs.filter(
            Q(identifier_type__icontains=query)
            | Q(number__icontains=query)
            | Q(registration_country__short_name__icontains=query)
            | Q(registration_country__code__icontains=query)
            | Q(
                legal_entity_records__attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                legal_entity_records__is_active=True,
                legal_entity_records__short_name__icontains=query,
            )
            | Q(
                legal_entity_records__attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                legal_entity_records__is_active=True,
                legal_entity_records__full_name__icontains=query,
            )
            | Q(
                legal_entity_records__attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
                legal_entity_records__is_active=True,
                legal_entity_records__registration_region__icontains=query,
            )
        )
    return qs.prefetch_related(
        _active_name_record_prefetch(),
        _active_legal_address_record_prefetch(),
    ).distinct()


def _collect_autocomplete_results(query: str):
    results = []
    for identifier_record in _autocomplete_identifier_queryset(query):
        name_record = _get_last_prefetched_record(getattr(identifier_record, "active_name_records", []))
        address_record = _get_last_prefetched_record(getattr(identifier_record, "active_legal_address_records", []))
        if not name_record or not address_record:
            continue
        results.append(_serialize_autocomplete_identifier(identifier_record, name_record, address_record))
    results.sort(key=lambda item: ((item["short_name"] or "").lower(), item["identifier_record_id"]))
    return results


def _get_bea_queryset(as_of: date_type | None = None, business_entity_ids=None):
    qs = LegalEntityRecord.objects.select_related("registration_country", "identifier_record").filter(
        attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS
    )
    if business_entity_ids:
        qs = qs.filter(identifier_record__business_entity_id__in=business_entity_ids)
    if as_of is None:
        return qs
    return qs.filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=as_of),
    ).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=as_of),
    )


def _get_bei_queryset(as_of: date_type | None = None, duplicates_filter: str = "all", business_entity_ids=None):
    qs = BusinessEntityIdentifierRecord.objects.select_related("business_entity", "registration_country")
    if business_entity_ids:
        qs = qs.filter(business_entity_id__in=business_entity_ids)
    if as_of is None:
        filtered = qs
    else:
        filtered = qs.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=as_of),
        ).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=as_of),
        )
    if duplicates_filter not in {"yes", "no"}:
        return filtered

    duplicate_numbers = list(
        filtered.values("number")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .values_list("number", flat=True)
    )
    if duplicates_filter == "yes":
        return filtered.filter(number__in=duplicate_numbers)
    return filtered.exclude(number__in=duplicate_numbers)


def _get_ber_queryset(business_entity_ids=None):
    qs = BusinessEntityRecord.objects.order_by("position", "id")
    if business_entity_ids:
        qs = qs.filter(pk__in=business_entity_ids)
    return qs


def _get_brl_queryset(business_entity_ids=None):
    qs = BusinessEntityRelationRecord.objects.select_related(
        "event", "from_business_entity", "to_business_entity"
    )
    if business_entity_ids:
        qs = qs.filter(
            Q(from_business_entity_id__in=business_entity_ids) | Q(to_business_entity_id__in=business_entity_ids)
        )
    return qs.order_by("position", "id")


def _ber_context(request):
    queryset = _get_ber_queryset(_selected_business_entity_ids(request))
    return _paginate_queryset(
        request,
        queryset,
        item_key="ber_items",
        page_param="ber_page",
        partial_url=BER_TABLE_URL,
        target="#business-entities-table-wrap",
    )


def _ler_context(request):
    date_filter = _parse_date(_req_param(request, "ler_date"))
    business_entity_ids = _selected_business_entity_ids(request)
    if date_filter is None and not _has_param(request, "ler_date"):
        date_filter = date_type.today()
    context = _paginate_queryset(
        request,
        _get_ler_queryset(date_filter, business_entity_ids).order_by("position", "id"),
        item_key="ler_items",
        page_param="ler_page",
        partial_url=LER_TABLE_URL,
        target="#ler-table-wrap",
    )
    context["ler_date_filter"] = date_filter.isoformat() if date_filter else ""
    return context


def _bei_context(request):
    date_filter = _parse_date(_req_param(request, "bei_date"))
    duplicates_filter = (_req_param(request, "bei_duplicates") or "all").strip().lower()
    business_entity_ids = _selected_business_entity_ids(request)
    if duplicates_filter not in {"all", "yes", "no"}:
        duplicates_filter = "all"
    context = _paginate_queryset(
        request,
        _get_bei_queryset(date_filter, duplicates_filter, business_entity_ids).order_by("position", "id"),
        item_key="bei_items",
        page_param="bei_page",
        partial_url=BEI_TABLE_URL,
        target="#business-entity-identifiers-table-wrap",
    )
    context["bei_date_filter"] = date_filter.isoformat() if date_filter else ""
    context["bei_duplicates_filter"] = duplicates_filter
    return context


def _bea_context(request):
    date_filter = _parse_date(_req_param(request, "bea_date"))
    business_entity_ids = _selected_business_entity_ids(request)
    if date_filter is None and not _has_param(request, "bea_date"):
        date_filter = date_type.today()
    context = _paginate_queryset(
        request,
        _get_bea_queryset(date_filter, business_entity_ids).order_by("position", "id"),
        item_key="bea_items",
        page_param="bea_page",
        partial_url=BEA_TABLE_URL,
        target="#business-entity-addresses-table-wrap",
    )
    context["bea_date_filter"] = date_filter.isoformat() if date_filter else ""
    return context


def _brl_context(request):
    queryset = _get_brl_queryset(_selected_business_entity_ids(request))
    return _paginate_queryset(
        request,
        queryset,
        item_key="brl_items",
        page_param="brl_page",
        partial_url=BRL_TABLE_URL,
        target="#business-entity-relations-table-wrap",
    )


# ---------------------------------------------------------------------------
#  Common context / render helpers
# ---------------------------------------------------------------------------

def _classifiers_context(request):
    ctx = {}
    ctx.update(_oksm_context(request))
    ctx.update(_okv_context(request))
    ctx.update(_lei_context(request))
    ctx.update(_katd_context(request))
    ctx.update(_rfs_context(request))
    ctx.update(_lw_context(request))
    return ctx


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _classifiers_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _render_katd_updated(request):
    response = render(request, KATD_TABLE_TEMPLATE, _katd_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _render_rfs_updated(request):
    response = render(request, RFS_TABLE_TEMPLATE, _rfs_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_oksm_position():
    last = OKSMCountry.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_okv_position():
    last = OKVCurrency.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_lei_position():
    last = LegalEntityIdentifier.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_katd_position():
    last = TerritorialDivision.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_rfs_position():
    last = RussianFederationSubjectCode.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_lw_updated(request):
    response = render(request, LW_TABLE_TEMPLATE, _lw_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_ber_position():
    last = BusinessEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_ber_updated(request, *, affected=None):
    response = render(
        request,
        BER_TABLE_TEMPLATE,
        _ber_context(request),
    )
    return _set_registry_trigger(response, source="ber-select", affected=affected)


def _next_bei_position():
    last = BusinessEntityIdentifierRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_bei_updated(request, *, affected=None):
    response = render(
        request,
        BEI_TABLE_TEMPLATE,
        _bei_context(request),
    )
    return _set_registry_trigger(response, source="bei-select", affected=affected)


def _next_bat_position():
    last = BusinessEntityAttributeRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _bat_display_items():
    return [
        {
            "attribute_name": LegalEntityRecord.ATTRIBUTE_NAME,
            "subsection_name": "База юрлиц: наименование",
        },
        {
            "attribute_name": LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            "subsection_name": "База юрлиц: юрадрес",
        },
    ]


def _render_bat_updated(request, *, affected=None):
    response = render(
        request,
        BAT_TABLE_TEMPLATE,
        {"bat_items": _bat_display_items()},
    )
    return _set_registry_trigger(response, source="bat-select", affected=affected)


def _next_bea_position():
    return _next_ler_position()


def _render_bea_updated(request, *, affected=None):
    response = render(
        request,
        BEA_TABLE_TEMPLATE,
        _bea_context(request),
    )
    return _set_registry_trigger(response, source="bea-select", affected=affected)


def _next_brl_position():
    last = BusinessEntityRelationRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_bre_position():
    last = BusinessEntityReorganizationEvent.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_reorganization_event_uid():
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


def _create_business_entity_for_merge(name, user):
    business_entity = BusinessEntityRecord.objects.create(
        name=(name or "").strip(),
        record_date=date_type.today(),
        record_author=_ler_record_author(user),
        source=BUSINESS_ENTITY_SOURCE_BRL,
        comment="",
        position=_next_ber_position(),
    )
    _create_minimum_identifier_chain_for_business_entity(business_entity, user)
    return business_entity


def _unique_brl_entity_ids(values):
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(int(value))
    return result


def _build_brl_pairs(from_ids, to_ids):
    pairs = []
    seen = set()
    for from_id in _unique_brl_entity_ids(from_ids):
        for to_id in _unique_brl_entity_ids(to_ids):
            pair = (from_id, to_id)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
    return pairs


def _render_brl_updated(request, *, affected=None):
    response = render(
        request,
        BRL_TABLE_TEMPLATE,
        _brl_context(request),
    )
    return _set_registry_trigger(response, source="brl-select", affected=affected)


def _close_latest_identifier_for_split(from_business_entity_id, event_date):
    if not from_business_entity_id or event_date is None:
        return
    latest_identifier = (
        BusinessEntityIdentifierRecord.objects.filter(business_entity_id=from_business_entity_id)
        .order_by(
            F("valid_from").desc(nulls_last=True),
            F("registration_date").desc(nulls_last=True),
            F("record_date").desc(nulls_last=True),
            "-position",
            "-id",
        )
        .first()
    )
    if latest_identifier is None:
        return
    latest_identifier.valid_to = event_date
    latest_identifier.save(update_fields={"valid_to"})


def _resolve_brl_to_ids(form, user):
    relation_type = (form.cleaned_data.get("relation_type") or "").strip()
    if relation_type != "Слияние":
        if relation_type not in {"Разделение", "Выделение"}:
            return form.cleaned_data.get("to_business_entity_ids") or []
        result = []
        for row in form.cleaned_data.get("split_target_rows") or []:
            existing_id = (row.get("existing_id") or "").strip()
            name = (row.get("name") or "").strip()
            if existing_id:
                BusinessEntityRecord.objects.filter(pk=existing_id).update(name=name)
                result.append(existing_id)
            else:
                business_entity = _create_business_entity_for_merge(name, user)
                result.append(str(business_entity.pk))
        return result

    merge_target_entity_id = form.cleaned_data.get("merge_target_entity_id")
    merge_target_name = (form.cleaned_data.get("merge_target_name") or "").strip()
    if merge_target_entity_id:
        BusinessEntityRecord.objects.filter(pk=merge_target_entity_id).update(name=merge_target_name)
        return [merge_target_entity_id]

    business_entity = _create_business_entity_for_merge(merge_target_name, user)
    return [str(business_entity.pk)]


def _collect_business_entity_autocomplete_results(query: str):
    query_normalized = (query or "").strip().lower()
    if not query_normalized:
        return []

    results = []
    for item in BusinessEntityRecord.objects.only("id", "name").order_by("position", "id").iterator():
        formatted_id = f"{item.pk:05d}-BSN"
        name = (item.name or "").strip()
        haystack = f"{formatted_id} {name}".lower()
        if query_normalized not in haystack:
            continue
        results.append(
            {
                "id": item.pk,
                "formatted_id": formatted_id,
                "name": name,
                "label": f"{formatted_id} {name}".strip(),
            }
        )
    return results


def _serialize_business_entity_filter_item(item):
    formatted_id = f"{item.pk:05d}-BSN"
    name = (item.name or "").strip()
    return {
        "id": item.pk,
        "formatted_id": formatted_id,
        "name": name,
        "summary_label": formatted_id,
        "label": f"{formatted_id} {name}".strip(),
    }


def _business_entity_filter_items(*, ids=None):
    items = []
    queryset = BusinessEntityRecord.objects.only("id", "name").order_by("position", "id")
    if ids:
        queryset = queryset.filter(pk__in=ids)
    for item in queryset.iterator():
        items.append(_serialize_business_entity_filter_item(item))
    return items


def _business_entity_filter_search_items(query: str):
    items = []
    for item in _collect_business_entity_autocomplete_results(query):
        items.append(
            {
                "id": item["id"],
                "formatted_id": item["formatted_id"],
                "name": item["name"],
                "summary_label": item["formatted_id"],
                "label": item["label"],
            }
        )
    return items


def _collect_identifier_record_autocomplete_results(query: str):
    query_normalized = (query or "").strip().lower()
    if not query_normalized:
        return []

    name_prefetch = Prefetch(
        "legal_entity_records",
        queryset=LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_NAME).order_by("-is_active", "position", "id"),
        to_attr="autocomplete_name_records",
    )
    results = []
    queryset = (
        BusinessEntityIdentifierRecord.objects.select_related("business_entity")
        .prefetch_related(name_prefetch)
        .order_by("position", "id")
    )
    for item in queryset:
        formatted_id = f"{item.pk:05d}-IDN"
        identifier_type = (item.identifier_type or "").strip()
        number = (item.number or "").strip()
        short_name = ""
        for name_record in getattr(item, "autocomplete_name_records", []):
            short_name = (name_record.short_name or "").strip()
            if short_name:
                break
        haystack = f"{formatted_id} {identifier_type} {number} {short_name}".lower()
        if query_normalized not in haystack:
            continue
        label_parts = [formatted_id, identifier_type, number, short_name]
        label = " ".join(part for part in label_parts if part).strip()
        results.append(
            {
                "id": item.pk,
                "formatted_id": formatted_id,
                "identifier_type": identifier_type,
                "number": number,
                "short_name": short_name,
                "country_id": item.registration_country_id or "",
                "region": item.registration_region or "",
                "registration_date": item.registration_date.isoformat() if item.registration_date else "",
                "label": label,
            }
        )
    return results


@login_required
@user_passes_test(staff_required)
def brl_business_entity_search(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 1:
        return JsonResponse({"results": [], "total_count": 0})
    results = _collect_business_entity_autocomplete_results(q)
    return JsonResponse({"results": results[:15], "total_count": len(results)})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def business_entity_filter_options(request):
    q = (request.GET.get("q") or "").strip()
    ids = _req_list_param(request, "ids")
    if q:
        items = _business_entity_filter_search_items(q)
    elif ids:
        items = _business_entity_filter_items(ids=ids)
    else:
        items = _business_entity_filter_items()
    return JsonResponse({"results": items, "total_count": len(items)})


@login_required
@user_passes_test(staff_required)
def bea_identifier_record_search(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 1:
        return JsonResponse({"results": [], "total_count": 0})
    results = _collect_identifier_record_autocomplete_results(q)
    return JsonResponse({"results": results[:15], "total_count": len(results)})


def _validation_error(message: str, status: int = 409):
    return HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")


def _form_error_messages(form):
    messages = []
    for field in form:
        label = field.label or field.name
        for error in field.errors:
            messages.append(f"{label}: {error}")
    for error in form.non_field_errors():
        messages.append(str(error))
    if not messages:
        raw_text = (form.errors.as_text() or "").strip()
        if raw_text:
            messages.extend([line.strip("* ").strip() for line in raw_text.splitlines() if line.strip()])
    return messages


def _ensure_identifier_has_unified_record(identifier_record, user):
    if LegalEntityRecord.objects.filter(identifier_record=identifier_record).exists():
        return
    LegalEntityRecord.objects.create(
        attribute=LegalEntityRecord.ATTRIBUTE_NAME,
        identifier_record=identifier_record,
        short_name=identifier_record.business_entity.name or "",
        record_date=date_type.today(),
        record_author=_ler_record_author(user),
        position=_next_ler_position(),
    )


def _ensure_identifier_has_legal_address_record(identifier_record, user=None):
    address_record = (
        LegalEntityRecord.objects.filter(
            identifier_record=identifier_record,
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            is_active=True,
        )
        .order_by("position", "id")
        .first()
    )
    if address_record is None:
        record_author = _ler_record_author(user) if user else ""
        record_date = date_type.today() if user else identifier_record.record_date
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=identifier_record,
            registration_country=identifier_record.registration_country,
            registration_region=identifier_record.registration_region or "",
            record_date=record_date,
            record_author=record_author,
            valid_from=identifier_record.valid_from,
            position=_next_ler_position(),
        )
        return

    update_fields = []
    if not address_record.registration_country_id and identifier_record.registration_country_id:
        address_record.registration_country = identifier_record.registration_country
        update_fields.append("registration_country")
    if not (address_record.registration_region or "") and (identifier_record.registration_region or ""):
        address_record.registration_region = identifier_record.registration_region or ""
        update_fields.append("registration_region")
    if address_record.valid_from is None and identifier_record.valid_from is not None:
        address_record.valid_from = identifier_record.valid_from
        update_fields.append("valid_from")
    if address_record.record_date is None and identifier_record.record_date is not None:
        address_record.record_date = identifier_record.record_date
        update_fields.append("record_date")
    elif user and address_record.record_date is None:
        address_record.record_date = date_type.today()
        update_fields.append("record_date")
    if user and not (address_record.record_author or ""):
        address_record.record_author = _ler_record_author(user)
        update_fields.append("record_author")
    if update_fields:
        update_fields.append("updated_at")
        address_record.save(update_fields=update_fields)


def _create_minimum_identifier_chain_for_business_entity(business_entity, user):
    identifier_record = BusinessEntityIdentifierRecord.objects.create(
        business_entity=business_entity,
        identifier_type="",
        number="",
        registration_country=None,
        registration_region="",
        is_active=True,
        position=_next_bei_position(),
    )
    _ensure_identifier_has_unified_record(identifier_record, user)
    _ensure_identifier_has_legal_address_record(identifier_record, user)
    return identifier_record


def _ensure_name_record_has_identifier_chain(record, user, business_entity_source=""):
    if record.attribute != LegalEntityRecord.ATTRIBUTE_NAME:
        return record.identifier_record
    if record.identifier_record_id:
        identifier_record = record.identifier_record
        identifier_record.registration_country = record.registration_country
        identifier_record.registration_region = record.registration_region or ""
        identifier_record.registration_date = record.registration_date
        identifier_record.registration_code = record.registration_country.code if record.registration_country_id else ""
        identifier_record.save()
        _ensure_identifier_has_legal_address_record(identifier_record, user)
        return record.identifier_record

    business_entity = BusinessEntityRecord.objects.create(
        name=record.short_name or record.full_name or "",
        record_date=date_type.today() if user else None,
        record_author=_ler_record_author(user) if user else "",
        source=business_entity_source or "",
        comment="",
        position=_next_ber_position(),
    )
    identifier_record = BusinessEntityIdentifierRecord.objects.create(
        business_entity=business_entity,
        identifier_type=record.identifier or "",
        registration_country=record.registration_country,
        registration_region=record.registration_region or "",
        registration_date=record.registration_date,
        number=record.registration_number or "",
        valid_from=record.registration_date,
        valid_to=None,
        is_active=True,
        position=_next_bei_position(),
    )
    record.identifier_record = identifier_record
    record.save(update_fields=["identifier_record", "updated_at"])
    _ensure_identifier_has_legal_address_record(identifier_record, user)
    return identifier_record


def _find_name_record_for_registry_sync(short_name, country, identifier_type, registration_number, registration_date):
    candidates = list(
        LegalEntityRecord.objects.filter(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            short_name=short_name,
        )
        .select_related("identifier_record__registration_country")
        .order_by("position", "id")
    )
    country_id = country.pk if country else None
    identifier_type = (identifier_type or "").strip()
    registration_number = (registration_number or "").strip()

    for record in reversed(candidates):
        identifier_record = record.identifier_record
        if identifier_record is None:
            continue
        if identifier_record.registration_country_id != country_id:
            continue
        if identifier_type and (identifier_record.identifier_type or "") != identifier_type:
            continue
        if registration_number and (identifier_record.number or "") != registration_number:
            continue
        if registration_date and identifier_record.registration_date != registration_date:
            continue
        return record

    for record in reversed(candidates):
        if record.is_active:
            return record
    return candidates[-1] if candidates else None


def _selected_identifier_record_for_registry_sync(selected_identifier_record_id):
    if selected_identifier_record_id in (None, ""):
        return None
    try:
        pk = int(str(selected_identifier_record_id).strip())
    except (TypeError, ValueError):
        return None
    return BusinessEntityIdentifierRecord.objects.filter(pk=pk).first()


def _create_registry_entry_from_manual_input(
    short_name,
    country,
    identifier_type,
    registration_number,
    registration_date,
    user=None,
    business_entity_source="",
):
    record = LegalEntityRecord(
        attribute=LegalEntityRecord.ATTRIBUTE_NAME,
        short_name=short_name,
        full_name="",
        registration_country=country,
        registration_region="",
        identifier=identifier_type,
        registration_number=registration_number,
        registration_date=registration_date,
        name_received_date=registration_date,
        position=_next_ler_position(),
    )
    if user:
        record.record_date = date_type.today()
        record.record_author = _ler_record_author(user)
    record.save()
    return _ensure_name_record_has_identifier_chain(record, user, business_entity_source=business_entity_source)


@transaction.atomic
def sync_autocomplete_registry_entry(
    short_name,
    country,
    identifier_type,
    registration_number,
    registration_date,
    user=None,
    selected_identifier_record_id=None,
    selected_from_autocomplete=False,
    business_entity_source="",
):
    short_name = (short_name or "").strip()
    if not short_name:
        return None

    identifier_type = (identifier_type or "").strip()
    registration_number = (registration_number or "").strip()
    if selected_from_autocomplete:
        explicit_identifier = _selected_identifier_record_for_registry_sync(selected_identifier_record_id)
        if explicit_identifier is not None:
            return explicit_identifier

    return _create_registry_entry_from_manual_input(
        short_name=short_name,
        country=country,
        identifier_type=identifier_type,
        registration_number=registration_number,
        registration_date=registration_date,
        user=user,
        business_entity_source=business_entity_source,
    )


def _next_ler_position():
    last = LegalEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_ler_updated(request, *, affected=None):
    response = render(request, LER_TABLE_TEMPLATE, _ler_context(request))
    return _set_registry_trigger(response, source="ler-select", affected=affected)


def _next_lw_position():
    last = LivingWage.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


# ---------------------------------------------------------------------------
#  Classifiers partial (initial load)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def classifiers_partial(request):
    return render(request, PARTIAL_TEMPLATE, _classifiers_context(request))


# ---------------------------------------------------------------------------
#  ОКСМ — partial для HTMX-фильтрации по дате
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def oksm_table_partial(request):
    return render(request, OKSM_TABLE_TEMPLATE, _oksm_context(request))


# ---------------------------------------------------------------------------
#  ОКВ — partial для HTMX-фильтрации по дате
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def okv_table_partial(request):
    return render(request, OKV_TABLE_TEMPLATE, _okv_context(request))


# ---------------------------------------------------------------------------
#  LEI (Классификатор идентификаторов юрлиц) — partial
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def lei_table_partial(request):
    return render(request, LEI_TABLE_TEMPLATE, _lei_context(request))


# ---------------------------------------------------------------------------
#  ОКСМ CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def oksm_form_create(request):
    if request.method == "GET":
        form = OKSMCountryForm()
        return render(request, OKSM_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = OKSMCountryForm(request.POST)
    if not form.is_valid():
        return render(request, OKSM_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_oksm_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def oksm_form_edit(request, pk: int):
    country = get_object_or_404(OKSMCountry, pk=pk)
    if request.method == "GET":
        form = OKSMCountryForm(instance=country)
        return render(request, OKSM_FORM_TEMPLATE, {"form": form, "action": "edit", "country": country})
    form = OKSMCountryForm(request.POST, instance=country)
    if not form.is_valid():
        return render(request, OKSM_FORM_TEMPLATE, {"form": form, "action": "edit", "country": country})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def oksm_delete(request, pk: int):
    get_object_or_404(OKSMCountry, pk=pk).delete()
    return _render_updated(request)


def _normalize_oksm_positions():
    items = OKSMCountry.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            OKSMCountry.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def oksm_move_up(request, pk: int):
    _normalize_oksm_positions()
    items = list(OKSMCountry.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        OKSMCountry.objects.filter(pk=cur.id).update(position=prev.position)
        OKSMCountry.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_oksm_positions()
    return _render_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def oksm_move_down(request, pk: int):
    _normalize_oksm_positions()
    items = list(OKSMCountry.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        OKSMCountry.objects.filter(pk=cur.id).update(position=nxt.position)
        OKSMCountry.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_oksm_positions()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  ОКСМ CSV upload
# ---------------------------------------------------------------------------

def _parse_csv_date(raw: str) -> date_type | None:
    raw = raw.strip()
    if not raw or raw == "—":
        return None
    from datetime import datetime
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


@login_required
@user_passes_test(staff_required)
@require_POST
def oksm_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)

    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)

    # Try comma delimiter if only 1 column detected
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)

    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    header = rows[0]
    data_rows = rows[1:]
    created_count = 0
    errors = []
    position = _next_oksm_position()

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 6:
            errors.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается минимум 6).")
            continue

        try:
            number = int(row[0].strip()) if row[0].strip() else 0
            code = row[1].strip()[:3]
            short_name = row[2].strip()
            full_name = row[3].strip() if len(row) > 3 else ""
            alpha2 = row[4].strip().upper()[:2] if len(row) > 4 else ""
            alpha3 = row[5].strip().upper()[:3] if len(row) > 5 else ""
            approval_date = _parse_csv_date(row[6]) if len(row) > 6 else None
            expiry_date = _parse_csv_date(row[7]) if len(row) > 7 else None
            source = row[8].strip() if len(row) > 8 else ""

            if not short_name:
                errors.append(f"Строка {i}: отсутствует наименование страны (краткое).")
                continue

            OKSMCountry.objects.create(
                number=number,
                code=code,
                short_name=short_name,
                full_name=full_name,
                alpha2=alpha2,
                alpha3=alpha3,
                approval_date=approval_date,
                expiry_date=expiry_date,
                source=source,
                position=position,
            )
            position += 1
            created_count += 1
        except Exception as exc:
            logger.exception("CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {"ok": True, "created": created_count}
    if errors:
        result["warnings"] = errors[:20]
    return JsonResponse(result)


# ---------------------------------------------------------------------------
#  ОКВ CSV upload
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_POST
def okv_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)

    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    data_rows = rows[1:]
    created_count = 0
    errors = []
    position = _next_okv_position()

    all_countries = list(OKSMCountry.objects.all().values("id", "short_name", "code", "approval_date", "expiry_date"))

    def find_countries_for_date(country_names_raw, approval_date, row_num):
        """Parse country names, match against OKSM filtered by date. Returns (found_ids, row_errors)."""
        found_ids = []
        row_errors = []
        if not country_names_raw or not country_names_raw.strip():
            return found_ids, row_errors

        names = [n.strip() for n in country_names_raw.split(";") if n.strip()]

        active_countries = []
        for c in all_countries:
            if approval_date:
                ad = c["approval_date"]
                ed = c["expiry_date"]
                if ad and ad > approval_date:
                    continue
                if ed and ed < approval_date:
                    continue
            active_countries.append(c)

        name_to_country = {}
        for c in active_countries:
            name_to_country[c["short_name"].strip().lower()] = c

        for name in names:
            key = name.strip().lower()
            country = name_to_country.get(key)
            if country:
                found_ids.append(country["id"])
            else:
                similar = []
                for c in active_countries:
                    cn = c["short_name"].strip().lower()
                    if key in cn or cn in key:
                        similar.append(c["short_name"])

                date_str = approval_date.strftime("%d.%m.%Y") if approval_date else "не указана"
                err_msg = (
                    f'Строка {row_num}: страна "{name}" не найдена в ОКСМ '
                    f'(фильтр по дате: {date_str}).'
                )
                if similar:
                    err_msg += f' Похожие: {"; ".join(similar[:5])}.'
                row_errors.append(err_msg)

        return found_ids, row_errors

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 3:
            errors.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается минимум 3).")
            continue

        try:
            code_numeric = row[0].strip()[:3]
            code_alpha = row[1].strip()[:3]
            name = row[2].strip()
            abbreviation = row[3].strip() if len(row) > 3 else ""
            symbol = row[4].strip() if len(row) > 4 else ""
            countries_raw = row[5].strip() if len(row) > 5 else ""
            approval_date = _parse_csv_date(row[6]) if len(row) > 6 else None
            expiry_date = _parse_csv_date(row[7]) if len(row) > 7 else None
            source = row[8].strip() if len(row) > 8 else ""

            if not name:
                errors.append(f"Строка {i}: отсутствует наименование валюты.")
                continue

            country_ids, country_errors = find_countries_for_date(countries_raw, approval_date, i)
            errors.extend(country_errors)

            obj = OKVCurrency.objects.create(
                code_numeric=code_numeric,
                code_alpha=code_alpha,
                name=name,
                abbreviation=abbreviation,
                symbol=symbol,
                approval_date=approval_date,
                expiry_date=expiry_date,
                source=source,
                position=position,
            )
            if country_ids:
                obj.countries.set(country_ids)
                obj.update_countries_codes()
            position += 1
            created_count += 1

        except Exception as exc:
            logger.exception("OKV CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {"ok": True, "created": created_count}
    if errors:
        result["warnings"] = errors[:50]
    return JsonResponse(result)


# ---------------------------------------------------------------------------
#  ОКВ CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def okv_form_create(request):
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = OKVCurrencyForm()
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    form = OKVCurrencyForm(request.POST)
    if not form.is_valid():
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_okv_position()
    obj.save()
    form.save_m2m()
    obj.update_countries_codes()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def okv_form_edit(request, pk: int):
    currency = get_object_or_404(OKVCurrency, pk=pk)
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = OKVCurrencyForm(instance=currency)
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "edit", "currency": currency, "today_iso": today_iso})
    form = OKVCurrencyForm(request.POST, instance=currency)
    if not form.is_valid():
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "edit", "currency": currency, "today_iso": today_iso})
    form.save()
    currency.update_countries_codes()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def okv_delete(request, pk: int):
    get_object_or_404(OKVCurrency, pk=pk).delete()
    return _render_updated(request)


def _normalize_okv_positions():
    items = OKVCurrency.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            OKVCurrency.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def okv_move_up(request, pk: int):
    _normalize_okv_positions()
    items = list(OKVCurrency.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        OKVCurrency.objects.filter(pk=cur.id).update(position=prev.position)
        OKVCurrency.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_okv_positions()
    return _render_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def okv_move_down(request, pk: int):
    _normalize_okv_positions()
    items = list(OKVCurrency.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        OKVCurrency.objects.filter(pk=cur.id).update(position=nxt.position)
        OKVCurrency.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_okv_positions()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  LEI (Классификатор идентификаторов юрлиц) CRUD
# ---------------------------------------------------------------------------

def _lei_form_context(form, action, lei=None):
    """Build context for LEI form template with country_codes_json."""
    qs = form.fields["country"].queryset
    country_codes = {str(c.id): c.code for c in qs}
    ctx = {"form": form, "action": action, "country_codes_json": json.dumps(country_codes)}
    if lei is not None:
        ctx["lei"] = lei
    return ctx


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def lei_form_create(request):
    if request.method == "GET":
        form = LegalEntityIdentifierForm()
        return render(request, LEI_FORM_TEMPLATE, _lei_form_context(form, "create"))
    form = LegalEntityIdentifierForm(request.POST)
    if not form.is_valid():
        return render(request, LEI_FORM_TEMPLATE, _lei_form_context(form, "create"))
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_lei_position()
    if obj.country:
        obj.code = obj.country.code
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def lei_form_edit(request, pk: int):
    lei = get_object_or_404(LegalEntityIdentifier, pk=pk)
    if request.method == "GET":
        form = LegalEntityIdentifierForm(instance=lei)
        return render(request, LEI_FORM_TEMPLATE, _lei_form_context(form, "edit", lei))
    form = LegalEntityIdentifierForm(request.POST, instance=lei)
    if not form.is_valid():
        return render(request, LEI_FORM_TEMPLATE, _lei_form_context(form, "edit", lei))
    obj = form.save(commit=False)
    if obj.country:
        obj.code = obj.country.code
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def lei_delete(request, pk: int):
    get_object_or_404(LegalEntityIdentifier, pk=pk).delete()
    return _render_updated(request)


def _normalize_lei_positions():
    items = LegalEntityIdentifier.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            LegalEntityIdentifier.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def lei_move_up(request, pk: int):
    _normalize_lei_positions()
    items = list(LegalEntityIdentifier.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LegalEntityIdentifier.objects.filter(pk=cur.id).update(position=prev.position)
        LegalEntityIdentifier.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_lei_positions()
    return _render_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def lei_move_down(request, pk: int):
    _normalize_lei_positions()
    items = list(LegalEntityIdentifier.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LegalEntityIdentifier.objects.filter(pk=cur.id).update(position=nxt.position)
        LegalEntityIdentifier.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_lei_positions()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  КАТД — partial для HTMX-фильтрации по дате
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def katd_table_partial(request):
    return render(request, KATD_TABLE_TEMPLATE, _katd_context(request))


# ---------------------------------------------------------------------------
#  КАТД CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def katd_form_create(request):
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = TerritorialDivisionForm()
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    form = TerritorialDivisionForm(request.POST)
    if not form.is_valid():
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_katd_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def katd_form_edit(request, pk: int):
    division = get_object_or_404(TerritorialDivision, pk=pk)
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = TerritorialDivisionForm(instance=division)
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "edit", "division": division, "today_iso": today_iso})
    form = TerritorialDivisionForm(request.POST, instance=division)
    if not form.is_valid():
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "edit", "division": division, "today_iso": today_iso})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def katd_delete(request, pk: int):
    get_object_or_404(TerritorialDivision, pk=pk).delete()
    return _render_updated(request)


def _normalize_katd_positions():
    items = TerritorialDivision.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            TerritorialDivision.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def katd_move_up(request, pk: int):
    _normalize_katd_positions()
    items = list(TerritorialDivision.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        TerritorialDivision.objects.filter(pk=cur.id).update(position=prev.position)
        TerritorialDivision.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_katd_positions()
    return _render_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def katd_move_down(request, pk: int):
    _normalize_katd_positions()
    items = list(TerritorialDivision.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        TerritorialDivision.objects.filter(pk=cur.id).update(position=nxt.position)
        TerritorialDivision.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_katd_positions()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  КАТД CSV upload
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_POST
def katd_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)

    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    data_rows = rows[1:]
    created_count = 0
    errors = []
    position = _next_katd_position()

    all_countries = {
        c.short_name.strip().lower(): c
        for c in OKSMCountry.objects.all()
    }
    all_countries_by_code = {
        c.code.strip(): c
        for c in OKSMCountry.objects.all()
    }

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 4:
            errors.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается минимум 4).")
            continue

        try:
            col_idx = 0
            country_code_raw = row[col_idx].strip() if len(row) > col_idx else ""
            col_idx = 1
            country_name_raw = row[col_idx].strip() if len(row) > col_idx else ""
            col_idx = 2
            region_name = row[col_idx].strip() if len(row) > col_idx else ""
            col_idx = 3
            region_code = row[col_idx].strip() if len(row) > col_idx else ""
            col_idx = 4
            effective_date = _parse_csv_date(row[col_idx]) if len(row) > col_idx else None
            col_idx = 5
            abolished_date = _parse_csv_date(row[col_idx]) if len(row) > col_idx else None
            col_idx = 6
            source = row[col_idx].strip() if len(row) > col_idx else ""

            country = None
            if country_code_raw:
                country = all_countries_by_code.get(country_code_raw)
            if not country and country_name_raw:
                country = all_countries.get(country_name_raw.lower())

            if not country:
                similar = [c for cn, c in all_countries.items() if country_name_raw.lower() in cn or cn in country_name_raw.lower()]
                err = f'Строка {i}: страна "{country_name_raw}" (код "{country_code_raw}") не найдена в ОКСМ.'
                if similar:
                    err += f' Похожие: {"; ".join(s.short_name for s in similar[:5])}.'
                errors.append(err)
                continue

            if not region_name:
                errors.append(f"Строка {i}: отсутствует название региона.")
                continue

            if not effective_date:
                errors.append(f"Строка {i}: отсутствует или некорректна дата образования.")
                continue

            TerritorialDivision.objects.create(
                country=country,
                region_name=region_name,
                region_code=region_code,
                effective_date=effective_date,
                abolished_date=abolished_date,
                source=source,
                position=position,
            )
            position += 1
            created_count += 1

        except Exception as exc:
            logger.exception("KATD CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {"ok": True, "created": created_count}
    if errors:
        result["warnings"] = errors[:50]
    return JsonResponse(result)


# ---------------------------------------------------------------------------
#  Величина прожиточного минимума — AJAX endpoint for dependent region dropdown
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def lw_regions_for_country(request):
    country_code = request.GET.get("country_code")
    if not country_code:
        return JsonResponse([], safe=False)
    as_of = _parse_date(request.GET.get("date")) or date_type.today()
    divisions = TerritorialDivision.objects.filter(
        country__code=country_code,
        effective_date__lte=as_of,
    ).filter(
        Q(abolished_date__isnull=True) | Q(abolished_date__gte=as_of),
    ).order_by("region_name")
    data = [{"id": d.pk, "name": d.region_name, "code": d.region_code} for d in divisions]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET"])
def lw_currency_for_country(request):
    country_code = request.GET.get("country_code")
    if not country_code:
        return JsonResponse({"code": ""})
    today = date_type.today()
    currency = OKVCurrency.objects.filter(
        countries__code=country_code,
    ).filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).first()
    return JsonResponse({"code": currency.code_alpha if currency else ""})


@login_required
@require_http_methods(["GET"])
def country_code_lookup(request):
    country_id = request.GET.get("country_id")
    if not country_id:
        return JsonResponse({"code": ""})
    try:
        country = OKSMCountry.objects.only("code").get(pk=country_id)
        return JsonResponse({"code": country.code})
    except OKSMCountry.DoesNotExist:
        return JsonResponse({"code": ""})


def ler_search(request):
    """Search active entity autocomplete data assembled from name, identifier, and address registries."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 1:
        return JsonResponse({"results": [], "total_count": 0})
    results = _collect_autocomplete_results(q)
    return JsonResponse({"results": results[:15], "total_count": len(results)})


def ler_identifiers_for_country(request):
    """Return LegalEntityIdentifier entries for a given country."""
    country_id = request.GET.get("country_id")
    if not country_id:
        return JsonResponse({"identifiers": []})
    try:
        country_id = int(country_id)
    except (ValueError, TypeError):
        return JsonResponse({"identifiers": []})
    items = LegalEntityIdentifier.objects.filter(country_id=country_id).order_by("position", "id")
    data = [{"id": i.id, "identifier": i.identifier, "full_name": i.full_name} for i in items]
    return JsonResponse({"identifiers": data})


def ler_regions_for_country(request):
    """Return unique TerritorialDivision region names for a given country."""
    country_id = request.GET.get("country_id")
    as_of = _parse_date(request.GET.get("date"))
    if not country_id:
        return JsonResponse({"regions": []})
    try:
        country_id = int(country_id)
    except (ValueError, TypeError):
        return JsonResponse({"regions": []})

    seen_names = set()
    region_names = []
    for region_name in (
        _get_katd_queryset(as_of).filter(country_id=country_id)
        .order_by("region_name", "id")
        .values_list("region_name", flat=True)
    ):
        if region_name in seen_names:
            continue
        seen_names.add(region_name)
        region_names.append(region_name)
    return JsonResponse({"regions": region_names})


@login_required
@require_http_methods(["GET"])
def ler_region_code_for_country(request):
    country_id = request.GET.get("country_id")
    region_name = request.GET.get("region_name")
    if not country_id or not region_name:
        return JsonResponse({"code": ""})
    try:
        country_id = int(country_id)
    except (ValueError, TypeError):
        return JsonResponse({"code": ""})
    return JsonResponse(
        {
            "code": resolve_territorial_division_region_code(
                country_id=country_id,
                region_name=region_name,
                as_of=_parse_date(request.GET.get("date")),
            )
        }
    )


def ler_region_autofill(request):
    identifier = (request.GET.get("identifier") or "").strip()
    registration_number = (request.GET.get("registration_number") or "").strip()
    region = detect_legal_entity_region_by_identifier(identifier, registration_number)
    return JsonResponse({"region": region})


@login_required
@require_http_methods(["GET"])
def okv_countries_for_date(request):
    """Return countries valid on a given date, sorted by short_name, for the OKV form."""
    raw_date = request.GET.get("date", "")
    as_of = _parse_date(raw_date)
    if as_of is None:
        as_of = date_type.today()
    qs = _get_oksm_queryset(as_of).order_by("short_name")
    data = [{"id": c.pk, "label": f"{c.code}  {c.short_name}"} for c in qs]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET"])
def katd_countries_for_date(request):
    """Return countries valid on a given date, sorted by short_name, for the KATD form."""
    raw_date = request.GET.get("date", "")
    as_of = _parse_date(raw_date)
    if as_of is None:
        as_of = date_type.today()
    qs = _get_oksm_queryset(as_of).order_by("short_name")
    data = [{"id": c.pk, "label": c.short_name} for c in qs]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET"])
def rfs_table_partial(request):
    return render(request, RFS_TABLE_TEMPLATE, _rfs_context(request))


def _resolve_region_code_by_subject_name(subject_name: str) -> str:
    if not subject_name:
        return ""
    division = TerritorialDivision.objects.filter(
        region_name__iexact=subject_name,
        country__short_name="Россия",
    ).order_by("position", "id").first()
    if division is None:
        division = TerritorialDivision.objects.filter(
            region_name__iexact=subject_name,
        ).order_by("position", "id").first()
    return division.region_code if division else ""


@login_required
@require_http_methods(["GET"])
def rfs_oktmo_for_subject(request):
    subject_name = (request.GET.get("subject_name") or "").strip()
    return JsonResponse({"code": _resolve_region_code_by_subject_name(subject_name)})


# ---------------------------------------------------------------------------
#  Коды субъектов Российской Федерации CRUD
# ---------------------------------------------------------------------------


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def rfs_form_create(request):
    if request.method == "GET":
        form = RussianFederationSubjectCodeForm()
        return render(request, RFS_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = RussianFederationSubjectCodeForm(request.POST)
    if not form.is_valid():
        resp = render(request, RFS_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.oktmo_code = _resolve_region_code_by_subject_name(obj.subject_name)
    if not getattr(obj, "position", 0):
        obj.position = _next_rfs_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def rfs_form_edit(request, pk: int):
    item = get_object_or_404(RussianFederationSubjectCode, pk=pk)
    if request.method == "GET":
        form = RussianFederationSubjectCodeForm(instance=item)
        return render(request, RFS_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
    form = RussianFederationSubjectCodeForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(request, RFS_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.oktmo_code = _resolve_region_code_by_subject_name(obj.subject_name)
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def rfs_delete(request, pk: int):
    get_object_or_404(RussianFederationSubjectCode, pk=pk).delete()
    return _render_rfs_updated(request)


def _normalize_rfs_positions():
    items = RussianFederationSubjectCode.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            RussianFederationSubjectCode.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def rfs_move_up(request, pk: int):
    _normalize_rfs_positions()
    items = list(RussianFederationSubjectCode.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        RussianFederationSubjectCode.objects.filter(pk=cur.id).update(position=prev.position)
        RussianFederationSubjectCode.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_rfs_positions()
    return _render_rfs_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def rfs_move_down(request, pk: int):
    _normalize_rfs_positions()
    items = list(RussianFederationSubjectCode.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        RussianFederationSubjectCode.objects.filter(pk=cur.id).update(position=nxt.position)
        RussianFederationSubjectCode.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_rfs_positions()
    return _render_rfs_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def rfs_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)
    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    data_rows = rows[1:]
    created_count = 0
    errors = []
    position = _next_rfs_position()

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        try:
            if len(row) < 4:
                errors.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается минимум 4).")
                continue

            subject_name = row[0].strip() if len(row) > 0 else ""
            oktmo_code_raw = row[1].strip() if len(row) > 1 else ""
            fns_code = row[2].strip() if len(row) > 2 else ""
            source = row[3].strip() if len(row) > 3 else ""

            if not subject_name:
                errors.append(f"Строка {i}: отсутствует наименование субъекта Российской Федерации.")
                continue
            if not oktmo_code_raw:
                errors.append(f"Строка {i}: отсутствует код региона ОКТМО.")
                continue

            oktmo_code_expected = _resolve_region_code_by_subject_name(subject_name)
            if not oktmo_code_expected:
                errors.append(f'Строка {i}: субъект "{subject_name}" не найден в КАТД.')
                continue
            if oktmo_code_raw != oktmo_code_expected:
                errors.append(
                    f'Строка {i}: код региона ОКТМО "{oktmo_code_raw}" не соответствует КАТД '
                    f'для субъекта "{subject_name}" (ожидается "{oktmo_code_expected}").'
                )
                continue

            RussianFederationSubjectCode.objects.create(
                subject_name=subject_name,
                oktmo_code=oktmo_code_raw,
                fns_code=fns_code,
                source=source,
                position=position,
            )
            position += 1
            created_count += 1
        except Exception as exc:
            logger.exception("RFS CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {"ok": True, "created": created_count}
    if errors:
        result["warnings"] = errors[:50]
    return JsonResponse(result)


# ---------------------------------------------------------------------------
#  Реестр бизнес-сущностей
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def ber_table_partial(request):
    return render(
        request,
        BER_TABLE_TEMPLATE,
        _ber_context(request),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ber_form_create(request):
    if request.method == "GET":
        form = BusinessEntityRecordForm()
        return render(
            request,
            BER_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                "record_date_display": "",
                "record_author_display": "",
                "source_display": BUSINESS_ENTITY_SOURCE_BER,
            },
        )
    form = BusinessEntityRecordForm(request.POST)
    if not form.is_valid():
        resp = render(
            request,
            BER_FORM_TEMPLATE,
            {
                "form": form,
                "action": "create",
                "record_date_display": "",
                "record_author_display": "",
                "source_display": BUSINESS_ENTITY_SOURCE_BER,
            },
        )
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_ber_position()
    if not obj.record_date:
        obj.record_date = date_type.today()
    if not (obj.record_author or ""):
        obj.record_author = _ler_record_author(request.user)
    if not (obj.source or ""):
        obj.source = BUSINESS_ENTITY_SOURCE_BER
    obj.save()
    _create_minimum_identifier_chain_for_business_entity(obj, request.user)
    return _render_ber_updated(request, affected=["bei-select", "ler-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ber_form_edit(request, pk: int):
    item = get_object_or_404(BusinessEntityRecord, pk=pk)
    if request.method == "GET":
        form = BusinessEntityRecordForm(instance=item)
        return render(
            request,
            BER_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
    form = BusinessEntityRecordForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(
            request,
            BER_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "item": item,
                "record_date_display": item.record_date.strftime("%d.%m.%Y") if item.record_date else "",
                "record_author_display": item.record_author or "",
                "source_display": item.source or "",
            },
        )
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    form.save()
    return _render_ber_updated(request, affected=["brl-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def ber_delete(request, pk: int):
    get_object_or_404(BusinessEntityRecord, pk=pk).delete()
    return _render_ber_updated(request, affected=["bei-select", "ler-select", "bea-select", "brl-select"])


def _normalize_ber_positions():
    items = BusinessEntityRecord.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            BusinessEntityRecord.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def ber_move_up(request, pk: int):
    _normalize_ber_positions()
    items = list(BusinessEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        BusinessEntityRecord.objects.filter(pk=cur.id).update(position=prev.position)
        BusinessEntityRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_ber_positions()
    return _render_ber_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def ber_move_down(request, pk: int):
    _normalize_ber_positions()
    items = list(BusinessEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        BusinessEntityRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        BusinessEntityRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_ber_positions()
    return _render_ber_updated(request)


# ---------------------------------------------------------------------------
#  Реестр идентификаторов
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def bei_table_partial(request):
    return render(
        request,
        BEI_TABLE_TEMPLATE,
        _bei_context(request),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bei_form_create(request):
    if request.method == "GET":
        form = BusinessEntityIdentifierRecordForm()
        return render(request, BEI_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = BusinessEntityIdentifierRecordForm(request.POST)
    if not form.is_valid():
        resp = render(request, BEI_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_bei_position()
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    _ensure_identifier_has_unified_record(obj, request.user)
    _ensure_identifier_has_legal_address_record(obj, request.user)
    return _render_bei_updated(request, affected=["ler-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bei_form_edit(request, pk: int):
    item = get_object_or_404(BusinessEntityIdentifierRecord, pk=pk)
    if request.method == "GET":
        form = BusinessEntityIdentifierRecordForm(instance=item)
        return render(request, BEI_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
    form = BusinessEntityIdentifierRecordForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(request, BEI_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    _ensure_identifier_has_legal_address_record(obj, request.user)
    return _render_bei_updated(request, affected=["bea-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def bei_delete(request, pk: int):
    item = get_object_or_404(BusinessEntityIdentifierRecord, pk=pk)
    if item.business_entity.identifiers.exclude(pk=item.pk).count() == 0:
        return _validation_error(
            "Нельзя удалить последнюю запись из \"Реестр идентификаторов\": у каждой бизнес-сущности должен быть как минимум один идентификатор."
        )
    item.delete()
    return _render_bei_updated(request, affected=["ler-select", "bea-select"])


def _normalize_bei_positions():
    items = BusinessEntityIdentifierRecord.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            BusinessEntityIdentifierRecord.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def bei_move_up(request, pk: int):
    _normalize_bei_positions()
    items = list(BusinessEntityIdentifierRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        BusinessEntityIdentifierRecord.objects.filter(pk=cur.id).update(position=prev.position)
        BusinessEntityIdentifierRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_bei_positions()
    return _render_bei_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def bei_move_down(request, pk: int):
    _normalize_bei_positions()
    items = list(BusinessEntityIdentifierRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        BusinessEntityIdentifierRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        BusinessEntityIdentifierRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_bei_positions()
    return _render_bei_updated(request)


# ---------------------------------------------------------------------------
#  Реестр атрибутов
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def bat_table_partial(request):
    return render(
        request,
        BAT_TABLE_TEMPLATE,
        {"bat_items": _bat_display_items()},
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bat_form_create(request):
    if request.method == "GET":
        form = BusinessEntityAttributeRecordForm()
        return render(request, BAT_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = BusinessEntityAttributeRecordForm(request.POST)
    if not form.is_valid():
        resp = render(request, BAT_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_bat_position()
    obj.save()
    return _render_bat_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bat_form_edit(request, pk: int):
    item = get_object_or_404(BusinessEntityAttributeRecord, pk=pk)
    if request.method == "GET":
        form = BusinessEntityAttributeRecordForm(instance=item)
        return render(request, BAT_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
    form = BusinessEntityAttributeRecordForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(request, BAT_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    form.save()
    return _render_bat_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def bat_delete(request, pk: int):
    get_object_or_404(BusinessEntityAttributeRecord, pk=pk).delete()
    return _render_bat_updated(request)


def _normalize_bat_positions():
    items = BusinessEntityAttributeRecord.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            BusinessEntityAttributeRecord.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def bat_move_up(request, pk: int):
    _normalize_bat_positions()
    items = list(BusinessEntityAttributeRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        BusinessEntityAttributeRecord.objects.filter(pk=cur.id).update(position=prev.position)
        BusinessEntityAttributeRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_bat_positions()
    return _render_bat_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def bat_move_down(request, pk: int):
    _normalize_bat_positions()
    items = list(BusinessEntityAttributeRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        BusinessEntityAttributeRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        BusinessEntityAttributeRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_bat_positions()
    return _render_bat_updated(request)


# ---------------------------------------------------------------------------
#  Реестр юридических адресов
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def bea_table_partial(request):
    return render(
        request,
        BEA_TABLE_TEMPLATE,
        _bea_context(request),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bea_form_create(request):
    if request.method == "GET":
        form = BusinessEntityLegalAddressRecordForm()
        return render(request, BEA_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = BusinessEntityLegalAddressRecordForm(request.POST)
    if not form.is_valid():
        resp = render(request, BEA_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.attribute = LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS
    if not getattr(obj, "position", 0):
        obj.position = _next_bea_position()
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    return _render_bea_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def bea_form_edit(request, pk: int):
    item = get_object_or_404(LegalEntityRecord, pk=pk, attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS)
    if request.method == "GET":
        form = BusinessEntityLegalAddressRecordForm(instance=item)
        return render(request, BEA_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
    form = BusinessEntityLegalAddressRecordForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(request, BEA_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.attribute = LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    return _render_bea_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def bea_delete(request, pk: int):
    item = get_object_or_404(LegalEntityRecord, pk=pk, attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS)
    if item.identifier_record_id and LegalEntityRecord.objects.filter(
        identifier_record_id=item.identifier_record_id,
        attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
    ).exclude(pk=item.pk).count() == 0:
        return _validation_error(
            "Нельзя удалить последнюю запись из \"Реестр юридических адресов\": у каждого идентификатора должна быть как минимум одна запись с юридическим адресом."
        )
    item.delete()
    return _render_bea_updated(request)


def _normalize_bea_positions():
    _normalize_ler_positions()


@require_http_methods(["POST", "GET"])
@login_required
def bea_move_up(request, pk: int):
    _normalize_bea_positions()
    items = list(LegalEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LegalEntityRecord.objects.filter(pk=cur.id).update(position=prev.position)
        LegalEntityRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_bea_positions()
    return _render_bea_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def bea_move_down(request, pk: int):
    _normalize_bea_positions()
    items = list(LegalEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LegalEntityRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        LegalEntityRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_bea_positions()
    return _render_bea_updated(request)


# ---------------------------------------------------------------------------
#  Реестр реорганизаций
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def brl_table_partial(request):
    return render(
        request,
        BRL_TABLE_TEMPLATE,
        _brl_context(request),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
@transaction.atomic
def brl_form_create(request):
    if request.method == "GET":
        form = BusinessEntityRelationRecordForm()
        return render(request, BRL_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = BusinessEntityRelationRecordForm(request.POST)
    if not form.is_valid():
        resp = render(request, BRL_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    relation_type = form.cleaned_data.get("relation_type") or ""
    from_ids = form.cleaned_data.get("from_business_entity_ids") or []
    to_ids = _resolve_brl_to_ids(form, request.user)
    reorganization_event_uid = _next_reorganization_event_uid()
    event = BusinessEntityReorganizationEvent.objects.create(
        reorganization_event_uid=reorganization_event_uid,
        relation_type=relation_type,
        event_date=form.cleaned_data.get("event_date"),
        comment=form.cleaned_data.get("comment") or "",
        position=_next_bre_position(),
    )
    pairs = _build_brl_pairs(
        from_ids,
        to_ids,
    )
    position = _next_brl_position()
    for from_id, to_id in pairs:
        BusinessEntityRelationRecord.objects.create(
            event=event,
            from_business_entity_id=from_id,
            to_business_entity_id=to_id,
            position=position,
        )
        position += 1
    if relation_type == "Разделение":
        _close_latest_identifier_for_split(
            int(from_ids[0]) if from_ids else None,
            event.event_date,
        )
    return _render_brl_updated(request, affected=["ber-select", "bei-select", "ler-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
@transaction.atomic
def brl_form_edit(request, pk: int):
    item = get_object_or_404(BusinessEntityRelationRecord, pk=pk)
    if request.method == "GET":
        form = BusinessEntityRelationRecordForm(instance=item)
        return render(request, BRL_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
    form = BusinessEntityRelationRecordForm(request.POST, instance=item)
    if not form.is_valid():
        resp = render(request, BRL_FORM_TEMPLATE, {"form": form, "action": "edit", "item": item})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    relation_type = form.cleaned_data.get("relation_type") or ""
    from_ids = form.cleaned_data.get("from_business_entity_ids") or []
    to_ids = _resolve_brl_to_ids(form, request.user)
    event = item.event
    if event is None:
        event = BusinessEntityReorganizationEvent.objects.create(
            reorganization_event_uid=_next_reorganization_event_uid(),
            relation_type="",
            event_date=None,
            comment="",
            position=_next_bre_position(),
        )
        item.event = event
        item.save(update_fields=["event", "updated_at"])
    pairs = _build_brl_pairs(
        from_ids,
        to_ids,
    )
    event.relation_type = relation_type
    event.event_date = form.cleaned_data.get("event_date")
    event.comment = form.cleaned_data.get("comment") or ""
    event.save()

    existing_relations = list(
        BusinessEntityRelationRecord.objects.filter(event=event).order_by("position", "id")
    )
    next_position = _next_brl_position()
    for index, pair in enumerate(pairs):
        from_id, to_id = pair
        if index < len(existing_relations):
            relation = existing_relations[index]
            relation.from_business_entity_id = from_id
            relation.to_business_entity_id = to_id
            relation.save(update_fields=["from_business_entity", "to_business_entity", "updated_at"])
            next_position = max(next_position, relation.position + 1)
        else:
            BusinessEntityRelationRecord.objects.create(
                event=event,
                from_business_entity_id=from_id,
                to_business_entity_id=to_id,
                position=next_position,
            )
            next_position += 1

    for relation in existing_relations[len(pairs):]:
        relation.delete()

    if relation_type == "Разделение":
        _close_latest_identifier_for_split(
            int(from_ids[0]) if from_ids else None,
            event.event_date,
        )
    return _render_brl_updated(request, affected=["ber-select", "bei-select", "ler-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def brl_delete(request, pk: int):
    item = get_object_or_404(BusinessEntityRelationRecord, pk=pk)
    event = item.event
    item.delete()
    if event is not None and not event.relations.exists():
        event.delete()
    return _render_brl_updated(request)


def _normalize_brl_positions():
    items = BusinessEntityRelationRecord.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            BusinessEntityRelationRecord.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def brl_move_up(request, pk: int):
    _normalize_brl_positions()
    items = list(BusinessEntityRelationRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        BusinessEntityRelationRecord.objects.filter(pk=cur.id).update(position=prev.position)
        BusinessEntityRelationRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_brl_positions()
    return _render_brl_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def brl_move_down(request, pk: int):
    _normalize_brl_positions()
    items = list(BusinessEntityRelationRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        BusinessEntityRelationRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        BusinessEntityRelationRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_brl_positions()
    return _render_brl_updated(request)


# ---------------------------------------------------------------------------
#  Величина прожиточного минимума — partial для HTMX-фильтрации по дате
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def lw_table_partial(request):
    return render(request, LW_TABLE_TEMPLATE, _lw_context(request))


# ---------------------------------------------------------------------------
#  Величина прожиточного минимума CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def lw_form_create(request):
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = LivingWageForm()
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    form = LivingWageForm(request.POST)
    if not form.is_valid():
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "create", "today_iso": today_iso})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_lw_position()
    obj.save()
    return _render_lw_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def lw_form_edit(request, pk: int):
    item = get_object_or_404(LivingWage, pk=pk)
    today_iso = date_type.today().isoformat()
    if request.method == "GET":
        form = LivingWageForm(instance=item)
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "edit", "lw_item": item, "today_iso": today_iso})
    form = LivingWageForm(request.POST, instance=item)
    if not form.is_valid():
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "edit", "lw_item": item, "today_iso": today_iso})
    form.save()
    return _render_lw_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def lw_delete(request, pk: int):
    get_object_or_404(LivingWage, pk=pk).delete()
    return _render_lw_updated(request)


def _normalize_lw_positions():
    items = LivingWage.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            LivingWage.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def lw_move_up(request, pk: int):
    _normalize_lw_positions()
    items = list(LivingWage.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LivingWage.objects.filter(pk=cur.id).update(position=prev.position)
        LivingWage.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_lw_positions()
    return _render_lw_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def lw_move_down(request, pk: int):
    _normalize_lw_positions()
    items = list(LivingWage.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LivingWage.objects.filter(pk=cur.id).update(position=nxt.position)
        LivingWage.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_lw_positions()
    return _render_lw_updated(request)


# ---------------------------------------------------------------------------
#  ВПМ CSV upload
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_POST
def lw_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)

    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    data_rows = rows[1:]
    created_count = 0
    errors = []
    position = _next_lw_position()

    all_countries_by_code = {
        c.code.strip(): c for c in OKSMCountry.objects.all()
    }
    all_countries_by_name = {
        c.short_name.strip().lower(): c for c in OKSMCountry.objects.all()
    }

    from decimal import Decimal, InvalidOperation

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 6:
            errors.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается минимум 6).")
            continue

        try:
            country_code_raw = row[0].strip()
            country_name_raw = row[1].strip()
            region_name_raw = row[2].strip()
            region_code_raw = row[3].strip()
            amount_raw = row[4].strip()
            currency_raw = row[5].strip()
            approval_date = _parse_csv_date(row[6]) if len(row) > 6 else None
            expiry_date = _parse_csv_date(row[7]) if len(row) > 7 else None
            source = row[8].strip() if len(row) > 8 else ""

            country = None
            if country_code_raw:
                country = all_countries_by_code.get(country_code_raw)
            if not country and country_name_raw:
                country = all_countries_by_name.get(country_name_raw.lower())

            if not country:
                similar = [
                    c for cn, c in all_countries_by_name.items()
                    if country_name_raw.lower() in cn or cn in country_name_raw.lower()
                ]
                err = f'Строка {i}: страна "{country_name_raw}" (код "{country_code_raw}") не найдена в ОКСМ.'
                if similar:
                    err += f' Похожие: {"; ".join(s.short_name for s in similar[:5])}.'
                errors.append(err)
                continue

            if not region_name_raw and not region_code_raw:
                errors.append(f"Строка {i}: отсутствует название и код региона.")
                continue

            region = None
            if region_code_raw:
                region = TerritorialDivision.objects.filter(
                    country=country,
                    region_code__iexact=region_code_raw,
                ).first()
            if not region and region_name_raw:
                region = TerritorialDivision.objects.filter(
                    country=country,
                    region_name__iexact=region_name_raw,
                ).first()
            if not region:
                available = list(
                    TerritorialDivision.objects.filter(country=country)
                    .values_list("region_name", flat=True)
                    .order_by("region_name")[:10]
                )
                search = region_code_raw or region_name_raw
                err = f'Строка {i}: регион "{search}" не найден для страны "{country.short_name}".'
                if available:
                    err += f' Доступные регионы: {"; ".join(available)}.'
                errors.append(err)
                continue

            amount_str = amount_raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
            try:
                amount = Decimal(amount_str)
            except (InvalidOperation, ValueError):
                errors.append(f'Строка {i}: некорректное значение ВПМ "{amount_raw}".')
                continue

            if not approval_date:
                errors.append(f"Строка {i}: отсутствует или некорректна дата введения в действие.")
                continue

            LivingWage.objects.create(
                country=country,
                region=region,
                amount=amount,
                currency=currency_raw,
                approval_date=approval_date,
                expiry_date=expiry_date,
                source=source,
                position=position,
            )
            position += 1
            created_count += 1

        except Exception as exc:
            logger.exception("LW CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {"ok": True, "created": created_count}
    if errors:
        result["warnings"] = errors[:50]
    return JsonResponse(result)


# ---------------------------------------------------------------------------
#  LER (База юридических лиц) partial
# ---------------------------------------------------------------------------

def ler_table_partial(request):
    return render(request, LER_TABLE_TEMPLATE, _ler_context(request))


# ---------------------------------------------------------------------------
#  LER CRUD
# ---------------------------------------------------------------------------

def _ler_record_author(user):
    full = f"{user.first_name} {user.last_name}".strip() if user else ""
    return full if full else getattr(user, "email", "") or getattr(user, "username", "")


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ler_form_create(request):
    if request.method == "GET":
        form = LegalEntityRecordForm()
        return render(request, LER_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = LegalEntityRecordForm(request.POST)
    if not form.is_valid():
        resp = render(
            request,
            LER_FORM_TEMPLATE,
            {"form": form, "action": "create", "form_error_messages": _form_error_messages(form)},
        )
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.attribute = LegalEntityRecord.ATTRIBUTE_NAME
    if not getattr(obj, "position", 0):
        obj.position = _next_ler_position()
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    _ensure_name_record_has_identifier_chain(obj, request.user, business_entity_source=BUSINESS_ENTITY_SOURCE_LER)
    return _render_ler_updated(request, affected=["ber-select", "bei-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ler_form_edit(request, pk: int):
    record = get_object_or_404(LegalEntityRecord, pk=pk, attribute=LegalEntityRecord.ATTRIBUTE_NAME)
    if request.method == "GET":
        form = LegalEntityRecordForm(instance=record)
        return render(request, LER_FORM_TEMPLATE, {"form": form, "action": "edit", "record": record})
    form = LegalEntityRecordForm(request.POST, instance=record)
    if not form.is_valid():
        resp = render(
            request,
            LER_FORM_TEMPLATE,
            {
                "form": form,
                "action": "edit",
                "record": record,
                "form_error_messages": _form_error_messages(form),
            },
        )
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.attribute = LegalEntityRecord.ATTRIBUTE_NAME
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    _ensure_name_record_has_identifier_chain(obj, request.user, business_entity_source=BUSINESS_ENTITY_SOURCE_LER)
    return _render_ler_updated(request, affected=["ber-select", "bei-select", "bea-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def ler_delete(request, pk: int):
    item = get_object_or_404(LegalEntityRecord, pk=pk, attribute=LegalEntityRecord.ATTRIBUTE_NAME)
    if item.identifier_record_id and LegalEntityRecord.objects.filter(identifier_record_id=item.identifier_record_id).exclude(pk=item.pk).count() == 0:
        return _validation_error(
            "Нельзя удалить последнюю связанную запись: у каждого идентификатора должна быть как минимум одна запись в \"Реестр наименований/Реестр юридических адресов\"."
        )
    item.delete()
    return _render_ler_updated(request)


def _normalize_ler_positions():
    items = LegalEntityRecord.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            LegalEntityRecord.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def ler_move_up(request, pk: int):
    _normalize_ler_positions()
    items = list(LegalEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LegalEntityRecord.objects.filter(pk=cur.id).update(position=prev.position)
        LegalEntityRecord.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_ler_positions()
    return _render_ler_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def ler_move_down(request, pk: int):
    _normalize_ler_positions()
    items = list(LegalEntityRecord.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LegalEntityRecord.objects.filter(pk=cur.id).update(position=nxt.position)
        LegalEntityRecord.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_ler_positions()
    return _render_ler_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ler_csv_upload(request):
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
            return JsonResponse({"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."}, status=400)

    reader = csv.reader(io.StringIO(raw), delimiter=";")
    rows = list(reader)

    if not rows:
        return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
    if len(rows[0]) <= 1:
        reader = csv.reader(io.StringIO(raw), delimiter=",")
        rows = list(reader)
    if len(rows) < 2:
        return JsonResponse({"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."}, status=400)

    data_rows = rows[1:]
    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors = []
    conflicts = []
    position = _next_ler_position()

    countries_by_code = {c.code.strip(): c for c in OKSMCountry.objects.all()}
    countries_by_name = {c.short_name.strip().lower(): c for c in OKSMCountry.objects.all()}
    countries_by_alpha2 = {c.alpha2.strip().upper(): c for c in OKSMCountry.objects.all() if c.alpha2}
    countries_by_alpha3 = {c.alpha3.strip().upper(): c for c in OKSMCountry.objects.all() if c.alpha3}

    author = _ler_record_author(request.user)
    today = date_type.today()

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue

        if len(row) < 1 or not row[0].strip():
            errors.append(f"Строка {i}: отсутствует наименование (краткое).")
            continue

        try:
            short_name = row[0].strip()
            full_name = row[1].strip() if len(row) > 1 else ""
            country_raw = row[2].strip() if len(row) > 2 else ""
            has_region_column = len(row) > 10
            region_raw = row[3].strip() if has_region_column and len(row) > 3 else ""
            identifier_idx = 4 if has_region_column else 3
            registration_number_idx = 5 if has_region_column else 4
            registration_date_idx = 6 if has_region_column else 5
            record_date_idx = 7 if has_region_column else 6
            record_author_idx = 8 if has_region_column else 7
            name_received_date_idx = 9 if has_region_column else 8
            name_changed_date_idx = 10 if has_region_column else 9

            identifier = row[identifier_idx].strip() if len(row) > identifier_idx else ""
            registration_number = row[registration_number_idx].strip() if len(row) > registration_number_idx else ""
            effective_region = region_raw or detect_legal_entity_region_by_identifier(identifier, registration_number)
            registration_date = _parse_csv_date(row[registration_date_idx]) if len(row) > registration_date_idx else None
            record_date_csv = _parse_csv_date(row[record_date_idx]) if len(row) > record_date_idx else None
            record_author_csv = row[record_author_idx].strip() if len(row) > record_author_idx else ""
            name_received_date = _parse_csv_date(row[name_received_date_idx]) if len(row) > name_received_date_idx else None
            name_changed_date = _parse_csv_date(row[name_changed_date_idx]) if len(row) > name_changed_date_idx else None

            country = None
            if country_raw:
                country = countries_by_name.get(country_raw.lower())
                if not country:
                    country = countries_by_code.get(country_raw)
                if not country:
                    country = countries_by_alpha2.get(country_raw.upper())
                if not country:
                    country = countries_by_alpha3.get(country_raw.upper())
                if not country:
                    similar = [
                        c for cn, c in countries_by_name.items()
                        if country_raw.lower() in cn or cn in country_raw.lower()
                    ]
                    err = f'Строка {i}: страна "{country_raw}" не найдена в ОКСМ.'
                    if similar:
                        err += f' Похожие: {"; ".join(s.short_name for s in similar[:5])}.'
                    errors.append(err)
                    continue

            existing = LegalEntityRecord.objects.filter(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                short_name__iexact=short_name,
            ).first()
            if existing:
                changed_fields = []
                field_map = {
                    "full_name": ("Наименование (полное)", full_name, existing.full_name),
                    "registration_country": ("Страна регистрации", country, existing.registration_country),
                    "registration_region": ("Регион", effective_region, existing.registration_region),
                    "identifier": ("Идент.", identifier, existing.identifier),
                    "registration_number": ("Регистр. номер", registration_number, existing.registration_number),
                    "registration_date": ("Дата регистрации", registration_date, existing.registration_date),
                    "name_received_date": ("Дата получения наим.", name_received_date, existing.name_received_date),
                    "name_changed_date": ("Дата смены наим.", name_changed_date, existing.name_changed_date),
                }
                for field, (label, new_val, old_val) in field_map.items():
                    if field == "registration_country":
                        new_id = new_val.pk if new_val else None
                        old_id = old_val.pk if old_val else None
                        if new_id != old_id and new_val is not None:
                            old_display = old_val.short_name if old_val else "—"
                            new_display = new_val.short_name if new_val else "—"
                            changed_fields.append(f'{label}: «{old_display}» → «{new_display}»')
                            setattr(existing, field, new_val)
                    elif field in ("registration_date", "name_received_date", "name_changed_date"):
                        if new_val is not None and new_val != old_val:
                            old_d = old_val.strftime("%d.%m.%Y") if old_val else "—"
                            new_d = new_val.strftime("%d.%m.%Y")
                            changed_fields.append(f'{label}: «{old_d}» → «{new_d}»')
                            setattr(existing, field, new_val)
                    else:
                        if new_val and new_val != (old_val or ""):
                            changed_fields.append(f'{label}: «{old_val or "—"}» → «{new_val}»')
                            setattr(existing, field, new_val)

                if changed_fields:
                    existing.record_date = record_date_csv or today
                    existing.record_author = record_author_csv or author
                    existing.save()
                    _ensure_name_record_has_identifier_chain(existing, request.user)
                    conflicts.append(
                        f'Строка {i}: «{short_name}» — обновлено: {"; ".join(changed_fields)}.'
                    )
                    updated_count += 1
                else:
                    skipped_count += 1
                    conflicts.append(
                        f'Строка {i}: «{short_name}» — дубликат без изменений, пропущено.'
                    )
                continue

            created = LegalEntityRecord.objects.create(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                short_name=short_name,
                full_name=full_name,
                registration_country=country,
                registration_region=effective_region,
                identifier=identifier,
                registration_number=registration_number,
                registration_date=registration_date,
                record_date=record_date_csv or today,
                record_author=record_author_csv or author,
                name_received_date=name_received_date,
                name_changed_date=name_changed_date,
                position=position,
            )
            _ensure_name_record_has_identifier_chain(created, request.user)
            position += 1
            created_count += 1

        except Exception as exc:
            logger.exception("LER CSV import row %d failed", i)
            errors.append(f"Строка {i}: {exc}")

    result = {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }
    if conflicts:
        result["conflicts"] = conflicts
    if errors:
        result["warnings"] = errors[:50]
    return JsonResponse(result)
