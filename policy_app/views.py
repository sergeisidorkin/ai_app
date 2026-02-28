from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Max
from .models import Product, TypicalSection, SectionStructure, Grade, DEPARTMENT_HEAD_GROUP
from .forms import ProductForm, TypicalSectionForm, SectionStructureForm, GradeForm

# Вынесенные константы для единообразия шаблонов/заголовков
POLICY_PARTIAL_TEMPLATE = "policy_app/policy_partial.html"
PRODUCT_FORM_TEMPLATE = "policy_app/product_form.html"
SECTION_FORM_TEMPLATE = "policy_app/section_form.html"
STRUCTURE_FORM_TEMPLATE = "policy_app/structure_form.html"
GRADE_FORM_TEMPLATE = "policy_app/grade_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_POLICY_UPDATED_EVENT = "policy-updated"


def _is_department_head(user):
    return user.groups.filter(name=DEPARTMENT_HEAD_GROUP).exists()


def _get_grades_for_user(user):
    qs = Grade.objects.select_related("created_by", "created_by__employee_profile")
    if user.is_superuser:
        return qs
    if _is_department_head(user):
        return qs.filter(created_by=user)
    return qs

def staff_required(user):
    return user.is_authenticated and user.is_staff

# Вспомогательные функции для устранения дублирования
def _policy_context(request):
    products = Product.objects.all()
    sections = TypicalSection.objects.select_related("product").all()
    structures = SectionStructure.objects.select_related("product", "section").all()
    grades = _get_grades_for_user(request.user)
    is_dept_head = _is_department_head(request.user)
    return {
        "products": products,
        "sections": sections,
        "structures": structures,
        "grades": grades,
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
        return render(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    # Если позиция не задана/нулевая — ставим в конец списка
    if not getattr(obj, "position", 0):
        obj.position = _next_position(Product)
    obj.save()
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
        return render(request, PRODUCT_FORM_TEMPLATE, {"form": form, "action": "edit", "product": product})
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

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_create(request):
    if request.method == "GET":
        form = TypicalSectionForm()
        return render(request, SECTION_FORM_TEMPLATE, {"form": form, "action": "create"})
    # POST
    form = TypicalSectionForm(request.POST)
    if not form.is_valid():
        return render(request, SECTION_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    # Новый раздел — в конец списка своего продукта
    if not getattr(obj, "position", 0):
        obj.position = _next_position(TypicalSection, {"product": obj.product})
    obj.save()
    return _render_policy_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def section_form_edit(request, pk: int):
    section = get_object_or_404(TypicalSection, pk=pk)
    if request.method == "GET":
        form = TypicalSectionForm(instance=section)
        return render(request, SECTION_FORM_TEMPLATE, {"form": form, "action": "edit", "section": section})
    # POST
    form = TypicalSectionForm(request.POST, instance=section)
    if not form.is_valid():
        return render(request, SECTION_FORM_TEMPLATE, {"form": form, "action": "edit", "section": section})
    form.save()
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
