from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db import transaction
from django.db.models import Max, Q
from django.db.models.functions import Trim
from django import forms
from django.utils import timezone
from classifiers_app.models import LegalEntityIdentifier, LegalEntityRecord
from .models import ProjectRegistration, WorkVolume, Performer, WorkVolumeItem, LegalEntity, RegistrationWorkspaceFolder
from .forms import ProjectRegistrationForm, ContractConditionsForm, WorkVolumeForm, PerformerForm, BootstrapMixin, LegalEntityForm

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from experts_app.models import ExpertProfile
from policy_app.models import TypicalSection
from users_app.models import Employee
from notifications_app.services import create_participation_notifications, create_info_request_notifications, create_contract_notifications

PROJECTS_PARTIAL_TEMPLATE = "projects_app/projects_partial.html"
REG_FORM_TEMPLATE       = "projects_app/registration_form.html"
CONTRACT_FORM_TEMPLATE  = "projects_app/contract_form.html"
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
    registrations = ProjectRegistration.objects.select_related("country").all()
    work_items = WorkVolume.objects.select_related("project", "country").all()
    legal_entities = (
        LegalEntity.objects
        .select_related("project", "work_item", "work_item__project", "country")
        .all()
    )
    legal_projects = (
        ProjectRegistration.objects
        .filter(legal_entities__isnull=False)
        .distinct()
        .order_by("-number", "-id")
    )
    work_projects = (
        ProjectRegistration.objects
        .filter(work_items__isnull=False)
        .distinct()
        .order_by("-number", "-id")
    )
    reg_filter_projects = ProjectRegistration.objects.order_by("-number", "-id")
    return {
        "registrations": registrations,
        "reg_filter_projects": reg_filter_projects,
        "work_items": work_items,
        "work_projects": work_projects,
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

def _sync_to_legal_entity_record(short_name, country, identifier, registration_number, registration_date, user=None):
    """Create or update a LegalEntityRecord from project data."""
    short_name = (short_name or "").strip()
    if not short_name:
        return
    defaults = {
        "registration_country": country,
        "identifier": identifier or "",
        "registration_number": registration_number or "",
        "registration_date": registration_date,
    }
    if user:
        from classifiers_app.views import _ler_record_author
        from datetime import date as _date
        defaults["record_date"] = _date.today()
        defaults["record_author"] = _ler_record_author(user)
    try:
        ler, created = LegalEntityRecord.objects.get_or_create(
            short_name=short_name,
            defaults=defaults,
        )
    except LegalEntityRecord.MultipleObjectsReturned:
        ler = LegalEntityRecord.objects.filter(short_name=short_name).order_by("id").first()
        created = False
    if not created:
        changed = False
        for field, val in defaults.items():
            if getattr(ler, field) != val:
                setattr(ler, field, val)
                changed = True
        if changed:
            ler.save()


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
    _sync_to_legal_entity_record(
        obj.customer, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
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
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.customer, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
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

# --- Условия контракта ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ContractConditionsForm(instance=reg)
        return render(request, CONTRACT_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg,
        })
    form = ContractConditionsForm(request.POST, instance=reg)
    if not form.is_valid():
        return render(request, CONTRACT_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg,
        })
    form.save()
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

    reg = ProjectRegistration.objects.select_related("type", "country").filter(pk=pid).first()
    if not reg:
        return JsonResponse({"ok": False})

    return JsonResponse({
        "ok": True,
        "type": str(reg.type) if reg.type_id else "",
        "type_short": getattr(reg.type, "short_name", "") if reg.type_id else "",
        "name": reg.name or "",
        "project_manager": reg.project_manager or "",
        "country_id": reg.country_id or "",
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
    _sync_to_legal_entity_record(
        obj.asset_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response

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
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.customer, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
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


def _employee_full_name(employee):
    parts = [
        employee.user.last_name.strip(),
        employee.user.first_name.strip(),
        employee.patronymic.strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _executor_choices(current_value=""):
    choices = [("", "— Не выбрано —")]
    current_value = (current_value or "").strip()
    current_in_choices = False

    employees = (
        Employee.objects
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )
    for employee in employees:
        full_name = _employee_full_name(employee)
        if not full_name:
            continue
        choices.append((full_name, full_name))
        if full_name == current_value:
            current_in_choices = True

    if current_value and not current_in_choices:
        choices.insert(1, (current_value, current_value))

    return choices


def _typical_section_option_label(section):
    product = getattr(section.product, "short_name", "") if getattr(section, "product_id", None) else ""
    code = section.code or ""
    short_name_ru = section.short_name_ru or ""
    head = f"{product}:{code}" if product else code
    return " ".join(part for part in (head, short_name_ru) if part).strip()


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
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.asset_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response


def _delete_related_performers_for_work_item(item: WorkVolume):
    """
    Удаляет связанные строки исполнителей:
      - новые строки, уже привязанные через work_item
      - старые строки без work_item, совпадающие по проекту/активу
    """
    asset_name = (item.asset_name or item.name or "").strip()
    filters = Q(work_item=item)
    if asset_name:
        filters |= Q(
            work_item__isnull=True,
            registration=item.project,
            asset_name=asset_name,
        )
    Performer.objects.filter(filters).delete()


@login_required
@user_passes_test(staff_required)
@require_POST
def work_delete(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id
    _delete_related_performers_for_work_item(item)
    item.delete()
    _normalize_work_positions(pid)
    _normalize_legal_positions(pid)
    _normalize_performer_positions()
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response

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
    _sync_to_legal_entity_record(
        entity.legal_name, entity.country, entity.identifier,
        entity.registration_number, entity.registration_date, request.user,
    )
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
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.legal_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
    )
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
    current_asset = ""
    if data and data.get("registration"):
        reg_id = data.get("registration")
    elif instance is not None:
        reg_id = getattr(instance, "registration_id", None)
    if data and data.get("asset_name"):
        current_asset = data.get("asset_name", "")
    elif instance is not None:
        current_asset = getattr(instance, "asset_name", "") or ""

    # Привязываем queryset для Типовых разделов
    if "typical_section" in form.fields:
        qs = TypicalSection.objects.none()
        if reg_id:
            reg = ProjectRegistration.objects.select_related("type").filter(pk=reg_id).first()
            if reg and reg.type_id:
                qs = TypicalSection.objects.filter(product=reg.type).select_related("product").order_by("position", "id")
        form.fields["typical_section"].queryset = qs
        form.fields["typical_section"].label_from_instance = _typical_section_option_label

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
        if current_asset and current_asset not in assets:
            assets.append(current_asset)
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
    active_participation_statuses = ["Не начат", "В работе"]
    performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "employee", "employee__user", "currency")
        .order_by("position", "id")
    )
    participation_performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "employee", "employee__user")
        .annotate(executor_trim=Trim("executor"))
        .filter(registration__status__in=active_participation_statuses)
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    participation_project_ids = participation_performers.values_list("registration_id", flat=True).distinct()
    participation_projects = (
        ProjectRegistration.objects
        .filter(id__in=participation_project_ids)
        .order_by("-number", "-id")
    )
    info_request_performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "employee", "employee__user")
        .annotate(executor_trim=Trim("executor"))
        .filter(
            registration__status__in=active_participation_statuses,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    info_request_project_ids = info_request_performers.values_list("registration_id", flat=True).distinct()
    info_request_projects = (
        ProjectRegistration.objects
        .filter(id__in=info_request_project_ids)
        .order_by("-number", "-id")
    )
    contract_performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "employee", "employee__user", "currency")
        .annotate(executor_trim=Trim("executor"))
        .filter(
            registration__status__in=active_participation_statuses,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    contract_project_ids = contract_performers.values_list("registration_id", flat=True).distinct()
    contract_projects = (
        ProjectRegistration.objects
        .filter(id__in=contract_project_ids)
        .order_by("-number", "-id")
    )
    request_sent_initial = timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    performer_project_ids = performers.values_list("registration_id", flat=True).distinct()
    performer_projects = (
        ProjectRegistration.objects
        .filter(id__in=performer_project_ids)
        .order_by("-number", "-id")
    )
    return {
        "performers": performers,
        "performer_projects": performer_projects,
        "participation_performers": participation_performers,
        "participation_projects": participation_projects,
        "participation_request_sent_initial": request_sent_initial,
        "info_request_performers": info_request_performers,
        "info_request_projects": info_request_projects,
        "info_request_sent_initial": request_sent_initial,
        "contract_performers": contract_performers,
        "contract_projects": contract_projects,
        "contract_request_sent_initial": request_sent_initial,
    }

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context())

def _build_executor_grade_map():
    profiles = (
        ExpertProfile.objects
        .select_related("employee__user", "grade")
    )
    result = {}
    for p in profiles:
        u = p.employee.user
        parts = [u.last_name or "", u.first_name or "", p.employee.patronymic or ""]
        full_name = " ".join(part for part in parts if part)
        if not full_name:
            continue
        g = p.grade
        entry = {
            "country_id": p.country_id,
            "region_id": p.region_id,
        }
        if g:
            entry.update({
                "grade_name": g.grade_ru or g.grade_en,
                "qualification": g.qualification,
                "qualification_levels": g.qualification_levels,
                "base_rate_share": 0 if g.is_base_rate else g.base_rate_share,
            })
        result[full_name] = entry
    return result


def _build_living_wage_map():
    from classifiers_app.models import LivingWage
    today = timezone.now().date()
    wages = (
        LivingWage.objects
        .filter(
            Q(approval_date__lte=today),
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
        )
        .order_by("-approval_date")
    )
    result = {}
    for w in wages:
        key = f"{w.country_id}_{w.region_id}"
        if key not in result:
            result[key] = float(w.amount)
    return result


def _build_tariff_map():
    from policy_app.models import Tariff
    tariffs = Tariff.objects.select_related("product", "section").all()
    result = {}
    for t in tariffs:
        key = f"{t.product_id}_{t.section_id}"
        result[key] = float(t.base_rate_vpm)
    return result


def _performer_form_ctx(form, action: str, performer=None):
    regs = ProjectRegistration.objects.select_related("type").order_by("position", "id")

    reg_map = {
        str(r.id): {
            "group": r.group,
            "type": str(r.type) if r.type_id else "",
            "type_short": getattr(r.type, "short_name", "") if r.type_id else "",
            "type_id": r.type_id,
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
        qs = (
            TypicalSection.objects
            .filter(product=r.type)
            .select_related("product")
            .only("id", "code", "short_name_ru", "product__short_name", "position")
            .order_by("position", "id")
        )
        sections_map[str(r.id)] = [
            {"id": s.id, "label": _typical_section_option_label(s)}
            for s in qs
        ]

    executor_grade_map = _build_executor_grade_map()
    living_wage_map = _build_living_wage_map()
    tariff_map = _build_tariff_map()

    return {
        "form": form,
        "action": action,
        "performer": performer,
        "reg_map_json": json.dumps(reg_map, ensure_ascii=False),
        "assets_map_json": json.dumps(assets_map, ensure_ascii=False),
        "sections_map_json": json.dumps(sections_map, ensure_ascii=False),
        "executor_grade_json": json.dumps(executor_grade_map, ensure_ascii=False),
        "living_wage_json": json.dumps(living_wage_map, ensure_ascii=False),
        "tariff_json": json.dumps(tariff_map, ensure_ascii=False),
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


def _parse_request_sent_at(raw_value: str):
    if not raw_value:
        return timezone.localtime().replace(second=0, microsecond=0)
    try:
        value = datetime.fromisoformat(raw_value)
    except ValueError:
        raise forms.ValidationError("Некорректная дата отправки запроса.")
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.replace(second=0, microsecond=0)


def _round_up_to_hour(value):
    value = value.replace(second=0, microsecond=0)
    if value.minute == 0:
        return value
    return (value + timedelta(hours=1)).replace(minute=0)

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
@user_passes_test(staff_required)
@require_POST
def participation_request(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для запроса."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    selected_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    try:
        with transaction.atomic():
            create_participation_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
            )
            updated = Performer.objects.filter(pk__in=performer_ids).update(
                participation_request_sent_at=request_sent_at,
                participation_deadline_at=deadline_at,
                participation_response="",
                participation_response_at=None,
            )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
        }
    )


def _build_contract_number(performer, sent_at, addendum_number=None):
    reg = getattr(performer, "registration", None)
    if not reg or getattr(reg, "group", "") != "RU":
        return ""
    parts = (performer.executor or "").split()
    if len(parts) < 2:
        return ""
    initials = parts[0][0] + parts[1][0]
    local_dt = timezone.localtime(sent_at)
    base = f"IMCM/{reg.number}-{initials}/{local_dt:%m-%y}"
    if addendum_number is not None:
        base = f"{base} ДС{addendum_number}"
    return base


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_request(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для отправки."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    selected_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
            "currency",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    try:
        with transaction.atomic():
            create_contract_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
            )
            groups = defaultdict(list)
            for p in selected_performers:
                groups[(p.registration_id, p.executor)].append(p)

            updated = 0
            for (reg_id, executor), group_performers in groups.items():
                batch_id = uuid.uuid4()
                rep = group_performers[0]

                existing_batch_count = (
                    Performer.objects
                    .filter(
                        registration_id=reg_id,
                        executor=executor,
                        contract_batch_id__isnull=False,
                    )
                    .values("contract_batch_id")
                    .distinct()
                    .count()
                )
                is_addendum = existing_batch_count > 0
                addendum_number = existing_batch_count if is_addendum else None

                if is_addendum:
                    first_performer = (
                        Performer.objects
                        .filter(
                            registration_id=reg_id,
                            executor=executor,
                            contract_batch_id__isnull=False,
                            contract_is_addendum=False,
                        )
                        .order_by("contract_sent_at", "id")
                        .first()
                    )
                    base_date = first_performer.contract_sent_at if first_performer else request_sent_at
                else:
                    base_date = request_sent_at

                contract_number = _build_contract_number(rep, base_date, addendum_number)
                update_kwargs = dict(
                    contract_sent_at=request_sent_at,
                    contract_deadline_at=deadline_at,
                    contract_batch_id=batch_id,
                    contract_is_addendum=is_addendum,
                    contract_addendum_number=addendum_number,
                )
                if contract_number:
                    update_kwargs["contract_number"] = contract_number
                group_ids = [p.pk for p in group_performers]
                updated += Performer.objects.filter(pk__in=group_ids).update(**update_kwargs)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def info_request_approval(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для запроса."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    selected_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    try:
        with transaction.atomic():
            create_info_request_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
            )
            updated = Performer.objects.filter(pk__in=performer_ids).update(
                info_request_sent_at=request_sent_at,
                info_request_deadline_at=deadline_at,
                info_approval_status="",
                info_approval_at=None,
            )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
        }
    )


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
        "country_id": work.country_id or "",
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def create_workspace(request):
    from yandexdisk_app.workspace import create_project_workspace

    project_id = request.POST.get("project_id")
    if not project_id:
        return JsonResponse({"ok": False, "error": "Не выбран проект."}, status=400)

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный ID проекта."}, status=400)

    project = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(pk=project_id)
        .first()
    )
    if not project:
        return JsonResponse({"ok": False, "error": "Проект не найден."}, status=404)

    result = create_project_workspace(request.user, project)
    if not result.ok:
        return JsonResponse({"ok": False, "error": result.message}, status=400)

    return JsonResponse({"ok": True, "message": result.message})


@login_required
@user_passes_test(staff_required)
@require_POST
def create_registration_workspace(request):
    from yandexdisk_app.workspace import create_basic_project_workspace_stream, WorkspaceResult

    project_id = request.POST.get("project_id")
    if not project_id:
        return JsonResponse({"ok": False, "error": "Не выбран проект."}, status=400)

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный ID проекта."}, status=400)

    project = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(pk=project_id)
        .first()
    )
    if not project:
        return JsonResponse({"ok": False, "error": "Проект не найден."}, status=404)

    MIN_CHUNK = 256

    def _padded(line):
        """Pad each line to MIN_CHUNK bytes so proxies flush immediately."""
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        for item in create_basic_project_workspace_stream(request.user, project):
            if isinstance(item, WorkspaceResult):
                if item.ok:
                    yield _padded(json.dumps({"ok": True, "message": item.message}) + "\n")
                else:
                    yield _padded(json.dumps({"ok": False, "error": item.message}) + "\n")
            else:
                yield _padded(json.dumps(item) + "\n")

    resp = StreamingHttpResponse(_stream(), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache, no-store"
    resp["X-Accel-Buffering"] = "no"
    return resp


@login_required
@user_passes_test(staff_required)
@require_GET
def workspace_folders_list(request):
    folders = RegistrationWorkspaceFolder.objects.all().values("id", "level", "name", "position")
    return JsonResponse({"folders": list(folders)})


@login_required
@user_passes_test(staff_required)
@require_POST
def workspace_folders_save(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    rows = data.get("folders", [])
    if not isinstance(rows, list):
        return JsonResponse({"ok": False, "error": "Некорректный формат."}, status=400)

    objects = []
    for i, row in enumerate(rows):
        level = row.get("level", 1)
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if level not in (1, 2, 3):
            level = 1
        objects.append(RegistrationWorkspaceFolder(level=level, name=name, position=i))

    with transaction.atomic():
        RegistrationWorkspaceFolder.objects.all().delete()
        RegistrationWorkspaceFolder.objects.bulk_create(objects)

    return JsonResponse({"ok": True})


@login_required
@require_GET
def identifier_for_country(request):
    country_id = request.GET.get("country_id")
    if not country_id:
        return JsonResponse({"identifier": ""})
    lei = (
        LegalEntityIdentifier.objects
        .filter(country_id=country_id)
        .values_list("identifier", flat=True)
        .first()
    )
    return JsonResponse({"identifier": lei or ""})