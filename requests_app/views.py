import csv
import io

from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Max

from policy_app.models import Product, TypicalSection
from .models import RequestTable, RequestItem
from .forms import RequestForm
from django.urls import reverse
from django.db import transaction


def _hx(request):
    return request.headers.get("HX-Request") == "true"

def _resolve_product_section(request):
    product_short = (request.GET.get("product") or "").strip().upper()
    section_id = (request.GET.get("section") or "").strip()

    product = Product.objects.filter(short_name__iexact=product_short).first()
    if not product:
        return None, None

    section = None
    if section_id:
        section = TypicalSection.objects.filter(id=section_id, product=product).first()
    if not section:
        section = product.sections.order_by("position", "id").first()  # дефолт: 1-й раздел

    return product, section

def _get_bindings(request):
    prod_short = (request.GET.get("product") or "").strip().upper()
    section_id = request.GET.get("section")
    product = Product.objects.filter(short_name__iexact=prod_short).first()
    section = TypicalSection.objects.filter(id=section_id).first() if section_id else None
    return product, section


def _render_table_for(table):
    return render(
        None,
        "requests_app/requests_table.html",
        {
            "product": table.product,
            "section": table.section,
            "table": table.__class__.objects.filter(pk=table.pk).prefetch_related("items").first(),
        },
    )


def _render_response(request, table):
    """Return either the all-sections or single-section table depending on query params."""
    section_raw = (request.GET.get("section") or request.POST.get("section") or "").strip()
    if section_raw == "all":
        prod_short = (request.GET.get("product") or request.POST.get("product") or "").strip().upper()
        product = Product.objects.filter(short_name__iexact=prod_short).first() or table.product
        all_items = (
            RequestItem.objects
            .filter(table__product=product)
            .select_related("table__section")
            .order_by("table__section__position", "position", "id")
        )
        return render(request, "requests_app/requests_table.html", {
            "product": product, "all_items": all_items, "all_sections": True,
        })
    table = RequestTable.objects.filter(pk=table.pk).prefetch_related("items").first()
    return render(request, "requests_app/requests_table.html", {
        "product": table.product, "section": table.section, "table": table,
    })


def requests_partial(request):
    section_id_raw = (request.GET.get("section") or "").strip()
    all_sections = section_id_raw == "" or section_id_raw == "all"

    prod_short = (request.GET.get("product") or "").strip().upper()
    product = Product.objects.filter(short_name__iexact=prod_short).first()

    table = None
    section = None
    all_items = None

    if product and all_sections:
        all_items = (
            RequestItem.objects
            .filter(table__product=product)
            .select_related("table__section")
            .order_by("table__section__position", "position", "id")
        )
    elif product and section_id_raw.isdigit():
        section = TypicalSection.objects.filter(id=section_id_raw).first()
        if section:
            table = RequestTable.objects.filter(product=product, section=section).prefetch_related("items").first()

    return render(request, "requests_app/requests_table.html", {
        "product": product,
        "section": section,
        "table": table,
        "all_items": all_items,
        "all_sections": all_sections,
    })


@require_http_methods(["GET", "POST"])
def request_form_create(request):
    section_id_raw = (request.GET.get("section") or "").strip()
    all_mode = section_id_raw == "all"

    prod_short = (request.GET.get("product") or "").strip().upper()
    product = Product.objects.filter(short_name__iexact=prod_short).first()
    if not product:
        return HttpResponseBadRequest("Не удалось определить продукт.")

    section = None
    if not all_mode and section_id_raw.isdigit():
        section = TypicalSection.objects.filter(id=section_id_raw).first()

    sections_choices = None
    if all_mode:
        sections_choices = TypicalSection.objects.filter(
            product=product
        ).order_by("position", "id")

    form_action = (
        f"{reverse('request_form_create')}?product={product.short_name.upper()}"
        f"&section={'all' if all_mode else (section.id if section else '')}"
    )

    if request.method == "POST":
        form = RequestForm(request.POST)

        if all_mode:
            sec_id = request.POST.get("section_id", "").strip()
            if sec_id.isdigit():
                section = TypicalSection.objects.filter(id=sec_id, product=product).first()
            if not section:
                form.add_error(None, "Выберите раздел.")

        if form.is_valid() and section:
            table, _ = RequestTable.objects.get_or_create(product=product, section=section)
            code_initial = getattr(section, "code", "")
            item = form.save(commit=False)
            item.table = table
            item.code = code_initial or item.code
            last = RequestItem.objects.filter(table=table).aggregate(m=Max("position"))["m"] or 0
            item.position = last + 1
            item.save()

            if all_mode:
                all_items = (
                    RequestItem.objects
                    .filter(table__product=product)
                    .select_related("table__section")
                    .order_by("table__section__position", "position", "id")
                )
                resp = render(request, "requests_app/requests_table.html",
                              {"product": product, "all_items": all_items, "all_sections": True})
            else:
                table = RequestTable.objects.filter(pk=table.pk).prefetch_related("items").first()
                resp = render(request, "requests_app/requests_table.html",
                              {"product": product, "section": section, "table": table})
            resp["HX-Trigger"] = "requests:saved"
            return resp

        selected_section_id = None
        if all_mode:
            raw = (request.POST.get("section_id") or "").strip()
            selected_section_id = int(raw) if raw.isdigit() else None
        resp = render(request, "requests_app/request_form_modal.html", {
            "title": "Добавить запрос",
            "submit_label": "Сохранить",
            "form_action": form_action,
            "form": form, "product": product, "section": section,
            "sections_choices": sections_choices,
            "selected_section_id": selected_section_id,
        })
        resp["HX-Retarget"] = "#requests-modal .modal-content"
        resp.status_code = 422
        return resp

    code_initial = getattr(section, "code", "") if section else ""
    form = RequestForm(initial={"code": code_initial})
    if not all_mode:
        form.fields["code"].widget.attrs["readonly"] = "readonly"

    return render(request, "requests_app/request_form_modal.html", {
        "title": "Добавить запрос",
        "submit_label": "Сохранить",
        "form_action": form_action,
        "form": form, "product": product, "section": section,
        "sections_choices": sections_choices,
    })


@require_http_methods(["GET", "POST"])
def request_form_edit(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table__product", "table__section"), pk=pk)
    table = item.table
    product, section = table.product, table.section

    section_raw = (request.GET.get("section") or "").strip()
    all_mode = section_raw == "all"
    qs = f"?section=all&product={product.short_name.upper()}" if all_mode else ""
    form_action = reverse('request_form_edit', args=[item.pk]) + qs

    if request.method == "POST":
        form = RequestForm(request.POST, instance=item)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.code = getattr(section, "code", obj.code)
            obj.save()
            resp = _render_response(request, table)
            resp["HX-Trigger"] = "requests:saved"
            return resp

        resp = render(request, "requests_app/request_form_modal.html", {
            "title": "Изменить запрос",
            "submit_label": "Сохранить",
            "form_action": form_action,
            "form": form, "product": product, "section": section,
        })
        resp["HX-Retarget"] = "#requests-modal .modal-content"
        resp.status_code = 422
        return resp

    form = RequestForm(instance=item)
    form.fields["code"].widget.attrs["readonly"] = "readonly"
    return render(request, "requests_app/request_form_modal.html", {
        "title": "Изменить запрос",
        "submit_label": "Сохранить",
        "form_action": form_action,
        "form": form, "product": product, "section": section,
    })

@require_http_methods(["POST"])
def request_delete(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table__product", "table__section"), pk=pk)
    table = item.table
    item.delete()
    return _render_response(request, table)


def _swap_positions(a: RequestItem, b: RequestItem):
    a.position, b.position = b.position, a.position
    a.save(update_fields=["position"])
    b.save(update_fields=["position"])


@require_http_methods(["POST"])
def request_move_up(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table"), pk=pk)
    prev = (
        RequestItem.objects.filter(table=item.table, position__lt=item.position)
        .order_by("-position")
        .first()
    )
    if prev:
        with transaction.atomic():
            _swap_positions(item, prev)
    return _render_response(request, item.table)


@require_http_methods(["POST"])
def request_move_down(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table"), pk=pk)
    nxt = (
        RequestItem.objects.filter(table=item.table, position__gt=item.position)
        .order_by("position")
        .first()
    )
    if nxt:
        with transaction.atomic():
            _swap_positions(item, nxt)
    return _render_response(request, item.table)


@require_POST
def request_csv_upload(request):
    prod_short = (request.GET.get("product") or "").strip().upper()
    section_id_raw = (request.GET.get("section") or "").strip()

    product = Product.objects.filter(short_name__iexact=prod_short).first()
    if not product:
        return JsonResponse({"ok": False, "error": "Продукт не найден."})

    all_mode = section_id_raw == "all"
    fixed_section = None
    if not all_mode:
        if section_id_raw.isdigit():
            fixed_section = TypicalSection.objects.filter(id=section_id_raw).first()
        if not fixed_section:
            return JsonResponse({"ok": False, "error": "Раздел не определён."})

    f = request.FILES.get("csv_file")
    if not f:
        return JsonResponse({"ok": False, "error": "Файл не выбран."})

    try:
        raw = f.read()
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            return JsonResponse({"ok": False, "error": "Не удалось определить кодировку файла."})

        first_line = text.split("\n", 1)[0]
        delimiter = ";" if ";" in first_line else ","
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)

        header = next(reader, None)
        if not header or len(header) < 4:
            return JsonResponse({"ok": False, "error": "CSV должен содержать минимум 4 столбца."})

        if all_mode:
            sections_by_code = {
                s.code.strip().upper(): s
                for s in TypicalSection.objects.filter(product=product)
            }

        table_last_pos = {}

        created = 0
        warnings = []
        for row_num, row in enumerate(reader, start=2):
            if not row or all(c.strip() == "" for c in row):
                continue
            if len(row) < 4:
                warnings.append(f"Строка {row_num}: пропущена — менее 4 столбцов.")
                continue

            code = row[0].strip()
            num_str = row[1].strip()
            short_name = row[2].strip()
            name = row[3].strip()

            if not code and not num_str and not name:
                continue

            if all_mode:
                section = sections_by_code.get(code.upper())
                if not section:
                    available = ", ".join(sorted(sections_by_code.keys())) or "(нет разделов)"
                    warnings.append(
                        f"Строка {row_num}: код '{code}' не найден в типовых разделах "
                        f"продукта {product.short_name}. Доступные коды: {available}"
                    )
                    continue
            else:
                section = fixed_section

            number = None
            if num_str:
                try:
                    number = int(num_str)
                except ValueError:
                    warnings.append(f"Строка {row_num}: невалидное значение №: '{num_str}'.")
                    continue

            table, _ = RequestTable.objects.get_or_create(product=product, section=section)
            tbl_pk = table.pk
            if tbl_pk not in table_last_pos:
                table_last_pos[tbl_pk] = (
                    RequestItem.objects.filter(table=table).aggregate(m=Max("position"))["m"] or 0
                )
            table_last_pos[tbl_pk] += 1

            RequestItem.objects.create(
                table=table,
                code=code or getattr(section, "code", ""),
                number=number if number is not None else 0,
                short_name=short_name,
                name=name,
                position=table_last_pos[tbl_pk],
            )
            created += 1

        return JsonResponse({"ok": True, "created": created, "warnings": warnings})

    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)})