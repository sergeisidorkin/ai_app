import csv
import io
import json
import logging
from datetime import date as date_type

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Max, Q
from django.http import JsonResponse

logger = logging.getLogger(__name__)

from .models import OKSMCountry, OKVCurrency, LegalEntityIdentifier, TerritorialDivision, LivingWage, LegalEntityRecord
from .forms import OKSMCountryForm, OKVCurrencyForm, LegalEntityIdentifierForm, TerritorialDivisionForm, LivingWageForm, LegalEntityRecordForm

PARTIAL_TEMPLATE = "classifiers_app/classifiers_partial.html"
OKSM_TABLE_TEMPLATE = "classifiers_app/oksm_table_partial.html"
OKSM_FORM_TEMPLATE = "classifiers_app/oksm_form.html"
KATD_TABLE_TEMPLATE = "classifiers_app/katd_table_partial.html"
KATD_FORM_TEMPLATE = "classifiers_app/katd_form.html"
OKV_TABLE_TEMPLATE = "classifiers_app/okv_table_partial.html"
OKV_FORM_TEMPLATE = "classifiers_app/okv_form.html"
LEI_TABLE_TEMPLATE = "classifiers_app/lei_table_partial.html"
LEI_FORM_TEMPLATE = "classifiers_app/lei_form.html"
LW_TABLE_TEMPLATE = "classifiers_app/lw_table_partial.html"
LW_FORM_TEMPLATE = "classifiers_app/lw_form.html"
LER_TABLE_TEMPLATE = "classifiers_app/ler_table_partial.html"
LER_FORM_TEMPLATE = "classifiers_app/ler_form.html"
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

def _get_ler_queryset(as_of: date_type | None = None):
    qs = LegalEntityRecord.objects.select_related("registration_country")
    if as_of is None:
        return qs
    return qs.filter(
        Q(name_received_date__lte=as_of),
    ).filter(
        Q(name_changed_date__isnull=True) | Q(name_changed_date__gt=as_of),
    )


def _ler_context(request):
    date_filter = _parse_date(_req_param(request, "ler_date"))
    if date_filter is None and not _has_param(request, "ler_date"):
        date_filter = date_type.today()
    return {
        "ler_items": _get_ler_queryset(date_filter).order_by("position", "id"),
        "ler_date_filter": date_filter.isoformat() if date_filter else "",
    }


# ---------------------------------------------------------------------------
#  Common context / render helpers
# ---------------------------------------------------------------------------

def _classifiers_context(request):
    ctx = {}
    ctx.update(_oksm_context(request))
    ctx.update(_okv_context(request))
    ctx.update(_lei_context(request))
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


def _next_lei_position():
    last = LegalEntityIdentifier.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _next_katd_position():
    last = TerritorialDivision.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_lw_updated(request):
    response = render(request, LW_TABLE_TEMPLATE, _lw_context(request))
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_ler_position():
    last = LegalEntityRecord.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _render_ler_updated(request):
    response = render(request, LER_TABLE_TEMPLATE, _ler_context(request))
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
    """Search LegalEntityRecord by partial short_name / full_name / registration_number match."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 1:
        return JsonResponse({"results": [], "total_count": 0})
    today = date_type.today()
    qs = (
        _get_ler_queryset(today)
        .filter(
            Q(short_name__icontains=q)
            | Q(full_name__icontains=q)
            | Q(registration_number__icontains=q)
        )
        .order_by("short_name")
    )
    total_count = qs.count()
    data = []
    for r in qs[:15]:
        data.append({
            "id": r.id,
            "short_name": r.short_name,
            "full_name": r.full_name or "",
            "identifier": r.identifier or "",
            "registration_number": r.registration_number or "",
            "country_id": r.registration_country_id or "",
            "country_name": r.registration_country.short_name if r.registration_country else "",
            "registration_date": r.registration_date.isoformat() if r.registration_date else "",
        })
    return JsonResponse({"results": data, "total_count": total_count})


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
    full = f"{user.first_name} {user.last_name}".strip()
    return full if full else user.email or user.username


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ler_form_create(request):
    if request.method == "GET":
        form = LegalEntityRecordForm()
        return render(request, LER_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = LegalEntityRecordForm(request.POST)
    if not form.is_valid():
        resp = render(request, LER_FORM_TEMPLATE, {"form": form, "action": "create"})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_ler_position()
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    return _render_ler_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ler_form_edit(request, pk: int):
    record = get_object_or_404(LegalEntityRecord, pk=pk)
    if request.method == "GET":
        form = LegalEntityRecordForm(instance=record)
        return render(request, LER_FORM_TEMPLATE, {"form": form, "action": "edit", "record": record})
    form = LegalEntityRecordForm(request.POST, instance=record)
    if not form.is_valid():
        resp = render(request, LER_FORM_TEMPLATE, {"form": form, "action": "edit", "record": record})
        resp["HX-Retarget"] = "#classifiers-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.record_date = date_type.today()
    obj.record_author = _ler_record_author(request.user)
    obj.save()
    return _render_ler_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ler_delete(request, pk: int):
    get_object_or_404(LegalEntityRecord, pk=pk).delete()
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
            identifier = row[3].strip() if len(row) > 3 else ""
            registration_number = row[4].strip() if len(row) > 4 else ""
            registration_date = _parse_csv_date(row[5]) if len(row) > 5 else None
            record_date_csv = _parse_csv_date(row[6]) if len(row) > 6 else None
            record_author_csv = row[7].strip() if len(row) > 7 else ""
            name_received_date = _parse_csv_date(row[8]) if len(row) > 8 else None
            name_changed_date = _parse_csv_date(row[9]) if len(row) > 9 else None

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

            existing = LegalEntityRecord.objects.filter(short_name__iexact=short_name).first()
            if existing:
                changed_fields = []
                field_map = {
                    "full_name": ("Наименование (полное)", full_name, existing.full_name),
                    "registration_country": ("Страна регистрации", country, existing.registration_country),
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

            LegalEntityRecord.objects.create(
                short_name=short_name,
                full_name=full_name,
                registration_country=country,
                identifier=identifier,
                registration_number=registration_number,
                registration_date=registration_date,
                record_date=record_date_csv or today,
                record_author=record_author_csv or author,
                name_received_date=name_received_date,
                name_changed_date=name_changed_date,
                position=position,
            )
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
