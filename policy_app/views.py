import csv
import io
import json
from collections import defaultdict

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from experts_app.models import ExpertSpecialty
from group_app.models import OrgUnit
from .models import (
    Product,
    TypicalSection,
    TypicalSectionSpecialty,
    SectionStructure,
    ServiceGoalReport,
    TypicalServiceComposition,
    ExpertiseDirection,
    Grade,
    SpecialtyTariff,
    Tariff,
    MANAGER_GROUPS,
)
from .forms import (
    ProductForm,
    TypicalSectionForm,
    SectionStructureForm,
    ServiceGoalReportForm,
    TypicalServiceCompositionForm,
    ExpertiseDirectionForm,
    GradeForm,
    SpecialtyTariffForm,
    TariffForm,
)

# Вынесенные константы для единообразия шаблонов/заголовков
POLICY_PARTIAL_TEMPLATE = "policy_app/policy_partial.html"
PRODUCT_FORM_TEMPLATE = "policy_app/product_form.html"
SECTION_FORM_TEMPLATE = "policy_app/section_form.html"
STRUCTURE_FORM_TEMPLATE = "policy_app/structure_form.html"
SERVICE_GOAL_REPORT_FORM_TEMPLATE = "policy_app/service_goal_report_form.html"
TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE = "policy_app/typical_service_composition_form.html"
EXPERTISE_DIR_FORM_TEMPLATE = "policy_app/expertise_direction_form.html"
GRADE_FORM_TEMPLATE = "policy_app/grade_form.html"
SPECIALTY_TARIFF_FORM_TEMPLATE = "policy_app/specialty_tariff_form.html"
TARIFF_FORM_TEMPLATE = "policy_app/tariff_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_POLICY_UPDATED_EVENT = "policy-updated"


def _render_form_with_errors(request, template, context):
    response = render(request, template, context)
    response["HX-Retarget"] = "#policy-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


def _is_department_head(user):
    return user.groups.filter(name__in=MANAGER_GROUPS).exists()


def _get_grades_for_user(user):
    qs = Grade.objects.select_related("created_by", "created_by__employee_profile", "currency")
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs


def _get_tariffs_for_user(user):
    qs = Tariff.objects.select_related(
        "product", "section", "created_by", "created_by__employee_profile"
    )
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs


def _get_specialty_tariffs_for_user(user):
    qs = SpecialtyTariff.objects.select_related(
        "currency", "created_by", "created_by__employee_profile"
    ).prefetch_related("specialties")
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs

def staff_required(user):
    return user.is_authenticated and user.is_staff

# Вспомогательные функции для устранения дублирования
def _policy_context(request):
    products = Product.objects.prefetch_related("owners").all()
    sections = TypicalSection.objects.select_related("product", "expertise_dir", "expertise_direction").prefetch_related(
        "ranked_specialties", "ranked_specialties__specialty"
    ).all()
    structures = SectionStructure.objects.select_related("product", "section").all()
    service_goal_reports = ServiceGoalReport.objects.select_related("product").all()
    typical_service_compositions = TypicalServiceComposition.objects.select_related("product", "section").all()
    expertise_directions = ExpertiseDirection.objects.prefetch_related("owners").all()
    grades = _get_grades_for_user(request.user)
    specialty_tariffs = _get_specialty_tariffs_for_user(request.user)
    tariffs = _get_tariffs_for_user(request.user)
    is_dept_head = _is_department_head(request.user)
    return {
        "products": products,
        "sections": sections,
        "structures": structures,
        "service_goal_reports": service_goal_reports,
        "typical_service_compositions": typical_service_compositions,
        "expertise_directions": expertise_directions,
        "grades": grades,
        "specialty_tariffs": specialty_tariffs,
        "tariffs": tariffs,
        "is_admin": request.user.is_superuser,
        "is_dept_head": is_dept_head,
    }

def _render_policy_updated(request):
    response = render(request, POLICY_PARTIAL_TEMPLATE, _policy_context(request))
    response[HX_TRIGGER_HEADER] = HX_POLICY_UPDATED_EVENT
    return response

def _next_position(model, filters: dict | None = None) -> int:
    """
    Возвращает следующую позицию (last+1) для списка объектов.
    filters — при необходимости ограничивает область (например, внутри продукта).
    """
    qs = model.objects
    if filters:
        qs = qs.filter(**filters)
    last = qs.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1

@login_required
@require_http_methods(["GET"])
def policy_partial(request):
    return render(request, POLICY_PARTIAL_TEMPLATE, _policy_context(request))

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def product_form_create(request):
    if request.method == "GET":
        form = ProductForm()
        return render(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "create"})
    # POST
    form = ProductForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "create"})
    if not form.instance.position:
        form.instance.position = _next_position(Product)
    form.save()
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def product_form_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "GET":
        form = ProductForm(instance=product)
        return render(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "edit", "product": product})
    # POST
    form = ProductForm(request.POST, instance=product)
    if not form.is_valid():
        return _render_form_with_errors(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "edit", "product": product})
    form.save()
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    return _render_policy_updated(request)

# --- Типовые разделы ---

def _section_specialty_options():
    return [
        {"id": s.pk, "label": s.specialty}
        for s in ExpertSpecialty.objects.exclude(specialty="").order_by("position")
    ]


def _section_form_context(form, action, section=None):
    spec_options = _section_specialty_options()
    ranked = []
    if section and section.pk:
        ranked = [
            {"rank": link.rank, "specialty_id": link.specialty_id}
            for link in TypicalSectionSpecialty.objects.filter(section=section).order_by("rank")
        ]
    ctx = {
        "form": form,
        "action": action,
        "specialty_options": spec_options,
        "specialty_options_json": json.dumps(spec_options, ensure_ascii=False),
        "ranked_specialties": ranked,
    }
    if section:
        ctx["section"] = section
    return ctx


def _save_section_specialties(section, post_data):
    specialty_ids = post_data.getlist("specialty_id")
    TypicalSectionSpecialty.objects.filter(section=section).delete()
    to_create = []
    for rank, raw_id in enumerate(specialty_ids, start=1):
        if raw_id:
            try:
                sid = int(raw_id)
            except (ValueError, TypeError):
                continue
            to_create.append(TypicalSectionSpecialty(
                section=section, specialty_id=sid, rank=rank,
            ))
    if to_create:
        TypicalSectionSpecialty.objects.bulk_create(to_create)


def _typical_sections_by_product_json():
    data = defaultdict(list)
    sections = TypicalSection.objects.select_related("product").order_by("product_id", "position", "id")
    for section in sections:
        data[str(section.product_id)].append({
            "id": section.pk,
            "label": section.name_ru,
        })
    return json.dumps(data, ensure_ascii=False)


def _typical_service_composition_form_context(form, action, composition=None):
    ctx = {
        "form": form,
        "action": action,
        "sections_by_product_json": _typical_sections_by_product_json(),
    }
    if composition:
        ctx["composition"] = composition
    return ctx


def _specialty_tariff_specialty_options():
    return [
        {
            "id": specialty.pk,
            "label": specialty.specialty,
            "expertise_direction": (
                ""
                if (getattr(specialty.expertise_dir, "short_name", "") or "").strip() == "—"
                else (getattr(specialty.expertise_dir, "short_name", "") or "").strip()
            ),
        }
        for specialty in ExpertSpecialty.objects.exclude(specialty="").select_related("expertise_dir").order_by("position", "id")
    ]


def _specialty_tariff_form_context(form, action, tariff=None):
    selected_specialty_ids = []
    if form.is_bound:
        selected_specialty_ids = [str(value) for value in form.data.getlist("specialties") if value]
    elif tariff and tariff.pk:
        selected_specialty_ids = [str(value) for value in tariff.specialties.values_list("pk", flat=True)]

    ctx = {
        "form": form,
        "action": action,
        "specialty_options": _specialty_tariff_specialty_options(),
        "specialty_options_json": json.dumps(_specialty_tariff_specialty_options(), ensure_ascii=False),
        "selected_specialty_ids_json": json.dumps(selected_specialty_ids, ensure_ascii=False),
    }
    if tariff:
        ctx["tariff"] = tariff
    return ctx


def _specialty_tariff_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_create(request):
    if request.method == "GET":
        form = TypicalSectionForm()
        return render(request, SECTION_FORM_TEMPLATE, _section_form_context(form, "create"))
    form = TypicalSectionForm(request.POST)
    if not form.is_valid():
        return render(request, SECTION_FORM_TEMPLATE, _section_form_context(form, "create"))
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalSection, {"product": obj.product})
    obj.save()
    _save_section_specialties(obj, request.POST)
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_edit(request, pk: int):
    section = get_object_or_404(TypicalSection, pk=pk)
    if request.method == "GET":
        form = TypicalSectionForm(instance=section)
        return render(request, SECTION_FORM_TEMPLATE, _section_form_context(form, "edit", section))
    form = TypicalSectionForm(request.POST, instance=section)
    if not form.is_valid():
        return render(request, SECTION_FORM_TEMPLATE, _section_form_context(form, "edit", section))
    form.save()
    _save_section_specialties(section, request.POST)
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def section_delete(request, pk: int):
    section = get_object_or_404(TypicalSection, pk=pk)
    section.delete()
    return _render_policy_updated(request)

def _normalize_product_positions():
    """
    Гарантирует сквозную нумерацию позиций (1..N) в порядке текущей сортировки.
    """
    products = Product.objects.order_by("position", "id").only("id", "position")
    for idx, p in enumerate(products, start=1):
        if p.position != idx:
            Product.objects.filter(pk=p.pk).update(position=idx)

def _normalize_section_positions(product_id: int | None = None):
    """
    Гарантирует сквозную нумерацию позиций разделов внутри каждого продукта.
    Если product_id задан, нормализует только для одного продукта.
    """
    qs = TypicalSection.objects.select_related("product").only("id", "position", "product_id")
    if product_id:
        groups = {product_id: list(qs.filter(product_id=product_id).order_by("position", "id"))}
    else:
        # группируем по продукту
        groups = {}
        for sec in qs.order_by("product_id", "position", "id"):
            groups.setdefault(sec.product_id, []).append(sec)
    for pid, items in groups.items():
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                TypicalSection.objects.filter(pk=it.pk).update(position=idx)

@require_http_methods(["POST", "GET"])
@login_required
def product_move_up(request, pk: int):
    _normalize_product_positions()
    items = list(Product.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        Product.objects.filter(pk=cur.id).update(position=prev_pos)
        Product.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_product_positions()
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def product_move_down(request, pk: int):
    _normalize_product_positions()
    items = list(Product.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        Product.objects.filter(pk=cur.id).update(position=next_pos)
        Product.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_product_positions()
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def section_move_up(request, pk: int):
    sec = get_object_or_404(TypicalSection, pk=pk)
    pid = sec.product_id
    _normalize_section_positions(product_id=pid)
    items = list(TypicalSection.objects.filter(product_id=pid).order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        TypicalSection.objects.filter(pk=cur.id).update(position=prev_pos)
        TypicalSection.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_section_positions(product_id=pid)
    return _render_policy_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def section_move_down(request, pk: int):
    sec = get_object_or_404(TypicalSection, pk=pk)
    pid = sec.product_id
    _normalize_section_positions(product_id=pid)
    items = list(TypicalSection.objects.filter(product_id=pid).order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        TypicalSection.objects.filter(pk=cur.id).update(position=next_pos)
        TypicalSection.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_section_positions(product_id=pid)
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def section_csv_upload(request):
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

    products_by_name = {p.short_name.strip().lower(): p for p in Product.objects.all()}
    expertise_units = {
        u.department_name.strip().lower(): u
        for u in OrgUnit.objects.filter(Q(unit_type="expertise") | Q(unit_type="administrative", level=1))
    }
    data_rows = rows[1:]
    created = 0
    warnings = []

    for i, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 8:
            warnings.append(f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 8–9: Продукт, Код, Краткое имя EN, Краткое имя RU, Наименование EN, Наименование RU, Тип учета, Исполнитель, [Направление экспертизы]).")
            continue

        product_name = row[0].strip()
        code = row[1].strip()
        short_name = row[2].strip()
        short_name_ru = row[3].strip() if len(row) > 3 else ""
        name_en = row[4].strip() if len(row) > 4 else ""
        name_ru = row[5].strip() if len(row) > 5 else ""
        accounting_type = row[6].strip() if len(row) > 6 else "Раздел"
        executor = row[7].strip() if len(row) > 7 else ""
        expertise_name = row[8].strip() if len(row) > 8 else ""

        product = products_by_name.get(product_name.lower())
        if not product:
            warnings.append(f"Строка {i}: продукт «{product_name}» не найден. Доступные: {', '.join(products_by_name.keys())}.")
            continue

        if not code:
            warnings.append(f"Строка {i}: отсутствует код раздела.")
            continue

        missing = []
        if not short_name:
            missing.append("Краткое имя EN")
        if not name_en:
            missing.append("Наименование EN")
        if not name_ru:
            missing.append("Наименование RU")
        if not executor:
            missing.append("Исполнитель")
        if missing:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: {', '.join(missing)}.")
            continue

        if accounting_type not in dict(TypicalSection.ACCOUNTING_TYPE_CHOICES):
            warnings.append(f"Строка {i}: неизвестный тип учета «{accounting_type}». Допустимые: {', '.join(dict(TypicalSection.ACCOUNTING_TYPE_CHOICES).keys())}. Установлено «Раздел».")
            accounting_type = "Раздел"

        expertise_direction = None
        if expertise_name:
            expertise_direction = expertise_units.get(expertise_name.lower())
            if not expertise_direction:
                warnings.append(f"Строка {i}: направление экспертизы «{expertise_name}» не найдено. Поле оставлено пустым.")

        position = _next_position(TypicalSection, {"product": product})
        try:
            TypicalSection.objects.create(
                product=product,
                code=code,
                short_name=short_name,
                short_name_ru=short_name_ru,
                name_en=name_en,
                name_ru=name_ru,
                accounting_type=accounting_type,
                executor=executor,
                expertise_direction=expertise_direction,
                position=position,
            )
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


# --- Типовая структура раздела ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def structure_form_create(request):
    if request.method == "GET":
        form = SectionStructureForm()
        return render(request, STRUCTURE_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = SectionStructureForm(request.POST)
    if not form.is_valid():
        return render(request, STRUCTURE_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(SectionStructure)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def structure_form_edit(request, pk: int):
    structure = get_object_or_404(SectionStructure, pk=pk)
    if request.method == "GET":
        form = SectionStructureForm(instance=structure)
        return render(request, STRUCTURE_FORM_TEMPLATE, {"form": form, "action": "edit", "structure": structure})
    form = SectionStructureForm(request.POST, instance=structure)
    if not form.is_valid():
        return render(request, STRUCTURE_FORM_TEMPLATE, {"form": form, "action": "edit", "structure": structure})
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def structure_delete(request, pk: int):
    structure = get_object_or_404(SectionStructure, pk=pk)
    structure.delete()
    return _render_policy_updated(request)


def _normalize_structure_positions():
    items = SectionStructure.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            SectionStructure.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def structure_move_up(request, pk: int):
    _normalize_structure_positions()
    items = list(SectionStructure.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        SectionStructure.objects.filter(pk=cur.id).update(position=prev_pos)
        SectionStructure.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_structure_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def structure_move_down(request, pk: int):
    _normalize_structure_positions()
    items = list(SectionStructure.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        SectionStructure.objects.filter(pk=cur.id).update(position=next_pos)
        SectionStructure.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_structure_positions()
    return _render_policy_updated(request)


# --- Цели услуг и названия отчетов ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def service_goal_report_form_create(request):
    if request.method == "GET":
        form = ServiceGoalReportForm()
        return render(request, SERVICE_GOAL_REPORT_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ServiceGoalReportForm(request.POST)
    if not form.is_valid():
        return render(request, SERVICE_GOAL_REPORT_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ServiceGoalReport)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def service_goal_report_form_edit(request, pk: int):
    service_goal_report = get_object_or_404(ServiceGoalReport, pk=pk)
    if request.method == "GET":
        form = ServiceGoalReportForm(instance=service_goal_report)
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            {"form": form, "action": "edit", "service_goal_report": service_goal_report},
        )
    form = ServiceGoalReportForm(request.POST, instance=service_goal_report)
    if not form.is_valid():
        return render(
            request,
            SERVICE_GOAL_REPORT_FORM_TEMPLATE,
            {"form": form, "action": "edit", "service_goal_report": service_goal_report},
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def service_goal_report_delete(request, pk: int):
    service_goal_report = get_object_or_404(ServiceGoalReport, pk=pk)
    service_goal_report.delete()
    return _render_policy_updated(request)


def _normalize_service_goal_report_positions():
    items = ServiceGoalReport.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ServiceGoalReport.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def service_goal_report_move_up(request, pk: int):
    _normalize_service_goal_report_positions()
    items = list(
        ServiceGoalReport.objects
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ServiceGoalReport.objects.filter(pk=cur.id).update(position=prev_pos)
        ServiceGoalReport.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_service_goal_report_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def service_goal_report_move_down(request, pk: int):
    _normalize_service_goal_report_positions()
    items = list(
        ServiceGoalReport.objects
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ServiceGoalReport.objects.filter(pk=cur.id).update(position=next_pos)
        ServiceGoalReport.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_service_goal_report_positions()
    return _render_policy_updated(request)


# --- Типовой состав услуг ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_composition_form_create(request):
    if request.method == "GET":
        form = TypicalServiceCompositionForm()
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _typical_service_composition_form_context(form, "create"),
        )
    form = TypicalServiceCompositionForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _typical_service_composition_form_context(form, "create"),
        )
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalServiceComposition)
    obj.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def typical_service_composition_form_edit(request, pk: int):
    composition = get_object_or_404(TypicalServiceComposition, pk=pk)
    if request.method == "GET":
        form = TypicalServiceCompositionForm(instance=composition)
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _typical_service_composition_form_context(form, "edit", composition),
        )
    form = TypicalServiceCompositionForm(request.POST, instance=composition)
    if not form.is_valid():
        return render(
            request,
            TYPICAL_SERVICE_COMPOSITION_FORM_TEMPLATE,
            _typical_service_composition_form_context(form, "edit", composition),
        )
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def typical_service_composition_delete(request, pk: int):
    composition = get_object_or_404(TypicalServiceComposition, pk=pk)
    composition.delete()
    return _render_policy_updated(request)


def _normalize_typical_service_composition_positions():
    items = TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            TypicalServiceComposition.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_composition_move_up(request, pk: int):
    _normalize_typical_service_composition_positions()
    items = list(
        TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        TypicalServiceComposition.objects.filter(pk=cur.id).update(position=prev_pos)
        TypicalServiceComposition.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_typical_service_composition_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
@user_passes_test(staff_required)
def typical_service_composition_move_down(request, pk: int):
    _normalize_typical_service_composition_positions()
    items = list(
        TypicalServiceComposition.objects.order_by("position", "id").only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        TypicalServiceComposition.objects.filter(pk=cur.id).update(position=next_pos)
        TypicalServiceComposition.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_typical_service_composition_positions()
    return _render_policy_updated(request)


# --- Направления экспертизы ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def expertise_dir_form_create(request):
    if request.method == "GET":
        form = ExpertiseDirectionForm()
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ExpertiseDirectionForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "create"})
    if not form.instance.position:
        form.instance.position = _next_position(ExpertiseDirection)
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def expertise_dir_form_edit(request, pk: int):
    direction = get_object_or_404(ExpertiseDirection, pk=pk)
    if request.method == "GET":
        form = ExpertiseDirectionForm(instance=direction)
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "edit", "direction": direction})
    form = ExpertiseDirectionForm(request.POST, instance=direction)
    if not form.is_valid():
        return render(request, EXPERTISE_DIR_FORM_TEMPLATE, {"form": form, "action": "edit", "direction": direction})
    form.save()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def expertise_dir_delete(request, pk: int):
    direction = get_object_or_404(ExpertiseDirection, pk=pk)
    direction.delete()
    return _render_policy_updated(request)


def _normalize_expertise_dir_positions():
    items = ExpertiseDirection.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            ExpertiseDirection.objects.filter(pk=it.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def expertise_dir_move_up(request, pk: int):
    _normalize_expertise_dir_positions()
    items = list(ExpertiseDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur = items[idx]
        prev = items[idx - 1]
        cur_pos, prev_pos = cur.position, prev.position
        ExpertiseDirection.objects.filter(pk=cur.id).update(position=prev_pos)
        ExpertiseDirection.objects.filter(pk=prev.id).update(position=cur_pos)
        _normalize_expertise_dir_positions()
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def expertise_dir_move_down(request, pk: int):
    _normalize_expertise_dir_positions()
    items = list(ExpertiseDirection.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur = items[idx]
        nxt = items[idx + 1]
        cur_pos, next_pos = cur.position, nxt.position
        ExpertiseDirection.objects.filter(pk=cur.id).update(position=next_pos)
        ExpertiseDirection.objects.filter(pk=nxt.id).update(position=cur_pos)
        _normalize_expertise_dir_positions()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def products_apply_defaults(request):
    """
    Пакетное применение флагов is_default по отмеченным чекбоксам.
    В POST приходит несколько defaults=<id>. Для всех id из списка ставим True, для остальных — False.
    """
    ids_checked = request.POST.getlist("defaults")
    ids_checked = [int(x) for x in ids_checked if str(x).isdigit()]

    # Обновляем — сначала всем False, затем отмеченным True
    Product.objects.update(is_default=False)
    if ids_checked:
        Product.objects.filter(id__in=ids_checked).update(is_default=True)

    return _render_policy_updated(request)


# --- Грейды ---

def _grade_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


@login_required
@require_http_methods(["GET", "POST"])
def grade_form_create(request):
    if request.method == "GET":
        form = GradeForm(request_user=request.user)
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    form = GradeForm(request.POST, request_user=request.user)
    if not form.is_valid():
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    obj.created_by = _grade_owner(request, form)
    obj.position = _next_position(Grade, {"created_by": obj.created_by})
    obj.save()
    if form.cleaned_data.get("qualification_levels"):
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(
            qualification_levels=obj.qualification_levels
        )
    if obj.is_base_rate:
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(is_base_rate=False)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["GET", "POST"])
def grade_form_edit(request, pk: int):
    grade = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and grade.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = GradeForm(instance=grade, request_user=request.user)
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "edit", "grade": grade,
            "is_admin": request.user.is_superuser,
        })
    form = GradeForm(request.POST, instance=grade, request_user=request.user)
    if not form.is_valid():
        return render(request, GRADE_FORM_TEMPLATE, {
            "form": form, "action": "edit", "grade": grade,
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    if form.cleaned_data.get("qualification_levels"):
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(
            qualification_levels=obj.qualification_levels
        )
    if obj.is_base_rate:
        Grade.objects.filter(created_by=obj.created_by).exclude(pk=obj.pk).update(is_base_rate=False)
    return _render_policy_updated(request)


@login_required
@require_POST
def grade_delete(request, pk: int):
    grade = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and grade.created_by != request.user:
        return _render_policy_updated(request)
    grade.delete()
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def grade_move_up(request, pk: int):
    obj = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Grade.objects.filter(created_by=obj.created_by)
    prev = qs.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Grade.objects.filter(pk=obj.pk).update(position=obj.position)
        Grade.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def grade_move_down(request, pk: int):
    obj = get_object_or_404(Grade, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Grade.objects.filter(created_by=obj.created_by)
    nxt = qs.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Grade.objects.filter(pk=obj.pk).update(position=obj.position)
        Grade.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_policy_updated(request)


# --- Тарифы специальностей ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_tariff_form_create(request):
    if request.method == "GET":
        form = SpecialtyTariffForm(request_user=request.user)
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "create"),
                "is_admin": request.user.is_superuser,
            },
        )
    form = SpecialtyTariffForm(request.POST, request_user=request.user)
    if not form.is_valid():
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "create"),
                "is_admin": request.user.is_superuser,
            },
        )
    obj = form.save(commit=False)
    obj.created_by = _specialty_tariff_owner(request, form)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(SpecialtyTariff, {"created_by": obj.created_by})
    obj.save()
    form.save_m2m()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_tariff_form_edit(request, pk: int):
    specialty_tariff = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and specialty_tariff.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = SpecialtyTariffForm(instance=specialty_tariff, request_user=request.user)
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "edit", specialty_tariff),
                "is_admin": request.user.is_superuser,
            },
        )
    form = SpecialtyTariffForm(request.POST, instance=specialty_tariff, request_user=request.user)
    if not form.is_valid():
        return render(
            request,
            SPECIALTY_TARIFF_FORM_TEMPLATE,
            {
                **_specialty_tariff_form_context(form, "edit", specialty_tariff),
                "is_admin": request.user.is_superuser,
            },
        )
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    form.save_m2m()
    return _render_policy_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def specialty_tariff_delete(request, pk: int):
    specialty_tariff = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and specialty_tariff.created_by != request.user:
        return _render_policy_updated(request)
    specialty_tariff.delete()
    return _render_policy_updated(request)


def _normalize_specialty_tariff_positions():
    items = SpecialtyTariff.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            SpecialtyTariff.objects.filter(pk=item.pk).update(position=idx)


@require_http_methods(["POST", "GET"])
@login_required
def specialty_tariff_move_up(request, pk: int):
    obj = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = SpecialtyTariff.objects.filter(created_by=obj.created_by)
    prev = qs.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        SpecialtyTariff.objects.filter(pk=obj.pk).update(position=obj.position)
        SpecialtyTariff.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_policy_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def specialty_tariff_move_down(request, pk: int):
    obj = get_object_or_404(SpecialtyTariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = SpecialtyTariff.objects.filter(created_by=obj.created_by)
    nxt = qs.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        SpecialtyTariff.objects.filter(pk=obj.pk).update(position=obj.position)
        SpecialtyTariff.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_policy_updated(request)


# --- Тарифы ---

def _tariff_owner(request, form):
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            return owner
    return request.user


@login_required
@require_http_methods(["GET", "POST"])
def tariff_form_create(request):
    if request.method == "GET":
        form = TariffForm(request_user=request.user)
        return render(request, TARIFF_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    form = TariffForm(request.POST, request_user=request.user)
    if not form.is_valid():
        return render(request, TARIFF_FORM_TEMPLATE, {
            "form": form, "action": "create",
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    obj.created_by = _tariff_owner(request, form)
    obj.position = _next_position(Tariff, {"created_by": obj.created_by})
    obj.save()
    return _render_policy_updated(request)


@login_required
@require_http_methods(["GET", "POST"])
def tariff_form_edit(request, pk: int):
    tariff = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and tariff.created_by != request.user:
        return _render_policy_updated(request)
    if request.method == "GET":
        form = TariffForm(instance=tariff, request_user=request.user)
        return render(request, TARIFF_FORM_TEMPLATE, {
            "form": form, "action": "edit", "tariff": tariff,
            "is_admin": request.user.is_superuser,
        })
    form = TariffForm(request.POST, instance=tariff, request_user=request.user)
    if not form.is_valid():
        return render(request, TARIFF_FORM_TEMPLATE, {
            "form": form, "action": "edit", "tariff": tariff,
            "is_admin": request.user.is_superuser,
        })
    obj = form.save(commit=False)
    if request.user.is_superuser:
        owner = form.cleaned_data.get("owner")
        if owner:
            obj.created_by = owner
    obj.save()
    return _render_policy_updated(request)


@login_required
@require_POST
def tariff_delete(request, pk: int):
    tariff = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and tariff.created_by != request.user:
        return _render_policy_updated(request)
    tariff.delete()
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def tariff_move_up(request, pk: int):
    obj = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Tariff.objects.filter(created_by=obj.created_by)
    prev = qs.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Tariff.objects.filter(pk=obj.pk).update(position=obj.position)
        Tariff.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_policy_updated(request)


@login_required
@require_http_methods(["POST", "GET"])
def tariff_move_down(request, pk: int):
    obj = get_object_or_404(Tariff, pk=pk)
    if not request.user.is_superuser and obj.created_by != request.user:
        return _render_policy_updated(request)
    qs = Tariff.objects.filter(created_by=obj.created_by)
    nxt = qs.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Tariff.objects.filter(pk=obj.pk).update(position=obj.position)
        Tariff.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_policy_updated(request)
