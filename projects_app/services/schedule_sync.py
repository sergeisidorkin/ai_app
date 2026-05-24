"""Synchronize managed project Gantt tasks with project assets and performers."""

from __future__ import annotations

import copy
from typing import Any


MANAGED_SOURCE_WORK_VOLUME = "work_volume"
MANAGED_SOURCE_PERFORMER = "performer"
MANAGED_SOURCE_CHECKLIST_SECTION = "checklist_section"
MANAGED_SOURCES = {MANAGED_SOURCE_WORK_VOLUME, MANAGED_SOURCE_PERFORMER, MANAGED_SOURCE_CHECKLIST_SECTION}
MANAGED_SCOPE_PRELIMINARY = "preliminary_report"
MANAGED_SCOPE_SOURCE_DATA = "source_data"
PROJECT_ASSET_SYSTEM_KEY = "project_asset"
TEMPLATE_ASSET_SYSTEM_KEY = "preliminary_report_asset"
PRELIMINARY_REPORT_SUBMISSION_SYSTEM_KEY = "preliminary_report_submission"
SECTION_TEMPLATE_META_KEY = "managed_asset_section_templates"
ASSET_TEMPLATE_META_KEY = "managed_asset_task_template"
SECTION_LINK_TEMPLATE_META_KEY = "managed_asset_section_link_templates"
SOURCE_DATA_PROJECT_ASSET_SYSTEM_KEY = "source_data_project_asset"
SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY = "source_data_asset"
SOURCE_DATA_ASSET_TEMPLATE_META_KEY = "managed_source_data_asset_task_template"
SOURCE_DATA_SECTION_TEMPLATE_META_KEY = "managed_source_data_section_templates"
SOURCE_DATA_SECTION_LINK_TEMPLATE_META_KEY = "managed_source_data_section_link_templates"
MANAGED_VALIDATION_SPECIALTY = "__managed_performer__"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _format_executor_display_name(value: Any) -> str:
    normalized = _norm(value)
    parts = normalized.split()
    if len(parts) < 2:
        return normalized
    if "." in parts[1]:
        return f"{parts[0]} {parts[1]}".strip()
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{parts[0]} {initials}".strip()


def _same_executor_value(left: Any, right: Any) -> bool:
    left_norm = _norm(left)
    right_norm = _norm(right)
    return bool(left_norm or right_norm) and (
        left_norm == right_norm
        or _format_executor_display_name(left_norm) == _format_executor_display_name(right_norm)
    )


def _task_id(prefix: str, pk: int | str | None) -> str:
    return f"{prefix}-{pk}"


def _unique_task_id(tasks: list[dict], base: str) -> str:
    existing = {str(task.get("id") or "") for task in tasks}
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def is_managed_task(task: dict | None) -> bool:
    return isinstance(task, dict) and str(task.get("managed_source") or "") in MANAGED_SOURCES


def managed_task_locked_fields(task: dict | None) -> set[str]:
    if not is_managed_task(task):
        return set()
    source = str(task.get("managed_source") or "")
    if source == MANAGED_SOURCE_WORK_VOLUME:
        return {"text", "type", "system_key", "managed_source", "managed_scope", "work_volume_id"}
    if source == MANAGED_SOURCE_PERFORMER:
        return {
            "text",
            "type",
            "executor",
            "specialty",
            "service_section_name",
            "section_name",
            "managed_source",
            "managed_scope",
            "performer_id",
            "work_volume_id",
            "typical_section_id",
            "asset_name",
        }
    if source == MANAGED_SOURCE_CHECKLIST_SECTION:
        return {
            "text",
            "type",
            "executor",
            "specialty",
            "progress",
            "service_section_name",
            "section_name",
            "managed_source",
            "managed_scope",
            "work_volume_id",
            "typical_section_id",
            "asset_name",
        }
    return set()


def _payload_for(reg) -> dict:
    payload = reg.gantt_data if isinstance(getattr(reg, "gantt_data", None), dict) else {}
    payload = copy.deepcopy(payload)
    payload.setdefault("data", [])
    payload.setdefault("links", [])
    payload.setdefault("meta", {})
    if not isinstance(payload["data"], list):
        payload["data"] = []
    if not isinstance(payload["links"], list):
        payload["links"] = []
    if not isinstance(payload["meta"], dict):
        payload["meta"] = {}
    return payload


def _task_key(task: dict) -> str:
    return str(task.get("id") or "")


def _children(tasks: list[dict], parent_id: str) -> list[dict]:
    return [task for task in tasks if str(task.get("parent") or "") == parent_id]


def _strip_template_task(task: dict, *, keep_identity: bool = False) -> dict:
    item = copy.deepcopy(task)
    for key in (
        "$index",
        "$level",
        "$local_index",
        "$open",
        "$rendered_at",
        "$source",
        "$target",
        "managed_source",
        "work_volume_id",
        "performer_id",
        "typical_section_id",
        "template_task_id",
        "asset_name",
        "managed_scope",
    ):
        item.pop(key, None)
    if not keep_identity:
        item.pop("id", None)
        item.pop("parent", None)
    return item


def _find_system_task(tasks: list[dict], system_key: str) -> dict | None:
    return next(
        (
            task
            for task in tasks
            if str(task.get("system_key") or "").strip() == system_key
            and task.get("id") is not None
        ),
        None,
    )


def _find_preliminary_task(tasks: list[dict]) -> dict | None:
    return _find_system_task(tasks, "preliminary_report")


def _apply_preliminary_submission_deadline(payload: dict, registration) -> None:
    task = _find_system_task(payload.get("data") or [], PRELIMINARY_REPORT_SUBMISSION_SYSTEM_KEY)
    if task is None:
        return
    deadline = getattr(registration, "deadline", None)
    if not deadline:
        if task.get("constraint_type") == "mfo":
            task.pop("constraint_type", None)
            task.pop("constraint_date", None)
        return
    deadline_value = deadline.isoformat() if hasattr(deadline, "isoformat") else str(deadline)
    task["constraint_type"] = "mfo"
    task["constraint_date"] = deadline_value


def _find_asset_template(tasks: list[dict], system_key: str = TEMPLATE_ASSET_SYSTEM_KEY) -> dict | None:
    return next(
        (
            task
            for task in tasks
            if str(task.get("system_key") or "").strip() == system_key
            and task.get("id") is not None
        ),
        None,
    )


def _service_section_label(task: dict) -> str:
    return _norm(task.get("service_section_name") or task.get("section_name") or task.get("text"))


def _ensure_templates(
    payload: dict,
    *,
    asset_system_key: str = TEMPLATE_ASSET_SYSTEM_KEY,
    asset_template_meta_key: str = ASSET_TEMPLATE_META_KEY,
    section_template_meta_key: str = SECTION_TEMPLATE_META_KEY,
    link_template_meta_key: str = SECTION_LINK_TEMPLATE_META_KEY,
) -> tuple[dict, list[dict], list[dict]]:
    tasks = payload["data"]
    meta = payload["meta"]
    asset_template = meta.get(asset_template_meta_key)
    if not isinstance(asset_template, dict):
        source_asset = _find_asset_template(tasks, asset_system_key)
        if source_asset:
            asset_template = _strip_template_task(source_asset)
            asset_template["template_task_id"] = str(source_asset.get("id") or "")
        else:
            parent_system_key = "source_data" if asset_system_key == SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY else "preliminary_report"
            preliminary = _find_system_task(tasks, parent_system_key) or {}
            asset_template = {
                "text": "Актив",
                "start_date": preliminary.get("start_date"),
                "end_date": preliminary.get("end_date"),
                "duration": preliminary.get("duration"),
                "progress": 0,
                "type": "project",
                "is_report_bar": True,
            }
        meta[asset_template_meta_key] = copy.deepcopy(asset_template)

    templates = meta.get(section_template_meta_key)
    if not isinstance(templates, list):
        source_asset = _find_asset_template(tasks, asset_system_key)
        source_children = _children(tasks, _task_key(source_asset)) if source_asset else []
        templates = []
        for task in source_children:
            if str(task.get("type") or "").strip() != "service_section":
                continue
            template = _strip_template_task(task, keep_identity=True)
            template["template_task_id"] = str(task.get("id") or "")
            templates.append(template)
        meta[section_template_meta_key] = copy.deepcopy(templates)

    link_templates = meta.get(link_template_meta_key)
    if not isinstance(link_templates, list):
        template_task_ids = {
            _norm(template.get("template_task_id") or template.get("id"))
            for template in templates
            if _norm(template.get("template_task_id") or template.get("id"))
        }
        asset_template_id = _norm(asset_template.get("template_task_id") or asset_template.get("id"))
        source_task_ids = {
            str(task.get("id") or "")
            for task in tasks
            if task.get("id") is not None
        }
        link_templates = []
        for link in payload.get("links") or []:
            if not isinstance(link, dict):
                continue
            source = _norm(link.get("source"))
            target = _norm(link.get("target"))
            if source not in template_task_ids and target not in template_task_ids:
                continue
            item = copy.deepcopy(link)
            item["source"] = source
            item["target"] = target
            if asset_template_id and item["source"] == asset_template_id:
                item["source_is_asset_template"] = True
            if asset_template_id and item["target"] == asset_template_id:
                item["target_is_asset_template"] = True
            item["source_is_section_template"] = source in template_task_ids
            item["target_is_section_template"] = target in template_task_ids
            item["source_exists_in_template"] = source in source_task_ids
            item["target_exists_in_template"] = target in source_task_ids
            link_templates.append(item)
        meta[link_template_meta_key] = copy.deepcopy(link_templates)

    return copy.deepcopy(asset_template), copy.deepcopy(templates), copy.deepcopy(link_templates)


def _managed_scope(task: dict | None) -> str:
    scope = _norm((task or {}).get("managed_scope"))
    return scope or MANAGED_SCOPE_PRELIMINARY


def _asset_subtree_anchor_index(
    tasks: list[dict],
    remove_ids: set[str],
    *,
    template_asset_system_key: str,
    managed_scope: str,
) -> int:
    anchor_index = None
    for index, task in enumerate(tasks):
        if (
            str(task.get("system_key") or "").strip() == template_asset_system_key
            or (
                is_managed_task(task)
                and str(task.get("managed_source") or "") == MANAGED_SOURCE_WORK_VOLUME
                and _managed_scope(task) == managed_scope
            )
        ):
            anchor_index = index
            break
    if anchor_index is None:
        anchor_index = len(tasks)
    return sum(
        1
        for task in tasks[:anchor_index]
        if str(task.get("id") or "") not in remove_ids
    )


def _remove_template_and_managed_tasks(payload: dict) -> dict[str, int]:
    tasks = payload["data"]
    remove_ids = {str(task.get("id")) for task in tasks if is_managed_task(task) and task.get("id") is not None}
    for asset_system_key in (TEMPLATE_ASSET_SYSTEM_KEY, SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY):
        source_asset = _find_asset_template(tasks, asset_system_key)
        if source_asset and source_asset.get("id") is not None:
            source_asset_id = str(source_asset["id"])
            remove_ids.add(source_asset_id)
            pending = {source_asset_id}
            changed = True
            while changed:
                changed = False
                for task in tasks:
                    task_id = str(task.get("id") or "")
                    if task_id and task_id not in remove_ids and str(task.get("parent") or "") in pending:
                        remove_ids.add(task_id)
                        pending.add(task_id)
                        changed = True
    insertion_indices = {
        MANAGED_SCOPE_SOURCE_DATA: _asset_subtree_anchor_index(
            tasks,
            remove_ids,
            template_asset_system_key=SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY,
            managed_scope=MANAGED_SCOPE_SOURCE_DATA,
        ),
        MANAGED_SCOPE_PRELIMINARY: _asset_subtree_anchor_index(
            tasks,
            remove_ids,
            template_asset_system_key=TEMPLATE_ASSET_SYSTEM_KEY,
            managed_scope=MANAGED_SCOPE_PRELIMINARY,
        ),
    }
    payload["data"] = [task for task in tasks if str(task.get("id") or "") not in remove_ids]
    payload["links"] = [
        link
        for link in payload["links"]
        if str(link.get("source") or "") not in remove_ids
        and str(link.get("target") or "") not in remove_ids
    ]
    return insertion_indices


def _section_template_map(templates: list[dict]) -> dict[str, dict]:
    result = {}
    for template in templates:
        label = _service_section_label(template)
        if label and label not in result:
            result[label] = template
    return result


def _preserve_editable_fields(new_task: dict, old_task: dict | None) -> dict:
    if not isinstance(old_task, dict):
        return new_task
    locked = managed_task_locked_fields(new_task)
    never_copy = {"id", "parent", "managed_source", "work_volume_id", "performer_id"}
    for key, value in old_task.items():
        if key in locked or key in never_copy:
            continue
        if key.startswith("$"):
            continue
        new_task[key] = copy.deepcopy(value)
    return new_task


def _section_specialties(section) -> list[str]:
    if not section:
        return []
    return [
        _norm(link.specialty.specialty)
        for link in section.ranked_specialties.select_related("specialty").order_by("rank", "id")
        if _norm(getattr(link.specialty, "specialty", ""))
    ]


def _executor_options_by_label() -> dict[str, list[dict]]:
    from policy_app.views import _typical_service_term_executor_options

    by_label: dict[str, list[dict]] = {}
    for option in _typical_service_term_executor_options():
        label = _norm(option.get("label"))
        if label:
            by_label.setdefault(label, []).append(option)
    return by_label


def _assignment_for_performer(performer, section) -> tuple[str, str]:
    executor_label = _norm(getattr(performer, "executor", ""))
    executor_display = _format_executor_display_name(executor_label)
    section_specialties = _section_specialties(section)
    if not executor_label:
        return "", section_specialties[0] if section_specialties else ""

    options = _executor_options_by_label().get(executor_label, [])
    option = options[0] if len(options) == 1 else None
    if not option:
        return executor_display, section_specialties[0] if section_specialties else ""

    option_specialties = [_norm(value) for value in option.get("specialties", []) if _norm(value)]
    specialty = ""
    for candidate in section_specialties:
        if candidate in option_specialties:
            specialty = candidate
            break
    if not specialty:
        specialty = section_specialties[0] if section_specialties else (option_specialties[0] if option_specialties else "")
    return executor_display, specialty


def _effective_asset_name(work_item) -> str:
    return _norm(getattr(work_item, "asset_name", "") or getattr(work_item, "name", ""))


def _performers_by_work_volume(registration, product_id: int | None) -> dict[int, list]:
    from projects_app.models import Performer

    qs = (
        Performer.objects
        .select_related("work_item", "typical_section", "typical_section__product")
        .filter(registration=registration, typical_section__isnull=False)
        .exclude(typical_section__is_system=True)
        .exclude(typical_section__code__iexact="DSC")
        .order_by("position", "id")
    )
    if product_id:
        qs = qs.filter(typical_section__product_id=product_id)
    grouped: dict[int, list] = {}
    by_asset_name: dict[str, list] = {}
    for performer in qs:
        if performer.work_item_id:
            grouped.setdefault(performer.work_item_id, []).append(performer)
            continue
        asset_name = _norm(performer.asset_name)
        if asset_name:
            by_asset_name.setdefault(asset_name, []).append(performer)

    if by_asset_name:
        work_items = registration.work_items.all()
        for work_item in work_items:
            grouped.setdefault(work_item.pk, []).extend(by_asset_name.get(_effective_asset_name(work_item), []))
    return grouped


def _source_data_sections(registration, product_id: int | None) -> list:
    from checklists_app.models import ChecklistItem

    qs = (
        ChecklistItem.objects
        .select_related("section")
        .filter(project=registration, section__isnull=False)
        .exclude(section__is_system=True)
        .exclude(section__code__iexact="DSC")
        .order_by("section__position", "section_id")
    )
    if product_id:
        qs = qs.filter(section__product_id=product_id)
    sections = []
    seen = set()
    for item in qs:
        section = item.section
        if section.pk in seen:
            continue
        seen.add(section.pk)
        sections.append(section)
    return sections


def _source_data_progress_by_work_volume_section(registration, sections: list) -> dict[tuple[int, int], float]:
    from django.db.models import Count

    from checklists_app.models import ChecklistItem, ChecklistStatus
    from projects_app.models import LegalEntity

    section_ids = [getattr(section, "pk", None) for section in sections if getattr(section, "pk", None)]
    if not section_ids:
        return {}

    item_counts = {
        row["section_id"]: row["total"]
        for row in (
            ChecklistItem.objects
            .filter(project=registration, section_id__in=section_ids)
            .values("section_id")
            .annotate(total=Count("id"))
        )
    }
    legal_entity_counts = {
        row["work_item_id"]: row["total"]
        for row in (
            LegalEntity.objects
            .filter(project=registration, work_item_id__isnull=False)
            .values("work_item_id")
            .annotate(total=Count("id"))
        )
    }
    provided_counts = {
        (row["legal_entity__work_item_id"], row["checklist_item__section_id"]): row["total"]
        for row in (
            ChecklistStatus.objects
            .filter(
                checklist_item__project=registration,
                checklist_item__section_id__in=section_ids,
                legal_entity__project=registration,
                legal_entity__work_item_id__isnull=False,
                status=ChecklistStatus.Status.PROVIDED,
            )
            .values("legal_entity__work_item_id", "checklist_item__section_id")
            .annotate(total=Count("id"))
        )
    }

    progress = {}
    for work_volume_id, legal_count in legal_entity_counts.items():
        for section_id, item_count in item_counts.items():
            total = int(legal_count or 0) * int(item_count or 0)
            provided = int(provided_counts.get((work_volume_id, section_id), 0) or 0)
            progress[(work_volume_id, section_id)] = max(0, min(1, provided / total)) if total else 0
    return progress


def _asset_task_from_template(
    template: dict,
    work_item,
    parent_id: str,
    *,
    scope: str = MANAGED_SCOPE_PRELIMINARY,
) -> dict:
    task = copy.deepcopy(template)
    task["id"] = (
        _task_id("managed-work-volume", work_item.pk)
        if scope == MANAGED_SCOPE_PRELIMINARY
        else f"managed-{scope}-work-volume-{work_item.pk}"
    )
    task["parent"] = parent_id
    task["text"] = _effective_asset_name(work_item) or "Актив"
    task["system_key"] = PROJECT_ASSET_SYSTEM_KEY if scope == MANAGED_SCOPE_PRELIMINARY else SOURCE_DATA_PROJECT_ASSET_SYSTEM_KEY
    task["managed_source"] = MANAGED_SOURCE_WORK_VOLUME
    task["managed_scope"] = scope
    task["work_volume_id"] = work_item.pk
    task["template_task_id"] = str(template.get("template_task_id") or template.get("id") or "")
    task["type"] = "project"
    task["$open"] = True
    task.setdefault("progress", 0)
    return task


def _placeholder_asset_task_from_template(
    template: dict,
    tasks: list[dict],
    parent_id: str,
    *,
    scope: str = MANAGED_SCOPE_PRELIMINARY,
) -> dict:
    task = copy.deepcopy(template)
    system_key = TEMPLATE_ASSET_SYSTEM_KEY if scope == MANAGED_SCOPE_PRELIMINARY else SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY
    task["id"] = _unique_task_id(tasks, system_key)
    task["parent"] = parent_id
    task["text"] = "Актив"
    task["system_key"] = system_key
    task["type"] = "project"
    task["$open"] = True
    task.setdefault("progress", 0)
    for key in ("managed_source", "managed_scope", "work_volume_id", "performer_id", "asset_name"):
        task.pop(key, None)
    return task


def _section_task_from_template(template: dict, performer, asset_task: dict) -> dict:
    section = performer.typical_section
    section_label = _norm(getattr(section, "name_ru", "")) or _service_section_label(template)
    executor, specialty = _assignment_for_performer(performer, section)
    task = copy.deepcopy(template)
    task["id"] = _task_id("managed-performer", performer.pk)
    task["parent"] = asset_task["id"]
    task["text"] = _norm(task.get("text")) or section_label
    task["type"] = "service_section"
    task["service_section_name"] = section_label
    task.pop("section_name", None)
    task["managed_source"] = MANAGED_SOURCE_PERFORMER
    task["managed_scope"] = MANAGED_SCOPE_PRELIMINARY
    task["performer_id"] = performer.pk
    task["work_volume_id"] = asset_task["work_volume_id"]
    task["typical_section_id"] = getattr(section, "pk", None)
    task["asset_name"] = asset_task["text"]
    task["executor"] = executor
    task["specialty"] = specialty
    task["template_task_id"] = str(template.get("template_task_id") or template.get("id") or "")
    task.setdefault("progress", 0)
    return task


def _source_data_section_task_from_template(template: dict, section, asset_task: dict) -> dict:
    section_label = _norm(getattr(section, "name_ru", "")) or _service_section_label(template)
    task = copy.deepcopy(template)
    task["id"] = f"managed-source-data-section-{asset_task['work_volume_id']}-{getattr(section, 'pk', '')}"
    task["parent"] = asset_task["id"]
    task["text"] = _norm(task.get("text")) or section_label
    task["type"] = "service_section"
    task["service_section_name"] = section_label
    task.pop("section_name", None)
    task["managed_source"] = MANAGED_SOURCE_CHECKLIST_SECTION
    task["managed_scope"] = MANAGED_SCOPE_SOURCE_DATA
    task["work_volume_id"] = asset_task["work_volume_id"]
    task["typical_section_id"] = getattr(section, "pk", None)
    task["asset_name"] = asset_task["text"]
    task["executor"] = ""
    task["specialty"] = ""
    task["template_task_id"] = str(template.get("template_task_id") or template.get("id") or "")
    task["progress"] = 0
    return task


def _insert_tasks(payload: dict, index: int, tasks: list[dict]) -> None:
    if not tasks:
        return
    bounded_index = max(0, min(index, len(payload["data"])))
    payload["data"][bounded_index:bounded_index] = tasks


def _build_managed_section_links(
    link_templates: list[dict],
    task_id_map: dict[str, str],
    existing_task_ids: set[str] | None = None,
) -> list[dict]:
    links = []
    seen = set()
    existing_task_ids = existing_task_ids or set()
    for template in link_templates or []:
        if not isinstance(template, dict):
            continue
        source_template_id = _norm(template.get("source"))
        target_template_id = _norm(template.get("target"))
        source = task_id_map.get(source_template_id, source_template_id)
        target = task_id_map.get(target_template_id, target_template_id)
        if not source or not target or source == target:
            continue
        if (
            (template.get("source_is_asset_template") or template.get("source_is_section_template"))
            and source_template_id not in task_id_map
        ):
            continue
        if (
            (template.get("target_is_asset_template") or template.get("target_is_section_template"))
            and target_template_id not in task_id_map
        ):
            continue
        if source_template_id not in task_id_map and source not in existing_task_ids:
            continue
        if target_template_id not in task_id_map and target not in existing_task_ids:
            continue
        key = (
            source,
            target,
            _norm(template.get("type")),
            _norm(template.get("lag")),
            _norm(template.get("lag_mode")),
        )
        if key in seen:
            continue
        seen.add(key)
        link = copy.deepcopy(template)
        for key_to_drop in (
            "id",
            "$source",
            "$target",
            "source_is_asset_template",
            "target_is_asset_template",
            "source_is_section_template",
            "target_is_section_template",
            "source_exists_in_template",
            "target_exists_in_template",
        ):
            link.pop(key_to_drop, None)
        link["id"] = f"managed-link-{source}-{target}-{len(links) + 1}"
        link["source"] = source
        link["target"] = target
        links.append(link)
    return links


def sync_project_gantt_from_sources(registration, *, save: bool = True) -> bool:
    """Reconcile managed Gantt tasks with WorkVolume/Performer rows."""
    if registration is None or not getattr(registration, "pk", None):
        return False
    payload = _payload_for(registration)
    if not payload["data"]:
        return False
    _apply_preliminary_submission_deadline(payload, registration)
    preliminary = _find_preliminary_task(payload["data"])
    source_data = _find_system_task(payload["data"], "source_data")
    if preliminary is None and source_data is None:
        return False

    preliminary_asset_template, preliminary_section_templates, preliminary_link_templates = _ensure_templates(payload)
    source_data_asset_template, source_data_section_templates, source_data_link_templates = _ensure_templates(
        payload,
        asset_system_key=SOURCE_DATA_TEMPLATE_ASSET_SYSTEM_KEY,
        asset_template_meta_key=SOURCE_DATA_ASSET_TEMPLATE_META_KEY,
        section_template_meta_key=SOURCE_DATA_SECTION_TEMPLATE_META_KEY,
        link_template_meta_key=SOURCE_DATA_SECTION_LINK_TEMPLATE_META_KEY,
    )
    work_items = list(registration.work_items.order_by("position", "id"))

    existing_assets = {
        (_managed_scope(task), task.get("work_volume_id")): copy.deepcopy(task)
        for task in payload["data"]
        if is_managed_task(task)
        and str(task.get("managed_source") or "") == MANAGED_SOURCE_WORK_VOLUME
        and task.get("work_volume_id")
    }
    existing_sections = {
        task.get("performer_id"): copy.deepcopy(task)
        for task in payload["data"]
        if is_managed_task(task)
        and str(task.get("managed_source") or "") == MANAGED_SOURCE_PERFORMER
        and task.get("performer_id")
    }
    existing_checklist_sections = {
        (task.get("work_volume_id"), task.get("typical_section_id")): copy.deepcopy(task)
        for task in payload["data"]
        if is_managed_task(task)
        and str(task.get("managed_source") or "") == MANAGED_SOURCE_CHECKLIST_SECTION
        and task.get("work_volume_id")
        and task.get("typical_section_id")
    }
    insertion_indices = _remove_template_and_managed_tasks(payload)
    if not work_items:
        if source_data is not None:
            _insert_tasks(
                payload,
                insertion_indices.get(MANAGED_SCOPE_SOURCE_DATA, len(payload["data"])),
                [
                    _placeholder_asset_task_from_template(
                        source_data_asset_template,
                        payload["data"],
                        str(source_data["id"]),
                        scope=MANAGED_SCOPE_SOURCE_DATA,
                    )
                ],
            )
        if preliminary is not None:
            _insert_tasks(
                payload,
                insertion_indices.get(MANAGED_SCOPE_PRELIMINARY, len(payload["data"])),
                [
                    _placeholder_asset_task_from_template(
                        preliminary_asset_template,
                        payload["data"],
                        str(preliminary["id"]),
                        scope=MANAGED_SCOPE_PRELIMINARY,
                    )
                ],
            )
        registration.gantt_data = payload
        if save:
            registration.__class__.objects.filter(pk=registration.pk).update(gantt_data=payload)
        return True

    preliminary_section_templates_by_label = _section_template_map(preliminary_section_templates)
    source_data_section_templates_by_label = _section_template_map(source_data_section_templates)
    primary_product = registration.primary_product
    product_id = getattr(primary_product, "pk", None) or getattr(getattr(registration, "type", None), "pk", None)
    performers_by_work_volume = _performers_by_work_volume(registration, product_id)
    source_sections = _source_data_sections(registration, product_id)
    source_progress = _source_data_progress_by_work_volume_section(registration, source_sections)

    source_data_tasks = []
    source_data_links = []
    existing_task_ids = {
        str(task.get("id") or "")
        for task in payload["data"]
        if task.get("id") is not None
    }
    if source_data is not None:
        for work_item in work_items:
            asset_task = _asset_task_from_template(
                source_data_asset_template,
                work_item,
                str(source_data["id"]),
                scope=MANAGED_SCOPE_SOURCE_DATA,
            )
            asset_task = _preserve_editable_fields(
                asset_task,
                existing_assets.get((MANAGED_SCOPE_SOURCE_DATA, work_item.pk)),
            )
            source_data_tasks.append(asset_task)
            task_id_map = {str(asset_task.get("template_task_id") or ""): str(asset_task["id"])}
            for section in source_sections:
                section_label = _norm(getattr(section, "name_ru", ""))
                template = source_data_section_templates_by_label.get(section_label)
                if template is None:
                    template = {
                        "text": section_label,
                        "type": "service_section",
                        "service_section_name": section_label,
                        "start_date": asset_task.get("start_date"),
                        "end_date": asset_task.get("end_date"),
                        "duration": asset_task.get("duration"),
                        "progress": 0,
                    }
                section_task = _source_data_section_task_from_template(template, section, asset_task)
                section_task["progress"] = source_progress.get(
                    (work_item.pk, getattr(section, "pk", None)),
                    0,
                )
                section_task = _preserve_editable_fields(
                    section_task,
                    existing_checklist_sections.get((work_item.pk, getattr(section, "pk", None))),
                )
                source_data_tasks.append(section_task)
                if section_task.get("template_task_id"):
                    task_id_map[str(section_task["template_task_id"])] = str(section_task["id"])
            source_data_links.extend(_build_managed_section_links(source_data_link_templates, task_id_map, existing_task_ids))

    preliminary_tasks = []
    preliminary_links = []
    if preliminary is not None:
        for work_item in work_items:
            asset_task = _asset_task_from_template(
                preliminary_asset_template,
                work_item,
                str(preliminary["id"]),
                scope=MANAGED_SCOPE_PRELIMINARY,
            )
            asset_task = _preserve_editable_fields(
                asset_task,
                existing_assets.get((MANAGED_SCOPE_PRELIMINARY, work_item.pk)),
            )
            preliminary_tasks.append(asset_task)
            task_id_map = {str(asset_task.get("template_task_id") or ""): str(asset_task["id"])}
            for performer in performers_by_work_volume.get(work_item.pk, []):
                section = getattr(performer, "typical_section", None)
                section_label = _norm(getattr(section, "name_ru", ""))
                template = preliminary_section_templates_by_label.get(section_label)
                if template is None:
                    template = {
                        "text": section_label,
                        "type": "service_section",
                        "service_section_name": section_label,
                        "start_date": asset_task.get("start_date"),
                        "end_date": asset_task.get("end_date"),
                        "duration": asset_task.get("duration"),
                        "progress": 0,
                    }
                section_task = _section_task_from_template(template, performer, asset_task)
                section_task = _preserve_editable_fields(section_task, existing_sections.get(performer.pk))
                preliminary_tasks.append(section_task)
                if section_task.get("template_task_id"):
                    task_id_map[str(section_task["template_task_id"])] = str(section_task["id"])
            preliminary_links.extend(_build_managed_section_links(preliminary_link_templates, task_id_map, existing_task_ids))

    _insert_tasks(payload, insertion_indices.get(MANAGED_SCOPE_PRELIMINARY, len(payload["data"])), preliminary_tasks)
    _insert_tasks(payload, insertion_indices.get(MANAGED_SCOPE_SOURCE_DATA, len(payload["data"])), source_data_tasks)
    payload["links"].extend(source_data_links)
    payload["links"].extend(preliminary_links)

    registration.gantt_data = payload
    if save:
        registration.__class__.objects.filter(pk=registration.pk).update(gantt_data=payload)
    return True


def sync_project_gantt_by_id(registration_id: int | None) -> bool:
    if not registration_id:
        return False
    from projects_app.models import ProjectRegistration

    registration = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related("product_links__product", "work_items")
        .filter(pk=registration_id)
        .first()
    )
    if registration is None:
        return False
    return sync_project_gantt_from_sources(registration)


def validate_managed_task_changes(existing_payload: dict | None, submitted_payload: dict | None) -> None:
    """Reject manual deletion or editing of fields owned by source tables."""
    if not isinstance(existing_payload, dict) or not isinstance(submitted_payload, dict):
        return
    existing_tasks = {
        str(task.get("id") or ""): task
        for task in existing_payload.get("data") or []
        if is_managed_task(task) and task.get("id") is not None
    }
    if not existing_tasks:
        return
    submitted_tasks = {
        str(task.get("id") or ""): task
        for task in submitted_payload.get("data") or []
        if isinstance(task, dict) and task.get("id") is not None
    }
    missing = [task_id for task_id in existing_tasks if task_id not in submitted_tasks]
    if missing:
        raise ValueError(
            "Управляемые задачи активов и разделов нельзя удалять в Gantt. "
            "Измените строки в таблицах «Объем услуг: активы», «Исполнители» или «Статусы запросов»."
        )
    for task_id, existing in existing_tasks.items():
        submitted = submitted_tasks.get(task_id) or {}
        for field in managed_task_locked_fields(existing):
            if field not in submitted:
                continue
            if field == "executor" and _same_executor_value(submitted.get(field), existing.get(field)):
                continue
            if submitted.get(field) != existing.get(field):
                raise ValueError(
                    "Управляемые поля задач активов и исполнителей нельзя менять в Gantt. "
                    "Измените данные в таблицах «Объем услуг: активы», «Исполнители» или «Статусы запросов»."
                )


def canonicalize_managed_assignments_for_validation(payload: dict | None, registration) -> dict | None:
    if not isinstance(payload, dict) or registration is None:
        return payload
    performer_ids = {
        task.get("performer_id")
        for task in payload.get("data") or []
        if isinstance(task, dict)
        and str(task.get("managed_source") or "") == MANAGED_SOURCE_PERFORMER
        and task.get("performer_id")
    }
    if not performer_ids:
        return payload
    from projects_app.models import Performer

    performers = {
        performer.pk: performer
        for performer in (
            Performer.objects
            .select_related("typical_section")
            .filter(registration=registration, pk__in=performer_ids)
        )
    }
    for task in payload.get("data") or []:
        if not isinstance(task, dict) or str(task.get("managed_source") or "") != MANAGED_SOURCE_PERFORMER:
            continue
        performer = performers.get(task.get("performer_id"))
        if not performer:
            continue
        section = getattr(performer, "typical_section", None)
        section_label = _norm(getattr(section, "name_ru", "")) or _service_section_label(task)
        executor, specialty = _assignment_for_performer(performer, section)
        task["executor"] = executor
        task["specialty"] = specialty
        task["service_section_name"] = section_label
        task["text"] = _norm(task.get("text")) or section_label
    return payload


def sanitize_project_gantt_resources_for_validation(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    tasks = payload.get("data") or []
    tasks_by_id = {
        str(task.get("id")).strip(): task
        for task in tasks
        if isinstance(task, dict) and task.get("id") is not None and str(task.get("id")).strip()
    }
    task_ids = {
        task_id
        for task_id in tasks_by_id
    }
    meta = payload.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("resources"), list):
        return payload

    seen_resource_ids = set()
    resource_id_map = {}
    kept_resource_ids = set()
    resource_task_ids = {}
    sanitized_resources = []
    for index, resource in enumerate(meta.get("resources") or [], start=1):
        if not isinstance(resource, dict):
            continue
        item = copy.deepcopy(resource)
        original_id = _norm(item.get("id")) or f"resource-{index}"
        resource_id = original_id
        suffix = 2
        while resource_id in seen_resource_ids:
            resource_id = f"{original_id}-{suffix}"
            suffix += 1
        seen_resource_ids.add(resource_id)
        if resource_id != original_id:
            resource_id_map[original_id] = resource_id
        item["id"] = resource_id
        specialty = _norm(item.get("specialty"))
        executor = _norm(item.get("executor"))
        if executor and not specialty:
            continue
        item["task_ids"] = []
        for task_id in [_norm(value) for value in (item.get("task_ids") or item.get("taskIds") or [])]:
            if task_id not in task_ids:
                continue
            task = tasks_by_id.get(task_id)
            if not isinstance(task, dict):
                continue
            if executor and _norm(task.get("executor")) != executor:
                continue
            if specialty and _norm(task.get("specialty")) != specialty:
                continue
            item["task_ids"].append(task_id)
        kept_resource_ids.add(resource_id)
        resource_task_ids[resource_id] = set(item["task_ids"])
        sanitized_resources.append(item)

    for task in tasks:
        if not isinstance(task, dict):
            continue
        resource_id = _norm(task.get("resource_id"))
        if resource_id in resource_id_map:
            resource_id = resource_id_map[resource_id]
            task["resource_id"] = resource_id
        task_id = _norm(task.get("id"))
        if resource_id and (
            resource_id not in kept_resource_ids
            or task_id not in resource_task_ids.get(resource_id, set())
        ):
            task.pop("resource_id", None)
            task.pop("resource_name", None)
    meta["resources"] = sanitized_resources
    return payload


def extend_assignment_options_for_managed_tasks(
    payload: dict | None,
    specialty_options: list,
    executor_options: list,
    section_specialties_by_name: dict | None = None,
) -> tuple[list, list]:
    """Allow project-managed performer assignments to pass generic Gantt validation.

    The policy Gantt validates executors against ExpertProfile option values, while
    project-managed tasks intentionally store ``Performer.executor`` as display text.
    """
    specialties = list(specialty_options or [])
    executors = list(executor_options or [])
    specialty_values = {_norm(item) for item in specialties if _norm(item)}
    executors_by_value = {}
    for item in executors:
        if isinstance(item, dict):
            value = _norm(item.get("value") or item.get("id") or item.get("label"))
        else:
            value = _norm(item)
        if value:
            executors_by_value[value] = item

    for task in (payload or {}).get("data") or []:
        if not isinstance(task, dict) or str(task.get("managed_source") or "") != MANAGED_SOURCE_PERFORMER:
            continue
        section_name = _norm(task.get("service_section_name") or task.get("section_name") or task.get("text"))
        section_specialties = [
            _norm(item.get("label") if isinstance(item, dict) else item)
            for item in (section_specialties_by_name or {}).get(section_name, [])
            if _norm(item.get("label") if isinstance(item, dict) else item)
        ]
        if section_name and not section_specialties:
            task["specialty"] = ""
            task["executor"] = ""
            continue
        specialty = _norm(task.get("specialty"))
        executor = _norm(task.get("executor"))
        if executor and not specialty:
            specialty = MANAGED_VALIDATION_SPECIALTY
            task["specialty"] = specialty
        if specialty and specialty not in specialty_values:
            specialties.append(specialty)
            specialty_values.add(specialty)
        if not executor:
            continue
        existing_executor = executors_by_value.get(executor)
        if isinstance(existing_executor, dict):
            current_specialties = existing_executor.setdefault("specialties", [])
            if specialty and specialty not in current_specialties:
                current_specialties.append(specialty)
            continue
        if executor:
            option = {
                "value": executor,
                "label": executor,
                "specialties": [specialty] if specialty else [],
            }
            executors.append(option)
            executors_by_value[executor] = option
    return specialties, executors


def extend_assignment_options_from_project_payload(
    payload: dict | None,
    specialty_options: list,
    executor_options: list,
) -> tuple[list, list]:
    specialties = list(specialty_options or [])
    executors = list(executor_options or [])
    specialty_values = {_norm(item) for item in specialties if _norm(item)}
    executors_by_value = {}
    for item in executors:
        if isinstance(item, dict):
            value = _norm(item.get("value") or item.get("id") or item.get("label"))
        else:
            value = _norm(item)
        if value:
            executors_by_value[value] = item

    def include_pair(specialty, executor):
        specialty = _norm(specialty)
        executor = _norm(executor)
        if not specialty or not executor:
            return
        if specialty not in specialty_values:
            specialties.append(specialty)
            specialty_values.add(specialty)
        existing = executors_by_value.get(executor)
        if isinstance(existing, dict):
            current_specialties = existing.setdefault("specialties", [])
            if specialty not in current_specialties:
                current_specialties.append(specialty)
            return
        option = {"value": executor, "label": executor, "specialties": [specialty]}
        executors.append(option)
        executors_by_value[executor] = option

    for task in (payload or {}).get("data") or []:
        if isinstance(task, dict):
            include_pair(task.get("specialty"), task.get("executor"))
    meta = (payload or {}).get("meta") if isinstance(payload, dict) else {}
    for resource in (meta or {}).get("resources") or []:
        if isinstance(resource, dict):
            include_pair(resource.get("specialty"), resource.get("executor"))
    return specialties, executors
