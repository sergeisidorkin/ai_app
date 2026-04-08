import json
from datetime import date as date_type
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import PersonRecordForm, PositionRecordForm
from .models import PersonRecord, PositionRecord

PRS_TABLE_TEMPLATE = "contacts_app/prs_table_partial.html"
PRS_FORM_TEMPLATE = "contacts_app/prs_form.html"
PSN_TABLE_TEMPLATE = "contacts_app/psn_table_partial.html"
PSN_FORM_TEMPLATE = "contacts_app/psn_form.html"
CONTACTS_PAGE_SIZE = 50
PRS_TABLE_URL = "/contacts/prs/table/"
PSN_TABLE_URL = "/contacts/psn/table/"
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
    keys = ("prs_page", "psn_page")
    data = {}
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


def _validation_error(message: str, status: int = 409):
    return HttpResponse(message, status=status, content_type="text/plain; charset=utf-8")


def _next_prs_position():
    return (PersonRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _next_psn_position():
    return (PositionRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


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


def _prs_context(request):
    queryset = PersonRecord.objects.select_related("citizenship").order_by("position", "id")
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
    return _paginate_queryset(
        request,
        queryset,
        item_key="psn_items",
        page_param="psn_page",
        partial_url=PSN_TABLE_URL,
        target="#contacts-positions-table-wrap",
    )


def _render_prs_updated(request, *, affected=None):
    response = render(request, PRS_TABLE_TEMPLATE, _prs_context(request))
    return _set_contacts_trigger(response, source="prs-select", affected=affected)


def _render_psn_updated(request, *, affected=None):
    response = render(request, PSN_TABLE_TEMPLATE, _psn_context(request))
    return _set_contacts_trigger(response, source="psn-select", affected=affected)


def _refresh_person_position_sources(person: PersonRecord):
    for item in person.positions.all():
        new_source = item.resolve_source()
        if item.source != new_source:
            PositionRecord.objects.filter(pk=item.pk).update(source=new_source)


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
    return _render_prs_updated(request, affected=["psn-select"])


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
    return _render_prs_updated(request, affected=["psn-select"])


@login_required
@user_passes_test(staff_required)
@require_POST
def prs_delete(request, pk: int):
    get_object_or_404(PersonRecord, pk=pk).delete()
    return _render_prs_updated(request, affected=["psn-select"])


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
@require_http_methods(["GET", "POST"])
def psn_form_create(request):
    if request.method == "GET":
        return render(
            request,
            PSN_FORM_TEMPLATE,
            {
                "form": PositionRecordForm(),
                "action": "create",
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
