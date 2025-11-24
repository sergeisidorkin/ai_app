from typing import Optional

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST

from projects_app.models import LegalEntity, Performer, ProjectRegistration
from policy_app.models import TypicalSection
from requests_app.models import RequestItem, RequestTable

from .models import ChecklistCommentHistory, ChecklistRequestNote, ChecklistStatus, ChecklistStatusHistory


def _product_short_label(product) -> str:
    for attr in ("short_name", "short", "code", "name_en", "name"):
        val = getattr(product, attr, None)
        if val:
            return str(val)
    return str(product) if product else ""


def _project_meta(project: Optional[ProjectRegistration], asset_name: Optional[str] = None) -> dict:
    if not project:
        return {"assets": [], "asset": "", "sections": []}

    assets, seen = [], set()
    legal_qs = (
        LegalEntity.objects.filter(project=project)
        .select_related("work_item")
        .order_by("position", "id")
    )
    for entity in legal_qs:
        label = (
            (entity.legal_name or "").strip()
            or (entity.work_name or "").strip()
            or (getattr(entity.work_item, "asset_name", "") or "").strip()
        )
        if label and label not in seen:
            seen.add(label)
            assets.append(label)

    performer_qs = None
    if not assets:
        performer_qs = (
            Performer.objects.filter(registration=project)
            .exclude(asset_name="")
            .select_related("typical_section")
            .order_by("position", "id")
        )
        for perf in performer_qs:
            asset = (perf.asset_name or "").strip()
            if asset and asset not in seen:
                seen.add(asset)
                assets.append(asset)

    selected_asset = asset_name if asset_name in seen else (assets[0] if assets else "")
    sections = []
    if selected_asset:
        if performer_qs is None:
            performer_qs = (
                Performer.objects.filter(registration=project)
                .exclude(asset_name="")
                .select_related("typical_section")
                .order_by("position", "id")
            )
        ids = set()
        for perf in performer_qs:
            if (perf.asset_name or "").strip() != selected_asset:
                continue
            ts = getattr(perf, "typical_section", None)
            if ts and ts.id not in ids:
                ids.add(ts.id)
                sections.append({"id": ts.id, "name": str(ts)})

    return {"assets": assets, "asset": selected_asset, "sections": sections}

def _code_cell_class(status_cells):
    statuses = {
        cell["status"].status
        for cell in status_cells
        if cell.get("status")
    }
    if not statuses:
        return ""
    if statuses == {ChecklistStatus.Status.PROVIDED}:
        return "chk-code--provided"
    if statuses == {ChecklistStatus.Status.PARTIAL}:
        return "chk-code--partial"
    if statuses == {ChecklistStatus.Status.NOT_REQUIRED}:
        return "chk-code--na"
    if ChecklistStatus.Status.PARTIAL in statuses:
        return "chk-code--partial"
    if (
        ChecklistStatus.Status.PROVIDED in statuses
        and ChecklistStatus.Status.MISSING in statuses
    ):
        return "chk-code--partial"
    if (
        ChecklistStatus.Status.PROVIDED in statuses
        and ChecklistStatus.Status.NOT_REQUIRED in statuses
        and len(statuses) == 2
    ):
        return "chk-code--provided"
    return ""


def _project_options():
    regs = ProjectRegistration.objects.select_related("type").order_by("position", "id")
    options = []
    for reg in regs:
        short_uid = (reg.short_uid or "").strip()
        product_short = _product_short_label(getattr(reg, "type", None))
        options.append(
            {
                "id": reg.id,
                "short_uid": short_uid,
                "label": " ".join(x for x in (short_uid, product_short, reg.name) if x),
                "code": short_uid or f"{reg.number}{reg.group}".upper(),
                "product_short": product_short,
                "product_id": getattr(getattr(reg, "type", None), "id", None),
            }
        )
    return options


def _resolve_section(project: ProjectRegistration, section_id: Optional[str], asset_name: Optional[str]):
    if section_id:
        section = TypicalSection.objects.filter(pk=section_id, product=project.type).first()
        if section:
            return section

    meta = _project_meta(project, asset_name)
    first = meta["sections"][0]["id"] if meta["sections"] else None
    if first:
        return TypicalSection.objects.filter(pk=first).first()

    return (
        TypicalSection.objects.filter(product=project.type).order_by("position", "id").first()
        if project.type_id
        else None
    )


def _legal_entities_for(project: ProjectRegistration, asset_name: Optional[str]):
    qs = (
        LegalEntity.objects.filter(project=project)
        .select_related("work_item")
        .order_by("position", "id")
    )
    if asset_name:
        qs = qs.filter(
            Q(work_item__asset_name__iexact=asset_name)
            | Q(work_item__name__iexact=asset_name)
            | Q(legal_name__iexact=asset_name)
        )
    return list(qs)


@require_GET
def panel(request):
    project_options = _project_options()
    selected_project_uid = project_options[0]["short_uid"] if project_options else None
    selected_project = (
        ProjectRegistration.objects.select_related("type").filter(short_uid=selected_project_uid).first()
    )
    meta = _project_meta(selected_project, None) if selected_project else {"assets": [], "asset": "", "sections": []}

    try:
        table_url = reverse("checklists_app:table_partial")
        update_url = reverse("checklists_app:update_status")
        note_url = reverse("checklists_app:update_note")
        meta_url_base = reverse("checklists_app:project_meta", args=["__uid__"])
    except NoReverseMatch:
        table_url = "/checklists/partial/table/"
        update_url = "/checklists/status/update/"
        note_url = "/checklists/note/update/"
        meta_url_base = "/checklists/project-meta/__uid__/"

    return render(
        request,
        "checklists_app/panel.html",
        {
            "project_options": project_options,
            "selected_project_uid": selected_project_uid,
            "asset_options": meta["assets"],
            "selected_asset": meta["asset"],
            "section_options": meta["sections"],
            "table_partial_url": table_url,
            "update_status_url": update_url,
            "update_note_url": note_url,
            "project_meta_url_base": meta_url_base,
        },
    )


@require_GET
def project_meta(request, uid: str):
    project = get_object_or_404(ProjectRegistration.objects.select_related("type"), short_uid=uid)
    asset = (request.GET.get("asset") or "").strip() or None
    return JsonResponse(_project_meta(project, asset))


@require_GET
def table_partial(request):
    project_uid = (request.GET.get("project_uid") or request.GET.get("project") or "").strip()
    asset_name = (request.GET.get("asset") or "").strip()
    section_id = (request.GET.get("section") or "").strip()

    if not project_uid:
        return render(request, "checklists_app/status_table.html", {"project": None})

    project = get_object_or_404(
        ProjectRegistration.objects.select_related("type"),
        short_uid=project_uid,
    )
    if not project.type:
        return render(
            request,
            "checklists_app/status_table.html",
            {"project": project, "section": None, "error": "У проекта не указан тип продукта"},
        )

    section = _resolve_section(project, section_id, asset_name)
    if not section:
        return render(
            request,
            "checklists_app/status_table.html",
            {"project": project, "section": None, "error": "Не удалось определить раздел"},
        )

    table = (
        RequestTable.objects.filter(product=project.type, section=section)
        .prefetch_related("items")
        .first()
    )
    request_items = list(table.items.all()) if table else []
    legal_entities = _legal_entities_for(project, asset_name)

    status_map = {}
    if request_items and legal_entities:
        status_qs = ChecklistStatus.objects.filter(
            request_item__in=[it.id for it in request_items],
            legal_entity__in=[le.id for le in legal_entities],
        ).select_related("request_item", "legal_entity")
        status_map = {(st.request_item_id, st.legal_entity_id): st for st in status_qs}

    note_map = {}
    if request_items:
        note_qs = ChecklistRequestNote.objects.filter(
            request_item__in=[it.id for it in request_items],
            project=project,
            section=section,
            asset_name=asset_name,
        )
        note_map = {note.request_item_id: note for note in note_qs}

    history_map = {}
    if request_items:
        history_qs = (
           ChecklistCommentHistory.objects
           .filter(note__request_item__in=[it.id for it in request_items],
                   note__project=project,
                   note__section=section,
                   note__asset_name=asset_name)
           .select_related("author", "note")
           .order_by("-created_at")
        )
        for entry in history_qs:
           key = entry.note.request_item_id
           history_map.setdefault(key, {"imc_comment": [], "customer_comment": []})
           history_map[key][entry.field].append(entry)

    rows = []
    for item in request_items:
        statuses = [
            {"entity": entity, "status": status_map.get((item.id, entity.id))}
            for entity in legal_entities
        ]
        rows.append(
            {
                "item": item,
                "statuses": statuses,
                "code_class": _code_cell_class(statuses),
                "note": note_map.get(item.id),
                "history": history_map.get(item.id, {"imc_comment": [], "customer_comment": []}),
            }
        )

    context = {
        "project": project,
        "section": section,
        "asset_name": asset_name,
        "legal_entities": legal_entities,
        "rows": rows,
        "status_choices": ChecklistStatus.Status.choices,
        "default_status": ChecklistStatus.Status.MISSING,
        "update_status_url": reverse("checklists_app:update_status"),
        "add_comment_url": reverse("checklists_app:add_comment"),
        "update_note_url": reverse("checklists_app:update_note"),
        "error": None if table else "В разделе «Запросы» нет строк для выбранного продукта/раздела",
    }
    return render(request, "checklists_app/status_table.html", context)

@login_required
@require_POST
def update_status(request):
    request_item_id = request.POST.get("request_item")
    legal_entity_id = request.POST.get("legal_entity")
    status_value = request.POST.get("status")
    asset_name = (request.POST.get("asset_name") or "").strip()

    if not all([request_item_id, legal_entity_id, status_value]):
        return HttpResponseBadRequest("Недостаточно данных.")

    valid_values = {value for value, _ in ChecklistStatus.Status.choices}
    if status_value not in valid_values:
        return HttpResponseBadRequest("Некорректный статус.")

    request_item = get_object_or_404(RequestItem, pk=request_item_id)
    legal_entity = get_object_or_404(LegalEntity, pk=legal_entity_id)

    with transaction.atomic():
        status_obj, created = ChecklistStatus.objects.select_for_update().get_or_create(
            request_item=request_item,
            legal_entity=legal_entity,
            defaults={"updated_by": request.user},
        )
        previous = None if created else status_obj.status
        status_obj.status = status_value
        status_obj.updated_by = request.user
        status_obj.save()

        if previous != status_value:
            ChecklistStatusHistory.objects.create(
                checklist_status=status_obj,
                request_item=request_item,
                legal_entity=legal_entity,
                previous_status=previous or "",
                new_status=status_value,
                changed_by=request.user,
            )

    project = legal_entity.project
    related_entities = _legal_entities_for(project, asset_name or None)
    status_map = {
        st.legal_entity_id: st
        for st in ChecklistStatus.objects.filter(
            request_item=request_item,
            legal_entity__in=[le.id for le in related_entities],
        )
    }
    row_statuses = [
        {"entity": entity, "status": status_map.get(entity.id)}
        for entity in related_entities
    ]
    code_class = _code_cell_class(row_statuses)

    return render(
        request,
        "checklists_app/components/status_cell_fragment.html",
        {
            "request_item": request_item,
            "legal_entity": legal_entity,
            "status": status_obj,
            "status_choices": ChecklistStatus.Status.choices,
            "default_status": ChecklistStatus.Status.MISSING,
            "update_url": reverse("checklists_app:update_status"),
            "code_class": code_class,
            "asset_name": asset_name,
        },
    )

@login_required
@require_POST
def update_note(request):
    field = request.POST.get("field")
    request_item_id = request.POST.get("request_item")
    project_id = request.POST.get("project")
    section_id = request.POST.get("section")
    asset_name = (request.POST.get("asset") or "").strip()
    value = (request.POST.get("value") or "").strip()

    if field not in {"imc_comment", "customer_comment"}:
        return HttpResponseBadRequest("Неизвестное поле.")
    if not all([request_item_id, project_id, section_id]):
        return HttpResponseBadRequest("Недостаточно данных.")

    project = get_object_or_404(ProjectRegistration, pk=project_id)
    section = get_object_or_404(TypicalSection, pk=section_id)
    request_item = get_object_or_404(RequestItem, pk=request_item_id)

    note, _ = ChecklistRequestNote.objects.get_or_create(
        request_item=request_item,
        project=project,
        section=section,
        asset_name=asset_name,
        defaults={"updated_by": request.user},
    )
    setattr(note, field, value)
    note.updated_by = request.user
    note.save(update_fields=[field, "updated_by", "updated_at"])

    return render(
        request,
        "checklists_app/components/comment_cell.html",
        {
            "field": field,
            "request_item": request_item,
            "project": project,
            "section": section,
            "asset_name": asset_name,
            "note": note,
            "note_url": reverse("checklists_app:update_note"),
        },
    )

@login_required
@require_POST
def add_comment(request):
    field = request.POST.get("field")
    request_item_id = request.POST.get("request_item")
    project_id = request.POST.get("project")
    section_id = request.POST.get("section")
    asset_name = (request.POST.get("asset") or "").strip()
    value = (request.POST.get("value") or "").strip()

    if field not in {"imc_comment", "customer_comment"}:
        return HttpResponseBadRequest("Неизвестное поле.")
    if not all([request_item_id, project_id, section_id]):
        return HttpResponseBadRequest("Недостаточно данных.")
    if not value:
        return HttpResponseBadRequest("Введите текст комментария.")

    request_item = get_object_or_404(RequestItem, pk=request_item_id)
    project = get_object_or_404(ProjectRegistration, pk=project_id)
    section = get_object_or_404(TypicalSection, pk=section_id)

    note, _ = ChecklistRequestNote.objects.get_or_create(
        request_item=request_item,
        project=project,
        section=section,
        asset_name=asset_name,
        defaults={"updated_by": request.user},
    )

    if field == "imc_comment":
        note.imc_comment = value
    else:
        note.customer_comment = value
    note.updated_by = request.user
    note.save(update_fields=[field, "updated_by", "updated_at"])

    ChecklistCommentHistory.objects.create(
        note=note,
        field=field,
        text=value,
        author=request.user,
    )

    history_qs = note.comment_history.filter(field=field).select_related("author")
    context = {
        "field": field,
        "request_item": request_item,
        "project": project,
        "section": section,
        "asset_name": asset_name,
        "note": note,
        "histories": history_qs,
        "add_comment_url": reverse("checklists_app:add_comment"),
    }
    # Рендерим ячейку + историю (OOB) в одном ответе
    from django.template.loader import render_to_string
    cell_html = render_to_string("checklists_app/components/comment_cell.html", context, request=request)
    history_html = render_to_string("checklists_app/components/comment_history.html", context, request=request)
    return HttpResponse(cell_html + history_html)