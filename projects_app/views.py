from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db import models, transaction
from django.db.models import Max, Q
from django.db.models.functions import Trim
from django import forms
from django.utils import timezone
from classifiers_app.models import LegalEntityIdentifier, LegalEntityRecord
from .models import ProjectRegistration, WorkVolume, Performer, WorkVolumeItem, LegalEntity, RegistrationWorkspaceFolder, PerformerParticipationSnapshot
from .forms import ProjectRegistrationForm, ContractConditionsForm, WorkVolumeForm, PerformerForm, BootstrapMixin, LegalEntityForm

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from experts_app.models import ExpertProfile
from policy_app.models import TypicalSection
from smtp_app.models import ExternalSMTPAccount
from users_app.models import Employee
from users_app.forms import FREELANCER_LABEL
from notifications_app.services import (
    create_contract_notifications,
    create_info_request_notifications,
    create_participation_notifications,
    normalize_delivery_channels,
)

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
    registrations = ProjectRegistration.objects.select_related("country", "group_member").all()
    work_items = WorkVolume.objects.select_related("project", "project__group_member", "country").all()
    legal_entities = (
        LegalEntity.objects
        .select_related("project", "project__group_member", "work_item", "work_item__project", "country")
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

def _performers_context(user=None):
    active_participation_statuses = ["Не начат", "В работе"]
    performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "typical_section__expertise_direction", "employee", "employee__user", "currency")
        .order_by("position", "id")
    )
    participation_performers = (
        Performer.objects
        .select_related("registration", "registration__type", "typical_section", "typical_section__expertise_direction", "employee", "employee__user")
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
            employee__employment=FREELANCER_LABEL,
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
    user_is_direction_head = False
    has_active_smtp_connection = False
    if user:
        try:
            from policy_app.models import DEPARTMENT_HEAD_GROUP
            user_is_direction_head = getattr(user.employee_profile, "role", "") == DEPARTMENT_HEAD_GROUP
        except Exception:
            pass
        has_active_smtp_connection = ExternalSMTPAccount.objects.filter(
            user=user,
            is_active=True,
            use_for_notifications=True,
        ).exists()

    if user:
        performers = list(performers)
        for p in performers:
            p.executor_locked = _is_executor_locked(user, p)

    if user_is_direction_head:
        from notifications_app.models import NotificationPerformerLink as NPL
        from django.db.models import F
        dh_notified_ids = set(
            NPL.objects
            .filter(
                notification__notification_type="project_participation_confirmation",
                notification__recipient_id=F("performer__employee__user_id"),
            )
            .values_list("performer_id", flat=True)
        )
        dh_department_id = getattr(user.employee_profile, "department_id", None)
        participation_performers = list(participation_performers)
        for p in participation_performers:
            ts_dir = _effective_direction_id(p.typical_section)
            in_dh_direction = bool(ts_dir and ts_dir == dh_department_id)
            p.dh_checkbox_locked = (
                not in_dh_direction
                or (p.employee_id and p.employee.user_id == user.id)
                or p.pk in dh_notified_ids
            )

    if not isinstance(participation_performers, list):
        participation_performers = list(participation_performers)
    from collections import defaultdict
    from types import SimpleNamespace
    snapshot_map = defaultdict(list)
    perf_ids = [p.pk for p in participation_performers]
    if perf_ids:
        for s in (
            PerformerParticipationSnapshot.objects
            .filter(performer_id__in=perf_ids)
            .select_related("employee", "employee__user")
            .order_by("request_sent_at", "id")
        ):
            snapshot_map[s.performer_id].append(s)

    participation_display_rows = []
    for p in participation_performers:
        p.is_snapshot = False
        for snap in snapshot_map.get(p.pk, []):
            row = SimpleNamespace(
                is_snapshot=True,
                registration_id=p.registration_id,
                registration=p.registration,
                executor=snap.executor_name,
                asset_name=p.asset_name,
                typical_section=p.typical_section,
                request_sent_at=snap.request_sent_at,
                deadline_at=snap.deadline_at,
                response_display=snap.get_response_display(),
                response_at=snap.response_at,
                response_status=snap.response_status,
            )
            participation_display_rows.append(row)
        participation_display_rows.append(p)
    def _participation_sort_key(r):
        if r.is_snapshot:
            status_order = 3
        elif not getattr(r, "participation_request_sent_at", None):
            status_order = 0
        elif not getattr(r, "participation_response", ""):
            status_order = 1
        else:
            status_order = 2
        return (
            r.registration_id or 0,
            r.executor or "",
            status_order,
            getattr(r, "asset_name", "") or "",
        )
    participation_display_rows.sort(key=_participation_sort_key)

    return {
        "performers": performers,
        "performer_projects": performer_projects,
        "participation_performers": participation_performers,
        "participation_display_rows": participation_display_rows,
        "participation_projects": participation_projects,
        "participation_request_sent_initial": request_sent_initial,
        "info_request_performers": info_request_performers,
        "info_request_projects": info_request_projects,
        "info_request_sent_initial": request_sent_initial,
        "contract_performers": contract_performers,
        "contract_projects": contract_projects,
        "contract_request_sent_initial": request_sent_initial,
        "user_is_direction_head": user_is_direction_head,
        "has_active_smtp_connection": has_active_smtp_connection,
    }

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

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


def _build_tariff_hours_map():
    from policy_app.models import Tariff
    tariffs = Tariff.objects.select_related("product", "section").all()
    result = {}
    for t in tariffs:
        key = f"{t.product_id}_{t.section_id}"
        result[key] = t.service_hours or 0
    return result


def _build_direction_hourly_rate_map():
    """Base-rate hourly rate per OrgUnit (direction).

    Returns {str(org_unit_id): float(hourly_rate)} from Grades where
    is_base_rate=True, keyed by the grade creator's department.
    """
    from policy_app.models import Grade
    result = {}
    for g in (
        Grade.objects
        .filter(is_base_rate=True, hourly_rate__isnull=False)
        .select_related("created_by__employee_profile")
    ):
        emp = getattr(g.created_by, "employee_profile", None)
        if emp and emp.department_id:
            result[str(emp.department_id)] = float(g.hourly_rate)
    return result


def _performer_form_ctx(form, action: str, performer=None):
    regs = ProjectRegistration.objects.select_related("type", "group_member").order_by("position", "id")

    reg_map = {
        str(r.id): {
            "group": r.group_display,
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
            .select_related("product", "expertise_dir")
            .order_by("position", "id")
        )
        sections_map[str(r.id)] = [
            {
                "id": s.id,
                "label": _typical_section_option_label(s),
                "pricing_method": (s.expertise_dir.pricing_method or "") if s.expertise_dir_id else "",
                "direction_id": s.expertise_direction_id,
            }
            for s in qs
        ]

    executor_grade_map = _build_executor_grade_map()
    living_wage_map = _build_living_wage_map()
    tariff_map = _build_tariff_map()
    tariff_hours_map = _build_tariff_hours_map()
    direction_hourly_rate_map = _build_direction_hourly_rate_map()

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
        "tariff_hours_json": json.dumps(tariff_hours_map, ensure_ascii=False),
        "direction_hourly_rate_json": json.dumps(direction_hourly_rate_map, ensure_ascii=False),
    }

def _render_performers_updated(request):
    resp = render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

def _next_performer_position():
    mx = Performer.objects.aggregate(Max("position")).get("position__max") or 0
    return mx + 1


def _effective_direction_id(typical_section):
    """Return the OrgUnit PK of the expertise direction, or None if absent or 'директорское' (level 1)."""
    if not typical_section:
        return None
    direction = getattr(typical_section, "expertise_direction", None)
    if not direction:
        return None
    if direction.level == 1:
        return None
    return direction.pk


def _is_executor_locked(user, performer):
    """Исполнитель заблокирован:
    - «Руководитель проектов»: если раздел привязан к (не-директорскому) направлению экспертизы.
    - «Руководитель направления»: если раздел НЕ относится к его направлению,
      или если запрос подтверждения отправлен и эксперт ещё не отклонил.
    Директорские направления (OrgUnit.level == 1) считаются отсутствующими.
    """
    try:
        emp = user.employee_profile
    except Exception:
        return False
    ts_direction_id = _effective_direction_id(performer.typical_section)
    if emp.role == "Руководитель проектов":
        if ts_direction_id:
            return True
        if (performer.participation_request_sent_at
                and performer.participation_response != Performer.ParticipationResponse.DECLINED):
            return True
        return False
    if emp.role == "Руководитель направления":
        if not ts_direction_id:
            return True
        if ts_direction_id != emp.department_id:
            return True
        dh_is_executor = performer.employee_id and performer.employee.user_id == user.id
        if dh_is_executor:
            return performer.participation_response == Performer.ParticipationResponse.CONFIRMED
        if (performer.participation_request_sent_at
                and performer.participation_response != Performer.ParticipationResponse.DECLINED):
            return True
        return False
    return False


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
    p = get_object_or_404(Performer.objects.select_related("typical_section", "typical_section__expertise_direction", "employee", "employee__user"), pk=pk)
    executor_locked = _is_executor_locked(request.user, p)

    if request.method == "GET":
        form = PerformerForm(instance=p)
        _bind_dynamic_performer_fields(form, instance=p)
        if executor_locked:
            attrs = form.fields["executor"].widget.attrs
            attrs["readonly"] = True
            attrs["class"] = attrs.get("class", "") + " readonly-field"
        ctx = _performer_form_ctx(form, "edit", performer=p)
        ctx["executor_locked"] = executor_locked
        return render(request, PERF_FORM_TEMPLATE, ctx)

    # POST
    form = PerformerForm(request.POST, instance=p)
    _bind_dynamic_performer_fields(form, data=request.POST, instance=p)

    if not form.is_valid():
        if executor_locked:
            attrs = form.fields["executor"].widget.attrs
            attrs["readonly"] = True
            attrs["class"] = attrs.get("class", "") + " readonly-field"
        ctx = _performer_form_ctx(form, "edit", performer=p)
        ctx["executor_locked"] = executor_locked
        return render(request, PERF_FORM_TEMPLATE, ctx, status=200)

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

    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

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
            notification_result = create_participation_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
                delivery_channels=delivery_channels,
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
            "delivery_channels": list(notification_result["delivery_channels"]),
            "email_delivery": notification_result["email_delivery"],
        }
    )


def _build_contract_number(performer, sent_at, addendum_number=None):
    reg = getattr(performer, "registration", None)
    if not reg or getattr(reg, "group_alpha2", "") != "RU":
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
            all_ids = [p.pk for p in selected_performers]
            updated = Performer.objects.filter(pk__in=all_ids).update(
                contract_sent_at=request_sent_at,
                contract_deadline_at=deadline_at,
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
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

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
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

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


def _get_effective_folders(user):
    """Return (queryset, is_custom) — user-specific if exists, else global (user=None)."""
    user_qs = RegistrationWorkspaceFolder.objects.filter(user=user)
    if user_qs.exists():
        return user_qs, True
    return RegistrationWorkspaceFolder.objects.filter(user__isnull=True), False


@login_required
@user_passes_test(staff_required)
@require_GET
def workspace_folders_list(request):
    qs, is_custom = _get_effective_folders(request.user)
    folders = list(qs.values("id", "level", "name", "position"))
    return JsonResponse({"folders": folders, "is_custom": is_custom})


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

    owner = None if request.user.is_superuser else request.user

    objects = []
    for i, row in enumerate(rows):
        level = row.get("level", 1)
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if level not in (1, 2, 3):
            level = 1
        objects.append(RegistrationWorkspaceFolder(user=owner, level=level, name=name, position=i))

    with transaction.atomic():
        RegistrationWorkspaceFolder.objects.filter(user=owner).delete()
        RegistrationWorkspaceFolder.objects.bulk_create(objects)

    return JsonResponse({"ok": True, "is_custom": owner is not None and len(objects) > 0})


@login_required
@user_passes_test(staff_required)
@require_POST
def workspace_folders_reset(request):
    RegistrationWorkspaceFolder.objects.filter(user=request.user).delete()
    qs, is_custom = _get_effective_folders(request.user)
    folders = list(qs.values("id", "level", "name", "position"))
    return JsonResponse({"ok": True, "folders": folders, "is_custom": is_custom})


@login_required
@user_passes_test(staff_required)
@require_POST
def create_source_data_workspace(request):
    from yandexdisk_app.workspace import create_source_data_workspace_stream, WorkspaceResult

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
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        for item in create_source_data_workspace_stream(request.user, project):
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
def source_data_target_folder_load(request):
    from .models import SourceDataTargetFolder
    from yandexdisk_app.workspace import REGISTRATION_STANDARD_FOLDERS

    qs, _ = _get_effective_folders(request.user)
    options = list(
        qs.filter(level=1)
        .order_by("position")
        .values_list("name", flat=True)
    )
    if not options:
        options = list(REGISTRATION_STANDARD_FOLDERS)

    target = SourceDataTargetFolder.objects.filter(user=request.user).first()
    folder_name = target.folder_name if target else ""

    return JsonResponse({"folder_name": folder_name, "options": options})


@login_required
@user_passes_test(staff_required)
@require_POST
def source_data_target_folder_save(request):
    from .models import SourceDataTargetFolder

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    folder_name = (data.get("folder_name") or "").strip()
    if not folder_name:
        return JsonResponse({"ok": False, "error": "Не указано имя папки."}, status=400)

    SourceDataTargetFolder.objects.update_or_create(
        user=request.user,
        defaults={"folder_name": folder_name},
    )
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(staff_required)
@require_GET
def contract_project_target_folder_load(request):
    from .models import ContractProjectTargetFolder
    from yandexdisk_app.workspace import REGISTRATION_STANDARD_FOLDERS

    qs, _ = _get_effective_folders(request.user)
    options = list(
        qs.filter(level=1)
        .order_by("position")
        .values_list("name", flat=True)
    )
    if not options:
        options = list(REGISTRATION_STANDARD_FOLDERS)

    target = ContractProjectTargetFolder.objects.filter(user=request.user).first()
    folder_name = target.folder_name if target else ""

    return JsonResponse({"folder_name": folder_name, "options": options})


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_project_target_folder_save(request):
    from .models import ContractProjectTargetFolder

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    folder_name = (data.get("folder_name") or "").strip()
    if not folder_name:
        return JsonResponse({"ok": False, "error": "Не указано имя папки."}, status=400)

    ContractProjectTargetFolder.objects.update_or_create(
        user=request.user,
        defaults={"folder_name": folder_name},
    )
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(staff_required)
@require_POST
def create_contract_project(request):
    """Create folders on Yandex.Disk for selected contract performers and
    populate them with .docx files from matching contract templates.

    One folder per unique executor within each project (deduplicated across
    assets / typical sections).  Returns an NDJSON streaming response with
    progress updates.
    """
    import re
    from .models import ContractProjectTargetFolder
    from contracts_app.models import ContractTemplate, ContractVariable
    from contracts_app.variable_resolver import resolve_variables
    from contracts_app.docx_processor import process_template
    from experts_app.models import ExpertProfile
    from group_app.models import GroupMember
    from yandexdisk_app.workspace import _build_project_folder_name, _sanitize
    from yandexdisk_app.models import YandexDiskSelection
    from yandexdisk_app.service import create_folder, list_resources, upload_file, publish_resource

    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки."}, status=400)

    try:
        ids = [int(i) for i in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные ID."}, status=400)

    performers = list(
        Performer.objects
        .filter(pk__in=ids)
        .select_related(
            "registration", "registration__type", "registration__country",
            "typical_section", "employee",
        )
        .order_by("position", "id")
    )
    if not performers:
        return JsonResponse({"ok": False, "error": "Исполнители не найдены."}, status=404)

    selection = YandexDiskSelection.objects.filter(user=request.user).first()
    if not selection or not selection.resource_path:
        return JsonResponse({"ok": False, "error": "Не выбрана папка на Яндекс.Диске."}, status=400)

    target_obj = ContractProjectTargetFolder.objects.filter(user=request.user).first()
    if not target_obj or not target_obj.folder_name:
        return JsonResponse({"ok": False, "error": "Не выбрана целевая папка в настройках."}, status=400)

    disk_root = selection.resource_path.rstrip("/")

    all_templates = list(
        ContractTemplate.objects
        .select_related("product")
        .filter(file__gt="")
    )

    all_variables = list(
        ContractVariable.objects.filter(
            models.Q(is_computed=True)
            | (
                ~models.Q(source_section="")
                & ~models.Q(source_table="")
                & ~models.Q(source_column="")
            )
        )
    )

    expert_cache = {}
    employee_ids = {p.employee_id for p in performers if p.employee_id}
    if employee_ids:
        for ep in ExpertProfile.objects.select_related("country").filter(employee_id__in=employee_ids):
            expert_cache[ep.employee_id] = ep

    def _executor_short(executor_full_name):
        raw = " ".join(str(executor_full_name or "").split())
        if not raw:
            return "Unknown"
        parts = raw.split(" ")
        last_name = parts[0]
        initials = "".join(part[0] for part in parts[1:3] if part)
        return f"{last_name} {initials}".strip()

    def _find_template(perf):
        """Find the best matching ContractTemplate for a Performer row."""
        project = perf.registration
        product = project.type
        if not product:
            return None

        group_member_ids = {project.group_member_id} if project.group_member_id else set()

        expert = expert_cache.get(perf.employee_id) if perf.employee_id else None

        is_self_employed = bool(expert and expert.self_employed)
        expected_contract_type = "smz" if is_self_employed else "gph"

        expected_party = "individual"

        expert_country_name = ""
        if expert and expert.country:
            expert_country_name = expert.country.short_name

        section_code = ""
        if perf.typical_section:
            section_code = perf.typical_section.code or ""

        candidates = []
        for t in all_templates:
            if t.group_member_id and t.group_member_id not in group_member_ids:
                continue
            if t.product_id != product.pk:
                continue
            if t.contract_type != expected_contract_type:
                continue
            if t.party != expected_party:
                continue
            if expert_country_name and t.country_name != expert_country_name:
                continue

            section_match_exact = False
            if t.is_all_sections:
                section_match = True
            else:
                codes_in_template = {
                    entry.get("code", "") for entry in (t.typical_sections_json or [])
                }
                if section_code and section_code in codes_in_template:
                    section_match = True
                    section_match_exact = True
                else:
                    section_match = False

            if not section_match:
                continue

            candidates.append((t, section_match_exact))

        if not candidates:
            return None

        exact = [t for t, exact in candidates if exact]
        if exact:
            candidates = [(t, True) for t in exact]

        def _version_key(item):
            t = item[0]
            try:
                return int(t.version)
            except (ValueError, TypeError):
                return 0

        candidates.sort(key=_version_key, reverse=True)
        return candidates[0][0]

    seen_executors = set()
    unique_entries = []
    executor_to_ids = {}
    executor_to_perfs = {}
    for perf in performers:
        key = (perf.registration_id, perf.executor)
        executor_to_ids.setdefault(key, []).append(perf.pk)
        executor_to_perfs.setdefault(key, []).append(perf)
        if key in seen_executors:
            continue
        seen_executors.add(key)
        unique_entries.append(perf)

    total = len(unique_entries)

    MIN_CHUNK = 256

    def _padded(line):
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        errors = []
        warnings = []
        created_ids = []
        current = 0

        for perf in unique_entries:
            project = perf.registration
            year_str = _sanitize(str(project.year) if project.year else "Без года")
            project_folder = _build_project_folder_name(project)
            target_folder = _sanitize(target_obj.folder_name)
            base_path = f"{disk_root}/{year_str}/{project_folder}/{target_folder}"

            existing = list_resources(request.user, base_path, limit=1000)
            next_number = 0
            for item in existing:
                match = re.match(r"^(\d{3})\s", item.get("name", ""))
                if match:
                    next_number = max(next_number, int(match.group(1)) + 1)

            executor_name = _executor_short(perf.executor)
            folder_name = _sanitize(f"{next_number:03d} {executor_name}")
            folder_path = f"{base_path}/{folder_name}"

            key = (perf.registration_id, perf.executor)
            if not create_folder(request.user, folder_path):
                errors.append(folder_name)
                current += 1
                yield _padded(json.dumps({"current": current, "total": total}) + "\n")
                continue

            created_ids.extend(executor_to_ids[key])

            now_dt = timezone.now()
            reg_id, executor_val = key
            existing_batch_count = (
                Performer.objects
                .filter(
                    registration_id=reg_id,
                    executor=executor_val,
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
                        executor=executor_val,
                        contract_batch_id__isnull=False,
                        contract_is_addendum=False,
                    )
                    .order_by("contract_sent_at", "id")
                    .first()
                )
                base_date = (
                    first_performer.contract_sent_at
                    if first_performer and first_performer.contract_sent_at
                    else now_dt
                )
            else:
                base_date = now_dt

            pre_contract_number = _build_contract_number(perf, base_date, addendum_number)
            perf.contract_number = pre_contract_number

            seen_templates = set()
            all_perfs_for_executor = executor_to_perfs[key]
            unique_section_perfs = {}
            for p in all_perfs_for_executor:
                sec_id = p.typical_section_id
                if sec_id not in unique_section_perfs:
                    unique_section_perfs[sec_id] = p

            for p in unique_section_perfs.values():
                tmpl = _find_template(p)
                if not tmpl:
                    warnings.append(
                        f"Образец шаблона не найден: {executor_name}"
                        + (f" ({p.typical_section.code})" if p.typical_section else "")
                    )
                    continue

                if tmpl.pk in seen_templates:
                    continue
                seen_templates.add(tmpl.pk)

                try:
                    tmpl.file.open("rb")
                    try:
                        file_data = tmpl.file.read()
                    finally:
                        tmpl.file.close()

                    if all_variables:
                        scalars, lists = resolve_variables(
                            perf, all_variables,
                            all_performers=all_perfs_for_executor,
                        )
                        if scalars or lists:
                            file_data = process_template(
                                file_data, scalars,
                                list_replacements=lists or None,
                            )

                    original_name = tmpl.file.name.split("/")[-1]
                    upload_path = f"{folder_path}/{original_name}"
                    if not upload_file(request.user, upload_path, file_data):
                        errors.append(f"Загрузка файла: {original_name} → {folder_name}")
                    else:
                        try:
                            public_url = publish_resource(request.user, upload_path)
                            if public_url:
                                Performer.objects.filter(
                                    pk__in=executor_to_ids[key],
                                ).update(contract_project_link=public_url)
                        except Exception:
                            pass
                except Exception:
                    errors.append(f"Чтение файла: {tmpl.sample_name}")

            batch_id = uuid.uuid4()
            update_kwargs = dict(
                contract_batch_id=batch_id,
                contract_is_addendum=is_addendum,
                contract_addendum_number=addendum_number,
                contract_project_disk_folder=folder_path,
            )
            if pre_contract_number:
                update_kwargs["contract_number"] = pre_contract_number
            Performer.objects.filter(pk__in=executor_to_ids[key]).update(**update_kwargs)

            current += 1
            yield _padded(json.dumps({"current": current, "total": total}) + "\n")

        if created_ids:
            created_set = set(created_ids)
            Performer.objects.filter(pk__in=created_set).update(
                contract_project_created=True,
                contract_project_created_at=timezone.now(),
                contract_date=timezone.now().date(),
            )

        if errors:
            msg = f"Ошибки: {'; '.join(errors)}"
            if warnings:
                msg += f"\nПредупреждения: {'; '.join(warnings)}"
            yield _padded(json.dumps({"ok": False, "error": msg}) + "\n")
        elif warnings:
            yield _padded(json.dumps({
                "ok": True,
                "message": "Проекты договоров созданы.",
                "warnings": warnings,
            }) + "\n")
        else:
            yield _padded(json.dumps({
                "ok": True,
                "message": "Проекты договоров успешно созданы.",
            }) + "\n")

    resp = StreamingHttpResponse(_stream(), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache, no-store"
    resp["X-Accel-Buffering"] = "no"
    return resp


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