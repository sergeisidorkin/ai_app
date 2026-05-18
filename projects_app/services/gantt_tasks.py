"""Operations on the per-project Gantt task list (`ProjectRegistration.gantt_data`).

The "График проекта" table and the Gantt diagram share the same JSON store
(`gantt_data` JSONField). This module keeps reads/writes consistent and
delegates schema-level validation to the same normalization helper used by
the Gantt POST endpoint, so both UIs always see the same shape.
"""
from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from django.db import transaction


CONSTRAINT_CODES = {
    "asap": "ASAP",
    "alap": "ALAP",
    "snet": "SNET",
    "snlt": "SNLT",
    "fnet": "FNET",
    "fnlt": "FNLT",
    "mso": "MSO",
    "mfo": "MFO",
}


# --------------------------------------------------------------------------- #
# Date helpers
# --------------------------------------------------------------------------- #
def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _serialize_date(value: date | None) -> str:
    if not value:
        return ""
    return value.isoformat()


# --------------------------------------------------------------------------- #
# Read path: build flat row dicts for the table view
# --------------------------------------------------------------------------- #
@dataclass
class _ScheduleRow:
    project_id: int
    task_id: str
    row_number: str
    task: str
    start_date: date | None
    end_date: date | None
    specialty: str
    executor: str
    deadline: date | None
    constraint: str
    duration: float | None
    duration_star: float | None
    predecessors: str
    progress: int
    position: int = 0
    parent_id: str = ""
    level: int = 0
    has_children: bool = False

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "row_number": self.row_number,
            "task": self.task,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "specialty": self.specialty,
            "executor": self.executor,
            "deadline": self.deadline,
            "constraint": self.constraint,
            "duration": self.duration,
            "duration_star": self.duration_star,
            "predecessors": self.predecessors,
            "progress": self.progress,
            # `pk` is unused by the new template paths, but we keep the alias
            # so any HTMX/JS that still reads `item.pk` doesn't break.
            "pk": self.task_id,
            "id": self.task_id,
            "parent_id": self.parent_id,
            "level": self.level,
            "has_children": self.has_children,
        }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_constraint(task: dict) -> str:
    raw_type = str(task.get("constraint_type") or "").strip().lower()
    code = CONSTRAINT_CODES.get(raw_type, "")
    if not code:
        return ""
    constraint_date = _parse_iso_date(task.get("constraint_date"))
    if constraint_date:
        return f"{code} {constraint_date.strftime('%d.%m.%Y')}"
    return code


def _wbs_for_tasks(tasks: list[dict]) -> dict[str, str]:
    """Compute a WBS (Work Breakdown Structure) string per task id.

    Tasks are walked in their stored order (mirroring the Gantt rendering).
    Top-level tasks get sequential 1, 2, 3...; children of "1" get 1.1, 1.2.
    """
    children_by_parent: dict[str, list[dict]] = defaultdict(list)
    task_ids = {str(t.get("id")) for t in tasks if t.get("id") is not None}
    for task in tasks:
        if task.get("id") is None:
            continue
        parent = str(task.get("parent") or "").strip()
        if parent in ("", "0", "null", "None") or parent not in task_ids:
            parent = ""
        children_by_parent[parent].append(task)

    wbs_by_id: dict[str, str] = {}

    def walk(parent_key: str, prefix: str) -> None:
        for idx, task in enumerate(children_by_parent.get(parent_key, []), start=1):
            tid = str(task.get("id"))
            number = f"{prefix}{idx}"
            wbs_by_id[tid] = number
            walk(tid, f"{number}.")

    walk("", "")
    return wbs_by_id


def _predecessors_for_tasks(
    links: list[dict], wbs_by_id: dict[str, str]
) -> dict[str, str]:
    by_target: dict[str, list[str]] = defaultdict(list)
    for link in links or []:
        target = str(link.get("target") or "").strip()
        source = str(link.get("source") or "").strip()
        if not target or not source:
            continue
        wbs = wbs_by_id.get(source)
        if wbs:
            by_target[target].append(wbs)
    return {tid: ", ".join(sorted(parts, key=_wbs_sort_key)) for tid, parts in by_target.items()}


def _wbs_sort_key(value: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in value.split("."))


def _executor_labels_by_value() -> dict[str, str]:
    """Map executor value (e.g. ``expert-profile:5``) to its display name.

    Same source as the Gantt lightbox — keeps the table view aligned with
    the diagram's rendering of the Исполнитель field.
    """
    from policy_app.views import _typical_service_term_executor_options
    mapping: dict[str, str] = {}
    for option in _typical_service_term_executor_options():
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or "").strip()
        if value and label:
            mapping[value] = label
    return mapping


def _iter_project_rows(project, executor_labels: dict[str, str] | None = None) -> Iterable[_ScheduleRow]:
    gantt = project.gantt_data if isinstance(project.gantt_data, dict) else {}
    tasks = gantt.get("data") or []
    if not isinstance(tasks, list):
        return
    links = gantt.get("links") or []
    if not isinstance(links, list):
        links = []
    if executor_labels is None:
        executor_labels = _executor_labels_by_value()
    wbs_by_id = _wbs_for_tasks(tasks)
    predecessors_by_id = _predecessors_for_tasks(links, wbs_by_id)

    # Build a parent → ordered children map so we can emit rows in tree
    # (depth-first) order, which keeps every parent immediately followed by
    # its descendants. The collapse/expand JS in the template relies on this.
    task_by_id: dict[str, dict] = {
        str(t.get("id")): t for t in tasks
        if isinstance(t, dict) and t.get("id") is not None
    }

    def _resolved_parent(task: dict) -> str:
        parent = str(task.get("parent") or "").strip()
        if parent in ("", "0", "null", "None") or parent not in task_by_id:
            return ""
        return parent

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        if not isinstance(task, dict) or task.get("id") is None:
            continue
        children_by_parent[_resolved_parent(task)].append(str(task["id"]))

    ordered_ids: list[tuple[str, int]] = []  # (task_id, level)

    def _walk(parent_key: str, level: int) -> None:
        for tid in children_by_parent.get(parent_key, []):
            ordered_ids.append((tid, level))
            _walk(tid, level + 1)

    _walk("", 0)

    for position, (task_id, level) in enumerate(ordered_ids, start=1):
        task = task_by_id[task_id]
        start = _parse_iso_date(task.get("start_date"))
        end = _parse_iso_date(task.get("end_date"))
        duration_star = None
        if start and end:
            duration_star = max((end - start).days, 0)
        executor_raw = str(task.get("executor") or "").strip()
        yield _ScheduleRow(
            project_id=project.pk,
            task_id=task_id,
            row_number=wbs_by_id.get(task_id, ""),
            task=str(task.get("text") or "").strip(),
            start_date=start,
            end_date=end,
            specialty=str(task.get("specialty") or "").strip(),
            executor=executor_labels.get(executor_raw, executor_raw),
            deadline=_parse_iso_date(task.get("deadline")),
            constraint=_format_constraint(task),
            duration=_safe_float(task.get("duration")),
            duration_star=duration_star,
            predecessors=predecessors_by_id.get(task_id, ""),
            progress=max(0, min(100, _safe_int(task.get("progress"), 0))),
            position=position,
            parent_id=_resolved_parent(task),
            level=level,
            has_children=bool(children_by_parent.get(task_id)),
        )


def iter_schedule_rows(projects: Iterable) -> list[dict]:
    """Flat list of row dicts across all given projects, in schedule_projects order."""
    executor_labels = _executor_labels_by_value()
    rows: list[dict] = []
    for project in projects:
        for row in _iter_project_rows(project, executor_labels):
            rows.append(row.as_dict())
    return rows


# --------------------------------------------------------------------------- #
# Write path: mutate `gantt_data["data"]` for a single project
# --------------------------------------------------------------------------- #
def _ensure_payload(reg) -> dict:
    payload = reg.gantt_data if isinstance(reg.gantt_data, dict) else {}
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


def _next_task_id(payload: dict) -> str:
    existing = {str(task.get("id")) for task in payload["data"] if task.get("id") is not None}
    base = "task-" + uuid.uuid4().hex[:10]
    candidate = base
    suffix = 1
    while candidate in existing:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _siblings(payload: dict, task_id: str) -> list[dict]:
    target = next(
        (t for t in payload["data"] if str(t.get("id")) == str(task_id)),
        None,
    )
    if target is None:
        return []
    parent = str(target.get("parent") or "").strip()
    if parent in ("", "0", "null", "None"):
        parent_key = ""
    else:
        parent_key = parent
    siblings = []
    for task in payload["data"]:
        task_parent = str(task.get("parent") or "").strip()
        if task_parent in ("", "0", "null", "None"):
            task_parent_key = ""
        else:
            task_parent_key = task_parent
        if task_parent_key == parent_key:
            siblings.append(task)
    return siblings


def _normalize_predecessors_string(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = [chunk.strip() for chunk in str(value).replace(";", ",").split(",")]
    return [item for item in items if item]


def _resolve_predecessor_to_id(payload: dict, value: str) -> str | None:
    """Map a user-typed predecessor (WBS like "1.2" or task id) to a task id."""
    if not value:
        return None
    # Direct id match wins.
    for task in payload["data"]:
        if str(task.get("id")) == value:
            return str(task.get("id"))
    # Fall back to WBS lookup.
    wbs_by_id = _wbs_for_tasks(payload["data"])
    for tid, wbs in wbs_by_id.items():
        if wbs == value:
            return tid
    return None


def _rebuild_links_for_target(payload: dict, target_id: str, predecessor_ids: list[str]) -> None:
    payload["links"] = [
        link for link in payload["links"]
        if str(link.get("target")) != str(target_id)
    ]
    for source_id in predecessor_ids:
        payload["links"].append({
            "id": f"link-{uuid.uuid4().hex[:10]}",
            "source": str(source_id),
            "target": str(target_id),
            "type": "0",
            "lag_mode": "fixed",
        })


def _save_payload(reg, payload: dict) -> None:
    """Validate via policy_app normalizer (same one the Gantt POST uses) and persist.

    When the project's primary product has no configured executors/specialties yet
    or the Gantt is empty, the strict normalizer raises - in that case we persist
    the raw payload unchanged so the table view can still operate on early-stage
    projects. Either way the JSON shape is identical to what the Gantt UI saves.
    """
    from policy_app.views import (
        _typical_service_term_section_options,
        _typical_service_term_specialty_options,
        _typical_service_term_executor_options,
        _normalize_typical_service_term_gantt_payload,
    )

    primary_product = reg.primary_product
    primary_product_id = (
        getattr(primary_product, "pk", None)
        or getattr(reg.type, "pk", None)
    )
    section_options = (
        _typical_service_term_section_options(primary_product_id)
        if primary_product_id else []
    )
    section_names = [item["label"] for item in section_options]
    section_specialties_by_name = {
        item["label"]: item.get("specialties", []) for item in section_options
    }
    specialty_options = _typical_service_term_specialty_options()
    executor_options = _typical_service_term_executor_options()
    try:
        normalized, _dated_tasks, _base = _normalize_typical_service_term_gantt_payload(
            payload,
            section_names,
            section_specialties_by_name,
            specialty_options,
            executor_options,
        )
        reg.gantt_data = normalized
    except ValueError:
        # Lenient fallback: keep the raw payload (cleared of unknown keys).
        reg.gantt_data = {
            "data": payload.get("data") or [],
            "links": payload.get("links") or [],
            "meta": payload.get("meta") or {},
        }
    reg.save(update_fields=["gantt_data"])


def _apply_task_payload(task: dict, fields: dict) -> dict:
    """Merge a partial task dict into an existing one without dropping unknown keys."""
    for key, value in fields.items():
        if value is None and key in {"deadline", "constraint_date"}:
            task[key] = None
        elif value is None:
            task.pop(key, None)
        else:
            task[key] = value
    return task


# Public API ---------------------------------------------------------------- #
@transaction.atomic
def add_task(reg, fields: dict) -> str:
    """Append a new task. Returns the new task id."""
    payload = _ensure_payload(reg)
    new_id = _next_task_id(payload)
    new_task: dict = {"id": new_id, "parent": 0, "type": "task", "progress": 0}
    predecessors = fields.pop("predecessors", None)
    _apply_task_payload(new_task, fields)
    payload["data"].append(new_task)
    if predecessors is not None:
        ids = [
            _resolve_predecessor_to_id(payload, value)
            for value in _normalize_predecessors_string(predecessors)
        ]
        _rebuild_links_for_target(payload, new_id, [tid for tid in ids if tid])
    _save_payload(reg, payload)
    return new_id


@transaction.atomic
def update_task(reg, task_id: str, fields: dict) -> bool:
    payload = _ensure_payload(reg)
    target = next(
        (t for t in payload["data"] if str(t.get("id")) == str(task_id)),
        None,
    )
    if target is None:
        return False
    from projects_app.services.schedule_sync import managed_task_locked_fields

    for field in managed_task_locked_fields(target):
        fields.pop(field, None)
    predecessors = fields.pop("predecessors", None)
    _apply_task_payload(target, fields)
    if predecessors is not None:
        ids = [
            _resolve_predecessor_to_id(payload, value)
            for value in _normalize_predecessors_string(predecessors)
        ]
        _rebuild_links_for_target(payload, str(task_id), [tid for tid in ids if tid])
    _save_payload(reg, payload)
    return True


@transaction.atomic
def delete_task(reg, task_id: str) -> bool:
    payload = _ensure_payload(reg)
    str_id = str(task_id)
    before = len(payload["data"])
    # Cascade delete children too.
    descendants = {str_id}
    changed = True
    while changed:
        changed = False
        for task in list(payload["data"]):
            parent = str(task.get("parent") or "")
            if parent in descendants and str(task.get("id")) not in descendants:
                descendants.add(str(task.get("id")))
                changed = True
    from projects_app.services.schedule_sync import is_managed_task

    if any(is_managed_task(t) for t in payload["data"] if str(t.get("id")) in descendants):
        return False
    payload["data"] = [t for t in payload["data"] if str(t.get("id")) not in descendants]
    payload["links"] = [
        link for link in payload["links"]
        if str(link.get("source")) not in descendants
        and str(link.get("target")) not in descendants
    ]
    if len(payload["data"]) == before:
        return False
    _save_payload(reg, payload)
    return True


@transaction.atomic
def move_task(reg, task_id: str, direction: str) -> bool:
    payload = _ensure_payload(reg)
    str_id = str(task_id)
    siblings = _siblings(payload, str_id)
    if not siblings:
        return False
    sibling_ids = [str(t.get("id")) for t in siblings]
    if str_id not in sibling_ids:
        return False
    idx = sibling_ids.index(str_id)
    if direction == "up" and idx == 0:
        return False
    if direction == "down" and idx == len(siblings) - 1:
        return False
    swap_with = siblings[idx - 1] if direction == "up" else siblings[idx + 1]
    swap_id = str(swap_with.get("id"))
    # Swap their absolute positions inside payload["data"].
    indices_by_id = {str(t.get("id")): i for i, t in enumerate(payload["data"])}
    i, j = indices_by_id[str_id], indices_by_id[swap_id]
    payload["data"][i], payload["data"][j] = payload["data"][j], payload["data"][i]
    _save_payload(reg, payload)
    return True
