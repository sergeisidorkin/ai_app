from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db.models import Max
from django import forms
from .models import ProjectRegistration, WorkVolume, Performer, WorkVolumeItem, LegalEntity
from .forms import ProjectRegistrationForm, WorkVolumeForm, PerformerForm, BootstrapMixin, LegalEntityForm

import json

from policy_app.models import TypicalSection

PROJECTS_PARTIAL_TEMPLATE = "projects_app/projects_partial.html"
REG_FORM_TEMPLATE       = "projects_app/registration_form.html"
WORK_FORM_TEMPLATE      = "projects_app/work_form.html"
LEGAL_FORM_TEMPLATE     = "projects_app/legal_entity_form.html"

PERF_FORM_TEMPLATE    = "projects_app/performer_form.html"
PERFORMERS_PARTIAL_TEMPLATE = "projects_app/performers_partial.html"

HX_TRIGGER_HEADER = "HX-Trigger"
HX_PERFORMERS_UPDATED_EVENT = "performers-updated"
HX_PROJECTS_UPDATED_EVENT = "projects-updated"

def staff_required(user):
    return user.is_authenticated and user.is_staff

def _projects_context():
    registrations = ProjectRegistration.objects.all()
    work_items = WorkVolume.objects.select_related("project").all()
    legal_entities = (
        LegalEntity.objects
        .select_related("project", "work_item", "work_item__project")
        .all()
    )
    legal_projects = (
        ProjectRegistration.objects
        .filter(legal_entities__isnull=False)
        .distinct()
        .order_by("position", "id")
    )
    return {
        "registrations": registrations,
        "work_items": work_items,
        "legal_entities": legal_entities,
        "legal_projects": legal_projects,
    }

def _render_projects_updated(request):
    resp = render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())
    resp[HX_TRIGGER_HEADER] = HX_PROJECTS_UPDATED_EVENT
    return resp

def _next_position(model, filters: dict | None = None) -> int:
    qs = model.objects
    if filters:
        qs = qs.filter(**filters)
    last = qs.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1

@login_required
@require_http_methods(["GET"])
def projects_partial(request):
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())

# --- Регистрация проекта ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_create(request):
    if request.method == "GET":
        form = ProjectRegistrationForm()
        return render(request, REG_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ProjectRegistrationForm(request.POST)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ProjectRegistration)
    obj.save()
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ProjectRegistrationForm(instance=reg)
        return render(request, REG_FORM_TEMPLATE, {"form": form, "action": "edit", "registration": reg})
    form = ProjectRegistrationForm(request.POST, instance=reg)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, {"form": form, "action": "edit", "registration": reg})
    form.save()
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_delete(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    reg.delete()
    return _render_projects_updated(request)

def _normalize_registration_positions():
    items = ProjectRegistration.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            ProjectRegistration.objects.filter(pk=it.pk).update(position=idx)

@require_http_methods(["POST", "GET"])
@login_required
def registration_move_up(request, pk: int):
    _normalize_registration_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx-1]
        ProjectRegistration.objects.filter(pk=cur.id).update(position=prev.position)
        ProjectRegistration.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_registration_positions()
    return _render_projects_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def registration_move_down(request, pk: int):
    _normalize_registration_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx+1]
        ProjectRegistration.objects.filter(pk=cur.id).update(position=nxt.position)
        ProjectRegistration.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_registration_positions()
    return _render_projects_updated(request)

# --- Объем работ ---
@login_required
@require_GET
def work_deps(request):
    """
    Вернёт данные для автоподстановки по выбранному проекту:
      - type / type_short (из Product)
      - name (из ProjectRegistration)
    """
    pid = request.GET.get("project")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False})

    reg = ProjectRegistration.objects.select_related("type").filter(pk=pid).first()
    if not reg:
        return JsonResponse({"ok": False})

    return JsonResponse({
        "ok": True,
        "type": str(reg.type) if reg.type_id else "",
        "type_short": getattr(reg.type, "short_name", "") if reg.type_id else "",
        "name": reg.name or "",
    })


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_create(request):
    if request.method == "GET":
        form = WorkVolumeForm()
        return render(request, WORK_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = WorkVolumeForm(request.POST)
    if not form.is_valid():
        return render(request, WORK_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(WorkVolume, {"project": obj.project})
    obj.save()
    return _render_projects_updated(request)

# Редактирование регистрации
@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ProjectRegistrationForm(instance=reg)
        return render(request, REG_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg
        })
    form = ProjectRegistrationForm(request.POST, instance=reg)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg
        })
    form.save()
    return _render_projects_updated(request)

class RegistrationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = getattr(obj.type, "short_name", obj.type) if obj.type_id else ""
        name_label = obj.name or ""
        parts = [obj.short_uid]
        if type_label:
            parts.append(str(type_label))
        if name_label:
            parts.append(name_label)
        return " ".join(parts)

class PerformerForm(BootstrapMixin, forms.ModelForm):
    registration = RegistrationChoiceField(
        label="Проект",
        queryset=ProjectRegistration.objects.select_related("type").order_by("-id"),
        required=True,
        widget=forms.Select(),
    )
    # делаем asset_name селектом, чтобы можно было подменять options с сервера/JS
    asset_name = forms.ChoiceField(label="Актив", required=False, choices=[("", "— Не выбрано —")])

    # «Номер» — через наш кастомный ModelChoiceField
    registration = RegistrationChoiceField(
        label="Номер",
        queryset=ProjectRegistration.objects.select_related("type").order_by("-id"),
        required=True,
        widget=forms.Select(),
    )

    typical_section = forms.ModelChoiceField(
        label="Типовые разделы",
        queryset=TypicalSection.objects.none(),  # наполняется вьюхой в зависимости от выбранного «Номер»
        required=False,
        empty_label="— Не выбрано —",
        widget=forms.Select(),
    )

    class Meta:
        model = Performer
        fields = [
            "registration", "asset_name", "executor", "grade",
            "typical_section", "actual_costs", "estimated_costs",
            "agreed_amount", "prepayment", "final_payment", "contract_number",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


# Редактирование записи "Объем работ"
@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_edit(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    if request.method == "GET":
        form = WorkVolumeForm(instance=item)
        return render(request, WORK_FORM_TEMPLATE, {
            "form": form, "action": "edit", "work": item
        })
    form = WorkVolumeForm(request.POST, instance=item)
    if not form.is_valid():
        return render(request, WORK_FORM_TEMPLATE, {
            "form": form, "action": "edit", "work": item
        })
    form.save()
    return _render_projects_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def work_delete(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id
    item.delete()
    _normalize_work_positions(pid)
    _normalize_legal_positions(pid)
    return _render_projects_updated(request)

def _normalize_work_positions(product_id: int | None = None):
    qs = WorkVolume.objects.select_related("project").only("id", "position", "project_id")
    if product_id:
        items = list(qs.filter(project_id=product_id).order_by("position", "id"))
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                WorkVolume.objects.filter(pk=it.pk).update(position=idx)
    else:
        # Группами по проекту
        cur_pid = None
        buf = []
        for it in qs.order_by("project_id", "position", "id"):
            if cur_pid is None:
                cur_pid = it.project_id
            if it.project_id != cur_pid:
                for idx, b in enumerate(buf, start=1):
                    if b.position != idx:
                        WorkVolume.objects.filter(pk=b.pk).update(position=idx)
                cur_pid, buf = it.project_id, [it]
            else:
                buf.append(it)
        for idx, b in enumerate(buf, start=1):
            if b.position != idx:
                WorkVolume.objects.filter(pk=b.pk).update(position=idx)

def _normalize_legal_positions(project_id: int | None = None):
    qs = LegalEntity.objects.select_related("project").only("id", "position", "project_id")
    if project_id:
        items = list(qs.filter(project_id=project_id).order_by("position", "id"))
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                LegalEntity.objects.filter(pk=it.pk).update(position=idx)
        return

    cur_pid = None
    buf = []
    for it in qs.order_by("project_id", "position", "id"):
        if cur_pid is None:
            cur_pid = it.project_id
        if it.project_id != cur_pid:
            for idx, b in enumerate(buf, start=1):
                if b.position != idx:
                    LegalEntity.objects.filter(pk=b.pk).update(position=idx)
            cur_pid, buf = it.project_id, [it]
        else:
            buf.append(it)
    for idx, b in enumerate(buf, start=1):
        if b.position != idx:
            LegalEntity.objects.filter(pk=b.pk).update(position=idx)

@require_http_methods(["POST", "GET"])
@login_required
def work_move_up(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id

    _normalize_work_positions(pid)
    items = list(
        WorkVolume.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        WorkVolume.objects.filter(pk=cur.id).update(position=prev.position)
        WorkVolume.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_work_positions(pid)

    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ БЕЗ HX-Trigger — чтобы не было двойной перерисовки
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())

@require_http_methods(["POST", "GET"])
@login_required
def work_move_down(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id

    _normalize_work_positions(pid)
    items = list(
        WorkVolume.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        WorkVolume.objects.filter(pk=cur.id).update(position=nxt.position)
        WorkVolume.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_work_positions(pid)

    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ БЕЗ HX-Trigger — чтобы не было двойной перерисовки
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def legal_entity_form_create(request):
    if request.method == "GET":
        form = LegalEntityForm()
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = LegalEntityForm(request.POST)
    if not form.is_valid():
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "create"})
    entity = form.save(commit=False)
    if not getattr(entity, "position", 0):
        entity.position = _next_position(LegalEntity, {"project": entity.project})
    entity.save()
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def legal_entity_form_edit(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    if request.method == "GET":
        form = LegalEntityForm(instance=entity)
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "edit", "legal_entity": entity})
    form = LegalEntityForm(request.POST, instance=entity)
    if not form.is_valid():
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "edit", "legal_entity": entity})
    form.save()
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def legal_entity_delete(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    pid = entity.project_id
    entity.delete()
    _normalize_legal_positions(pid)
    return _render_projects_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def legal_entity_move_up(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    pid = entity.project_id

    _normalize_legal_positions(pid)
    items = list(
        LegalEntity.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LegalEntity.objects.filter(pk=cur.id).update(position=prev.position)
        LegalEntity.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_legal_positions(pid)

    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())

@require_http_methods(["POST", "GET"])
@login_required
def legal_entity_move_down(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    pid = entity.project_id

    _normalize_legal_positions(pid)
    items = list(
        LegalEntity.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LegalEntity.objects.filter(pk=cur.id).update(position=nxt.position)
        LegalEntity.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_legal_positions(pid)

    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context())

def _bind_dynamic_performer_fields(form, *, data=None, instance=None):
    """
    Привязать серверные зависимости формы:
      - typical_section.queryset по продукту выбранной регистрации
      - choices для asset_name по WorkVolume выбранной регистрации
    """
    reg_id = None
    if data and data.get("registration"):
        reg_id = data.get("registration")
    elif instance is not None:
        reg_id = getattr(instance, "registration_id", None)

    # Привязываем queryset для Типовых разделов
    if "typical_section" in form.fields:
        qs = TypicalSection.objects.none()
        if reg_id:
            reg = ProjectRegistration.objects.select_related("type").filter(pk=reg_id).first()
            if reg and reg.type_id:
                qs = TypicalSection.objects.filter(product=reg.type).order_by("code", "id")
        form.fields["typical_section"].queryset = qs

    # Привязываем choices для Активов (если поле отрисовано как select)
    if "asset_name" in form.fields:
        assets = []
        if reg_id:
            assets = list(
                WorkVolume.objects
                .filter(project_id=reg_id)
                .values_list("asset_name", flat=True)
                .distinct()
            )
        choices = [("", "— Не выбрано —")] + [(a, a) for a in assets if a]
        # Если поле CharField с Select-виджетом — просто зададим choices на виджете
        try:
            form.fields["asset_name"].widget.choices = choices
        except Exception:
            pass
        # Если вдруг это ChoiceField — зададим и на самом поле
        try:
            form.fields["asset_name"].choices = choices
        except Exception:
            pass

def _performers_context():
    performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section")
        .order_by("position", "id")
    )
    return {"performers": performers}

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())

def _performer_form_ctx(form, action: str, performer=None):
    regs = ProjectRegistration.objects.select_related("type").order_by("position", "id")

    reg_map = {
        str(r.id): {
            "group": r.group,
            "type": str(r.type) if r.type_id else "",
            "type_short": getattr(r.type, "short_name", "") if r.type_id else "",
            "name": r.name,
        }
        for r in regs
    }
    assets_map = {
        str(r.id): [
            a for a in WorkVolume.objects
                     .filter(project=r)
                     .values_list("asset_name", flat=True)
                     .distinct()
            if a
        ]
        for r in regs
    }
    sections_map = {}
    for r in regs:
        if not r.type_id:
            sections_map[str(r.id)] = []
            continue
        qs = TypicalSection.objects.filter(product=r.type).only("id", "code").order_by("code", "id")
        sections_map[str(r.id)] = [{"id": s.id, "code": s.code} for s in qs]

    return {
        "form": form,
        "action": action,
        "performer": performer,
        "reg_map_json": json.dumps(reg_map, ensure_ascii=False),
        "assets_map_json": json.dumps(assets_map, ensure_ascii=False),
        "sections_map_json": json.dumps(sections_map, ensure_ascii=False),
    }

def _render_performers_updated(request):
    resp = render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())

def _next_performer_position():
    mx = Performer.objects.aggregate(Max("position")).get("position__max") or 0
    return mx + 1

@login_required
@require_http_methods(["GET", "POST"])
def performer_form_create(request):
    """
    GET:  вернуть форму в модалку (с JSON-картами и привязанными server-side зависимостями).
    POST: если форма невалидна — вернуть её обратно (200), если валидна — 204 + HX-Trigger.
    """
    if request.method == "GET":
        form = PerformerForm()
        _bind_dynamic_performer_fields(form)  # чтобы селекты были заполнены сразу
        return render(request, PERF_FORM_TEMPLATE, _performer_form_ctx(form, "create"))

    # POST
    form = PerformerForm(request.POST)
    _bind_dynamic_performer_fields(form, data=request.POST)  # ВАЖНО: привязать перед is_valid()

    if not form.is_valid():
        # Статус 200 — чтобы htmx спокойно перерисовал содержимое модалки шаблоном формы с ошибками
        return render(
            request,
            PERF_FORM_TEMPLATE,
            _performer_form_ctx(form, "create"),
            status=200,
        )

    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_performer_position()
    obj.save()

    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT  # "performers-updated"
    return resp

@login_required
@require_http_methods(["GET", "POST"])
def performer_form_edit(request, pk: int):
    """
    GET:  отдать форму редактирования в модалку (с картами и привязками).
    POST: если невалидно — вернуть форму (200); если ок — 204 + HX-Trigger.
    """
    p = get_object_or_404(Performer, pk=pk)

    if request.method == "GET":
        form = PerformerForm(instance=p)
        _bind_dynamic_performer_fields(form, instance=p)
        return render(
            request,
            PERF_FORM_TEMPLATE,
            _performer_form_ctx(form, "edit", performer=p),
        )

    # POST
    form = PerformerForm(request.POST, instance=p)
    _bind_dynamic_performer_fields(form, data=request.POST, instance=p)

    if not form.is_valid():
        return render(
            request,
            PERF_FORM_TEMPLATE,
            _performer_form_ctx(form, "edit", performer=p),
            status=200,
        )

    form.save()
    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp

@login_required
@require_POST
def performer_delete(request, pk: int):
    p = get_object_or_404(Performer, pk=pk)
    p.delete()
    return _render_performers_updated(request)

def _normalize_performer_positions():
    items = Performer.objects.order_by("position", "id").only("id", "position")
    for i, it in enumerate(items, start=1):
        if it.position != i:
            Performer.objects.filter(pk=it.pk).update(position=i)

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_up(request, pk: int):
    _normalize_performer_positions()
    items = list(Performer.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx-1]
        Performer.objects.filter(pk=cur.id).update(position=prev.position)
        Performer.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_performer_positions()
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_down(request, pk: int):
    _normalize_performer_positions()
    items = list(Performer.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx+1]
        Performer.objects.filter(pk=cur.id).update(position=nxt.position)
        Performer.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_performer_positions()
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())

@login_required
@require_GET
def legal_entity_work_deps(request):
    wid = request.GET.get("work_item")
    try:
        wid = int(wid)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False})

    work = (
        WorkVolume.objects
        .select_related("project")
        .filter(pk=wid)
        .first()
    )
    if not work:
        return JsonResponse({"ok": False})

    return JsonResponse({
        "ok": True,
        "project": getattr(work.project, "short_uid", ""),
        "type": work.type or "",
        "name": work.name or "",
    })    