from datetime import date as date_type

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Max, Q

from .models import OKSMCountry, OKVCurrency, TerritorialDivision, LivingWage
from .forms import OKSMCountryForm, OKVCurrencyForm, TerritorialDivisionForm, LivingWageForm

PARTIAL_TEMPLATE = "classifiers_app/classifiers_partial.html"
OKSM_TABLE_TEMPLATE = "classifiers_app/oksm_table_partial.html"
OKSM_FORM_TEMPLATE = "classifiers_app/oksm_form.html"
KATD_TABLE_TEMPLATE = "classifiers_app/katd_table_partial.html"
KATD_FORM_TEMPLATE = "classifiers_app/katd_form.html"
OKV_TABLE_TEMPLATE = "classifiers_app/okv_table_partial.html"
OKV_FORM_TEMPLATE = "classifiers_app/okv_form.html"
LW_TABLE_TEMPLATE = "classifiers_app/lw_table_partial.html"
LW_FORM_TEMPLATE = "classifiers_app/lw_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "classifiers-updated"


def staff_required(user):
    return user.is_authenticated and user.is_staff


# ---------------------------------------------------------------------------
#  Common date helpers
# ---------------------------------------------------------------------------

def _parse_date(raw: str | None) -> date_type | None:
    if not raw:
        return None
    try:
        return date_type.fromisoformat(raw)
    except (ValueError, TypeError):
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
#  Common context / render helpers
# ---------------------------------------------------------------------------

def _classifiers_context(request):
    ctx = {}
    ctx.update(_oksm_context(request))
    ctx.update(_okv_context(request))
    ctx.update(_katd_context(request))
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


def _next_oksm_position():
    last = OKSMCountry.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_okv_position():
    last = OKVCurrency.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_katd_position():
    last = TerritorialDivision.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_lw_updated(request):
    response = render(request, LW_TABLE_TEMPLATE, _lw_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


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
#  ОКВ CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def okv_form_create(request):
    if request.method == "GET":
        form = OKVCurrencyForm()
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = OKVCurrencyForm(request.POST)
    if not form.is_valid():
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "create"})
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
    if request.method == "GET":
        form = OKVCurrencyForm(instance=currency)
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "edit", "currency": currency})
    form = OKVCurrencyForm(request.POST, instance=currency)
    if not form.is_valid():
        return render(request, OKV_FORM_TEMPLATE, {"form": form, "action": "edit", "currency": currency})
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
    if request.method == "GET":
        form = TerritorialDivisionForm()
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = TerritorialDivisionForm(request.POST)
    if not form.is_valid():
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "create"})
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
    if request.method == "GET":
        form = TerritorialDivisionForm(instance=division)
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "edit", "division": division})
    form = TerritorialDivisionForm(request.POST, instance=division)
    if not form.is_valid():
        return render(request, KATD_FORM_TEMPLATE, {"form": form, "action": "edit", "division": division})
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
#  Величина прожиточного минимума — AJAX endpoint for dependent region dropdown
# ---------------------------------------------------------------------------

from django.http import JsonResponse


@login_required
@require_http_methods(["GET"])
def lw_regions_for_country(request):
    country_code = request.GET.get("country_code")
    if not country_code:
        return JsonResponse([], safe=False)
    today = date_type.today()
    divisions = TerritorialDivision.objects.filter(
        country__code=country_code,
        effective_date__lte=today,
    ).filter(
        Q(abolished_date__isnull=True) | Q(abolished_date__gte=today),
    ).order_by("region_name")
    data = [{"id": d.pk, "name": d.region_name} for d in divisions]
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
    if request.method == "GET":
        form = LivingWageForm()
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = LivingWageForm(request.POST)
    if not form.is_valid():
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_lw_position()
    obj.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def lw_form_edit(request, pk: int):
    item = get_object_or_404(LivingWage, pk=pk)
    if request.method == "GET":
        form = LivingWageForm(instance=item)
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "edit", "lw_item": item})
    form = LivingWageForm(request.POST, instance=item)
    if not form.is_valid():
        return render(request, LW_FORM_TEMPLATE, {"form": form, "action": "edit", "lw_item": item})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def lw_delete(request, pk: int):
    get_object_or_404(LivingWage, pk=pk).delete()
    return _render_updated(request)


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
    return _render_updated(request)


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
    return _render_updated(request)
