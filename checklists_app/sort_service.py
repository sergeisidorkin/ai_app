import logging
import json
import os
import re
import time
import unicodedata
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Max, Q
from django.utils import timezone

from core.cloud_storage import CloudStorageNotReadyError
from core.dsh_run import DshRunError, run_headless

from yandexdisk_app.workspace import _build_item_folder_name

from .models import (
    ChecklistItem,
    ChecklistSortChunk,
    ChecklistSortProposal,
    ChecklistSortRun,
    ChecklistSortWorkerState,
)
from .sort_parse import (
    _kit_key,
    contains_complete_json_array,
    decorate_dest_rows,
    dest_leaf_name,
    parse_json_proposals,
)
from .sort_validate import (
    SortChunkValidationError,
    build_dest_index,
    dedupe_rows,
    fallback_rows,
    validate_chunk_rows,
)
from .sort_workspace import (
    INVENTORY_NAME,
    LocalInboxError,
    build_requests_markdown,
    cleanup_stale_sort_workspaces,
    create_dest_tree,
    expand_inventory_kit,
    inbox_section_label,
    materialize_inbox_tree,
    materialize_local_inbox,
    parse_inbox_inventory,
    project_sections,
    reset_sort_workspace,
    resolve_inbox_folder,
    resolve_local_inbox_dir,
    section_folder_name,
    workspace_root_for,
    write_inbox_inventory,
    _safe_relpath,
)

logger = logging.getLogger(__name__)


class SortRunConflict(Exception):
    pass


class SortConfigError(Exception):
    pass


STALE_SORT_MESSAGE = "Сортировка не завершилась. Запустите её ещё раз."
WORKER_UNAVAILABLE_MESSAGE = "Worker сортировки недоступен. Запустите сортировку ещё раз."
SORT_SKILL_VERSION = "1.6.0"


def _lease_seconds():
    return max(int(getattr(settings, "DSH_SORT_WORKER_LEASE_SECONDS", 120) or 120), 30)


def _heartbeat_seconds():
    return max(int(getattr(settings, "DSH_SORT_WORKER_HEARTBEAT_SECONDS", 30) or 30), 5)


def _lease_deadline():
    return timezone.now() + timedelta(seconds=_lease_seconds())


def worker_is_alive():
    state = ChecklistSortWorkerState.objects.filter(pk="default").first()
    if state is None or state.heartbeat_at is None:
        return False
    return state.heartbeat_at >= timezone.now() - timedelta(seconds=_lease_seconds() * 2)


def _scoped_sort_runs(qs, *, project=None, section=None, asset_name=None):
    if project is not None:
        qs = qs.filter(project=project)
    if section is not None:
        qs = qs.filter(section=section)
    if asset_name is not None:
        qs = qs.filter(asset_name=(asset_name or "").strip())
    return qs


def reclaim_stale_sort_runs(*, project=None, section=None, asset_name=None):
    if worker_is_alive():
        return 0
    now = timezone.now()
    running = _scoped_sort_runs(
        ChecklistSortRun.objects.filter(status=ChecklistSortRun.Status.RUNNING),
        project=project,
        section=section,
        asset_name=asset_name,
    )
    updated = running.filter(
        Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=now)
    ).update(
        status=ChecklistSortRun.Status.ERROR,
        error_message=STALE_SORT_MESSAGE,
        finished_at=now,
        worker_id="",
        lease_expires_at=None,
    )
    queued = _scoped_sort_runs(
        ChecklistSortRun.objects.filter(status=ChecklistSortRun.Status.QUEUED),
        project=project,
        section=section,
        asset_name=asset_name,
    )
    queued_cutoff = now - timedelta(seconds=max(_lease_seconds() * 2, 300))
    return updated + queued.filter(created_at__lt=queued_cutoff).update(
        status=ChecklistSortRun.Status.ERROR,
        error_message=WORKER_UNAVAILABLE_MESSAGE,
        finished_at=now,
    )


def _dest_section_label(section):
    code = (getattr(section, "code", "") or "").strip()
    name = (
        (getattr(section, "short_name_ru", "") or "").strip()
        or (getattr(section, "name_ru", "") or "").strip()
        or str(section or "")
    )
    if code and name and code.casefold() not in name.casefold():
        return f"{code} {name}"
    return name or code


def _sort_prompt(
    section,
    *,
    scan_all_inbox=False,
    inbox_folder="",
    leftover_kits=None,
    chunk_file="",
    chunk_json="",
):
    dest_label = _dest_section_label(section)
    chosen = (
        f"Раздел dest уже выбран: {dest_label}. "
        "Не спрашивай, какой раздел обрабатывать, и не предлагай варианты GEO/TSF/… "
        "Сразу dry-run только по этому разделу и верни JSON.\n\n"
    )
    leftover = list(leftover_kits or [])
    if chunk_file:
        leftover_block = (
            f"Ниже уже встроено содержимое {chunk_file}. Не открывай файл и не вызывай tools. "
            "Это полный вход текущего прохода версии "
            f"{SORT_SKILL_VERSION}. Верни JSON-объекты только для комплектов, которые "
            "относятся к выбранному разделу; пропущенные комплекты считаются нерелевантными. "
            "Для каждой возвращённой строки повтори id и kit_path без изменений. "
            "Другие комплекты не рассматривай.\n"
            f"<chunk-json>\n{chunk_json}\n</chunk-json>\n"
        )
    elif leftover:
        listed = "\n".join(
            f"- {kit['kit_path']} (files={kit.get('file_count') or 0})"
            for kit in leftover
        )
        leftover_block = (
            "В этом проходе разбери ТОЛЬКО эти комплекты, по одному объекту JSON на каждый:\n"
            f"{listed}\n"
            "Остальные комплекты уже сопоставлены, их не трогай. "
            "Не вызывай find и не обходи всё дерево inbox.\n"
        )
    else:
        leftover_block = ""
    if chunk_file:
        scope = ""
    elif scan_all_inbox:
        scope = (
            f"Типовой раздел dest: {dest_label}.\n"
            "Имена папок inbox не фильтр: обойди ВСЕ каталоги первого уровня inbox, "
            "независимо от названия. Ищи комплекты, которые относятся к этому типовому "
            "разделу (строки requests.md и папки dest этого раздела; кросс-раздел вроде "
            "ИРД→LGL тоже учитывай). Не требуй папку inbox с тем же именем, её может не быть.\n"
        )
    else:
        folder = inbox_folder or dest_label
        scope = f"Начни с inbox/{folder}. Комплекты этого прохода — из этого каталога.\n"
    return (
        "/checklist-file-sort\n\n"
        f"{chosen}"
        "Корень: текущий рабочий каталог.\n"
        "inbox: inbox\n"
        "dest: dest\n"
        "список запросов проверки: requests.md\n"
        f"инвентарь комплектов: {INVENTORY_NAME}\n\n"
        "Режим: только dry-run. Файлы не копировать и не перемещать.\n"
        "Основные данные текущего прохода находятся в chunk JSON. "
        "Не вызывай find по всему дереву и не вставляй полный перечень файлов в ответ. "
        "Не вызывай ls: samples, text_excerpts и files уже даны во входе. "
        "files бери только из входного JSON.\n"
        "Класть можно только в папки dest, для которых есть строка в списке.\n"
        "Выведи только один блок ```json с относящимися к разделу комплектами, "
        "включая review. "
        "Каждый объект должен содержать только id, dest, confidence, action. "
        "kit/files/name/quote сервер восстановит из входа и dest_items. "
        "У review без пункта dest пиши dest = папка раздела. "
        "Нельзя оставлять в JSON только move.\n"
        "Неуверенные — review. высокая + конкретный пункт dest → move; "
        "средняя/низкая + пункт dest → review; "
        "Сопоставляй профессиональные сокращения, русские/английские синонимы и смысл имен файлов, "
        "а не только буквальное совпадение слов. Несколько согласованных имен файлов достаточно "
        "для высокой уверенности, даже если архивы и бинарные файлы не открывались. "
        "Расположение вне одноимённой папки раздела не означает ignore: сравни все комплекты и "
        "не предпочитай слабое совпадение внутри папки более сильному совпадению вне неё. "
        "комплект относится к разделу, но пункт неясен → review, dest = папка раздела, не пункт CODE-NN. "
        "Такие комплекты не опускай. Пункты dest без комплектов в JSON не выдумывай.\n\n"
        f"{leftover_block}"
        f"{scope}"
        f"Комплект = запись {INVENTORY_NAME} (каталог первого уровня или одиночный файл). "
        "Вложенные комплекты внутри сырой папки указывай относительно inbox. Без масок *.\n"
        "/no_think\n"
    )


def lock_sort_scope(project, section, asset_name=""):
    """Hold one row lock for sort start and verify enqueue of the same scope."""
    from projects_app.models import ProjectRegistration

    ProjectRegistration.objects.select_for_update().only("id").get(pk=project.pk)
    list(
        ChecklistSortRun.objects.select_for_update()
        .filter(
            project=project,
            section=section,
            asset_name=(asset_name or "").strip(),
        )
        .order_by("id")
        .only("id")
    )
    list(
        ChecklistSortProposal.objects.select_for_update()
        .filter(
            run__project=project,
            run__section=section,
            run__asset_name=(asset_name or "").strip(),
        )
        .order_by("id")
        .only("id")
    )


def active_run_for(project, section, asset_name):
    reclaim_stale_sort_runs(
        project=project,
        section=section,
        asset_name=asset_name,
    )
    return (
        ChecklistSortRun.objects.filter(
            project=project,
            section=section,
            asset_name=(asset_name or "").strip(),
            status__in=[ChecklistSortRun.Status.QUEUED, ChecklistSortRun.Status.RUNNING],
        )
        .order_by("-id")
        .first()
    )


def active_verify_for(project, section, asset_name):
    from .sort_verify import reclaim_stale_verifies

    reclaim_stale_verifies()
    return (
        ChecklistSortProposal.objects.filter(
            run__project=project,
            run__section=section,
            run__asset_name=(asset_name or "").strip(),
            verify_status__in={"queued", "running"},
        )
        .order_by("id")
        .first()
    )


def latest_run_for(project, section, asset_name):
    return (
        ChecklistSortRun.objects.filter(
            project=project,
            section=section,
            asset_name=(asset_name or "").strip(),
        )
        .order_by("-id")
        .first()
    )


def latest_runs_for_sections(project, section_ids, asset_name):
    ids = [sid for sid in section_ids if sid]
    if not ids:
        return {}
    asset = (asset_name or "").strip()
    latest_ids = (
        ChecklistSortRun.objects.filter(
            project=project,
            section_id__in=ids,
            asset_name=asset,
        )
        .values("section_id")
        .annotate(max_id=Max("id"))
        .values_list("max_id", flat=True)
    )
    runs = (
        ChecklistSortRun.objects.filter(pk__in=latest_ids)
        .select_related("section")
        .prefetch_related("proposals")
    )
    return {run.section_id: run for run in runs}


def section_label(section):
    if section is None:
        return ""
    label = str(section)
    short_ru = getattr(section, "short_name_ru", "") or ""
    if short_ru:
        label = f"{label} {short_ru}"
    return label


def _section_dest_items(project_id, section_id):
    if not project_id or not section_id:
        return []
    items = ChecklistItem.objects.filter(
        project_id=project_id,
        section_id=section_id,
    ).order_by("position", "id")
    return [
        {
            "folder": _build_item_folder_name(item),
            "request_name": item.short_name or "",
            "quote": item.name or "",
        }
        for item in items
    ]


def match_inventory_kits(kits, dest_items, dest_section_folder):
    dest_by_leaf = {}
    for item in dest_items or []:
        folder = str(item.get("folder") or "").strip()
        if not folder:
            continue
        dest_by_leaf[folder.casefold()] = item
    matched = []
    leftover = []
    prefix = str(dest_section_folder or "").strip().strip("/")
    for kit in kits or []:
        kit_path = str(kit.get("kit_path") or "").strip()
        leaf = dest_leaf_name(kit_path)
        item = dest_by_leaf.get(leaf.casefold()) if leaf and kit.get("is_dir") else None
        if item is None:
            leftover.append(kit)
            continue
        dest_path = f"dest/{prefix}/{item['folder']}" if prefix else f"dest/{item['folder']}"
        dest_path = dest_path.replace("//", "/")
        matched.append(
            {
                "kit_path": kit_path,
                "file_count": kit.get("file_count") or 0,
                "dest_path": dest_path,
                "request_name": item.get("request_name") or "",
                "quote": item.get("quote") or "",
                "confidence": "высокая",
                "action": "move",
                "position": 0,
            }
        )
    return matched, leftover


def _chunked(items, size):
    step = max(int(size or 1), 1)
    sequence = list(items or [])
    for index in range(0, len(sequence), step):
        yield sequence[index : index + step]


def renew_sort_lease(run_id, worker_id):
    now = timezone.now()
    renewed = ChecklistSortRun.objects.filter(
        pk=run_id,
        status=ChecklistSortRun.Status.RUNNING,
        worker_id=worker_id,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=_lease_seconds()),
    ) == 1
    if renewed:
        ChecklistSortWorkerState.objects.filter(pk="default", worker_id=worker_id).update(
            heartbeat_at=now,
        )
    return renewed


def owns_sort_lease(run_id, worker_id):
    return ChecklistSortRun.objects.filter(
        pk=run_id,
        status=ChecklistSortRun.Status.RUNNING,
        worker_id=worker_id,
    ).exists()


def claim_sort_run(run_id, worker_id):
    now = timezone.now()
    with transaction.atomic():
        run = ChecklistSortRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.status != ChecklistSortRun.Status.QUEUED:
            return False
        if run.lease_expires_at and run.lease_expires_at >= now and run.worker_id != worker_id:
            return False
        run.status = ChecklistSortRun.Status.RUNNING
        run.started_at = run.started_at or now
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=_lease_seconds())
        run.worker_id = worker_id
        run.finished_at = None
        run.error_message = ""
        run.save(update_fields=[
            "status",
            "started_at",
            "heartbeat_at",
            "lease_expires_at",
            "worker_id",
            "finished_at",
            "error_message",
        ])
    return True


def _chunk_size():
    return max(int(getattr(settings, "DSH_SORT_CHUNK_SIZE", 30) or 30), 1)


def _max_chunk_retries():
    return max(int(getattr(settings, "DSH_SORT_CHUNK_RETRIES", 1) or 1), 0)


def _max_dsh_calls():
    return max(int(getattr(settings, "DSH_SORT_MAX_DSH_CALLS", 500) or 500), 1)


def _write_chunk_artifact(root, chunk, run):
    dest_items = _section_dest_items(run.project_id, run.section_id)
    payload = {
        "schema_version": 1,
        "skill_version": SORT_SKILL_VERSION,
        "run_id": run.id,
        "chunk_id": chunk.id,
        "section": {
            "id": run.section_id,
            "label": _dest_section_label(run.section),
            "folder": section_folder_name(run.project, run.section),
        },
        "dest_items": dest_items,
        "kits": chunk.input_kits,
    }
    chunks_dir = Path(root) / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    path = chunks_dir / f"sort-chunk-{chunk.id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path.relative_to(root).as_posix()


def _update_run_progress(run_id):
    leaf = ChecklistSortChunk.objects.filter(run_id=run_id).exclude(
        status=ChecklistSortChunk.Status.SPLIT
    )
    terminal = leaf.filter(
        status__in=[ChecklistSortChunk.Status.DONE, ChecklistSortChunk.Status.ERROR]
    )
    deterministic = leaf.filter(kind=ChecklistSortChunk.Kind.DETERMINISTIC)
    fallback = leaf.filter(status=ChecklistSortChunk.Status.ERROR)
    values = {
        "chunks_total": leaf.count(),
        "chunks_done": terminal.count(),
        "kits_done": sum(
            len(chunk.input_kits or [])
            for chunk in terminal.only("input_kits")
        ),
        "deterministic_count": sum(
            len(chunk.input_kits or [])
            for chunk in deterministic.only("input_kits")
        ),
        "fallback_count": sum(
            len(chunk.input_kits or [])
            for chunk in fallback.only("input_kits")
        ),
    }
    ChecklistSortRun.objects.filter(pk=run_id).update(**values)
    return values


def _fast_first_max_kits():
    return max(int(getattr(settings, "DSH_SORT_FAST_FIRST_MAX_KITS", 200) or 200), 1)


_REQUEST_ROUTING_STOPWORDS = {
    "данные",
    "документы",
    "информация",
    "описание",
    "проекты",
    "работы",
}


def _request_routing_tokens(values):
    normalized = unicodedata.normalize(
        "NFC",
        " ".join(str(value or "") for value in values),
    ).casefold()
    return {
        token
        for token in re.findall(r"[0-9a-zа-яё]+", normalized)
        if len(token) >= 8 and token not in _REQUEST_ROUTING_STOPWORDS
    }


def _kit_matches_request_name(kit, dest_items):
    kit_tokens = _request_routing_tokens([
        kit.get("kit_path"),
        *(kit.get("samples") or []),
    ])
    return any(
        kit_tokens & _request_routing_tokens([item.get("request_name")])
        for item in dest_items
    )


def _add_request_name_rows(rows, kits, dest_items, section_folder):
    covered = {_kit_key(row.get("kit_path")) for row in rows}
    enriched = list(rows)
    for kit in kits:
        key = _kit_key(kit.get("kit_path"))
        if any(row_key == key or row_key.startswith(key + "/") for row_key in covered):
            continue
        kit_tokens = _request_routing_tokens([
            kit.get("kit_path"),
            *(kit.get("samples") or []),
            *(
                excerpt.get("text", "")
                for excerpt in kit.get("text_excerpts") or []
                if isinstance(excerpt, dict)
            ),
        ])
        candidates = []
        for item in dest_items:
            overlap = kit_tokens & _request_routing_tokens([item.get("request_name")])
            if overlap:
                candidates.append((len(overlap), item))
        if not candidates:
            continue
        candidates.sort(key=lambda value: value[0], reverse=True)
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            continue
        item = candidates[0][1]
        enriched.append({
            "kit_path": str(kit.get("kit_path") or ""),
            "file_count": int(kit.get("file_count") or 0),
            "dest_path": f"dest/{section_folder}/{item['folder']}".replace("//", "/"),
            "request_name": str(item.get("request_name") or ""),
            "quote": str(item.get("quote") or ""),
            "confidence": "высокая",
            "action": "move",
        })
    return enriched


def _expand_primary_section_kits(run, root, kits, dest_items):
    expanded = []

    def append_kit(kit):
        source_depth = len(
            [part for part in str(kit.get("source_path") or "").split("/") if part]
        )
        should_expand = (
            kit.get("is_dir")
            and (
                _kit_matches_section_label(kit, run.section)
                or (
                    (
                        _kit_under_section_label(kit, run.section)
                        or _kit_matches_request_name(kit, dest_items)
                    )
                    and int(kit.get("file_count") or 0) > _max_proposal_files()
                )
            )
            and source_depth < _max_refinement_depth()
        )
        if should_expand:
            children = expand_inventory_kit(root, kit)
            if children:
                for child in children:
                    append_kit(child)
                return
        expanded.append(kit)

    for source_kit in kits:
        append_kit(source_kit)
    return expanded


def plan_sort_chunks(run, root):
    dest_section_folder = section_folder_name(run.project, run.section)
    dest_items = _section_dest_items(run.project_id, run.section_id)
    inventory_path = root / INVENTORY_NAME
    inventory_text = inventory_path.read_text(encoding="utf-8") if inventory_path.is_file() else ""
    kits = _expand_primary_section_kits(
        run,
        root,
        parse_inbox_inventory(inventory_text),
        dest_items,
    )
    matched, leftover = match_inventory_kits(kits, dest_items, dest_section_folder)
    chunks = []
    if matched:
        chunks.append(
            ChecklistSortChunk(
                run=run,
                order_key="000000",
                kind=ChecklistSortChunk.Kind.DETERMINISTIC,
                status=ChecklistSortChunk.Status.DONE,
                attempts=0,
                input_kits=[kit for kit in kits if _kit_key(kit["kit_path"]) in {
                    _kit_key(row["kit_path"]) for row in matched
                }],
                result_rows=matched,
                started_at=timezone.now(),
                finished_at=timezone.now(),
            )
        )
    planned_dsh_chunks = (
        [leftover]
        if leftover and len(leftover) <= _fast_first_max_kits()
        else list(_chunked(leftover, _chunk_size()))
    )
    for index, kit_chunk in enumerate(planned_dsh_chunks, start=1):
        chunks.append(
            ChecklistSortChunk(
                run=run,
                order_key=f"{index:06d}",
                kind=ChecklistSortChunk.Kind.DSH,
                status=ChecklistSortChunk.Status.PENDING,
                input_kits=kit_chunk,
            )
        )
    with transaction.atomic():
        ChecklistSortChunk.objects.bulk_create(chunks)
        ChecklistSortRun.objects.filter(pk=run.pk).update(kits_total=len(kits))
    _update_run_progress(run.pk)
    logger.info(
        "Checklist sort planned run=%s kits=%s deterministic=%s dsh=%s",
        run.pk,
        len(kits),
        len(matched),
        len(leftover),
    )
    return len(kits)


def serialize_run(run):
    if hasattr(run, "_prefetched_objects_cache"):
        run._prefetched_objects_cache.pop("proposals", None)
    now = timezone.now()
    display_status = run.status
    display_error = run.error_message
    if run.status == ChecklistSortRun.Status.RUNNING and (
        run.lease_expires_at is None or run.lease_expires_at < now
    ):
        display_status = ChecklistSortRun.Status.ERROR
        display_error = STALE_SORT_MESSAGE
    elif (
        run.status == ChecklistSortRun.Status.QUEUED
        and run.created_at
        and run.created_at < now - timedelta(seconds=max(_lease_seconds() * 2, 300))
        and not worker_is_alive()
    ):
        display_status = ChecklistSortRun.Status.ERROR
        display_error = WORKER_UNAVAILABLE_MESSAGE
    verify_cutoff = now - timedelta(
        seconds=max(
            (int(getattr(settings, "DSH_VERIFY_TIMEOUT", 180) or 180) * 3) + 300,
            _lease_seconds() * 3,
        )
    )

    def verify_stalled(row):
        return row.verify_status == "running" and (
            (
                row.verify_lease_expires_at is not None
                and row.verify_lease_expires_at < now
            )
            or (
                row.verify_lease_expires_at is None
                and (
                    row.verify_started_at is None
                    or row.verify_started_at < verify_cutoff
                )
            )
        )

    proposals = [
        {
            "id": row.id,
            "proposal_id": row.id,
            "kit_path": row.kit_path,
            "file_count": row.file_count,
            "dest_path": row.dest_path,
            "request_name": row.request_name,
            "quote": row.quote,
            "confidence": row.confidence,
            "action": (row.action or "").strip().lower(),
            "verifying": row.verify_status in {"queued", "running"} and not verify_stalled(row),
            "verify_error": (
                row.verify_error
                if row.verify_status == "error"
                else (
                    "Проверка не завершилась. Нажмите «Проверить» ещё раз."
                    if verify_stalled(row)
                    else ""
                )
            ),
        }
        for row in run.proposals.all()
    ] if run.pk else []
    proposals = decorate_dest_rows(
        proposals,
        _section_dest_items(getattr(run, "project_id", None), getattr(run, "section_id", None)),
        section_folder=_dest_section_label(getattr(run, "section", None)),
    )
    return {
        "id": run.id,
        "status": display_status,
        "stored_status": run.status,
        "error_message": display_error,
        "section_id": run.section_id,
        "section_name": section_label(getattr(run, "section", None)),
        "inbox_section_name": run.inbox_section_name,
        "source_kind": getattr(run, "source_kind", "") or "cloud",
        "local_inbox_path": getattr(run, "local_inbox_path", "") or "",
        "created_at": run.created_at.isoformat() if run.created_at else "",
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "progress": {
            "kits_done": run.kits_done,
            "kits_total": run.kits_total,
            "chunks_done": run.chunks_done,
            "chunks_total": run.chunks_total,
            "deterministic": run.deterministic_count,
            "fallback": run.fallback_count,
        },
        "proposals": proposals,
    }


def _prepare_workspace(run, user, heartbeat=None):
    project = run.project
    section = run.section
    from .views import _ensure_checklist_items

    for typical in project_sections(project):
        _ensure_checklist_items(project, typical)
    _ensure_checklist_items(project, section)

    root = workspace_root_for(run.id)
    inbox_dir = root / "inbox"
    dest_dir = root / "dest"
    cleanup_stale_sort_workspaces(run)
    reset_sort_workspace(root)
    dest_dir.mkdir(parents=True, exist_ok=True)

    (root / "requests.md").write_text(build_requests_markdown(project), encoding="utf-8")
    create_dest_tree(dest_dir, project)
    scan_all_inbox = False
    inbox_folder = ""
    if (run.source_kind or "cloud") == "local":
        source_dir = resolve_local_inbox_dir(run.local_inbox_path, project, section)
        materialize_local_inbox(inbox_dir, source_dir)
        scan_all_inbox = True
        inbox_folder = _dest_section_label(section)
    else:
        source_folder = resolve_inbox_folder(project, section, run.asset_name)
        inbox_folder = inbox_section_label(project, section, source_folder)
        try:
            materialize_inbox_tree(
                inbox_dir,
                user,
                source_folder,
                inbox_folder,
                heartbeat=heartbeat,
            )
        except CloudStorageNotReadyError as exc:
            raise DshRunError(str(exc)) from exc

    scan_root = inbox_dir
    if not scan_all_inbox and inbox_folder:
        nested = inbox_dir / (_safe_relpath(inbox_folder) or Path("."))
        if nested.is_dir():
            scan_root = nested
    write_inbox_inventory(
        root,
        inbox_dir,
        scan_root,
        canonical_folders=[
            item["folder"] for item in _section_dest_items(project.id, section.id)
        ],
        heartbeat=heartbeat,
    )

    run.workspace_path = str(root)
    run.inbox_section_name = inbox_folder
    run.save(update_fields=["workspace_path", "inbox_section_name"])
    return root, {"scan_all_inbox": scan_all_inbox, "inbox_folder": inbox_folder}


def _is_retriable_chunk_error(exc):
    if isinstance(exc, SortChunkValidationError):
        return True
    if not isinstance(exc, DshRunError):
        return False
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "stream",
            "finish_reason",
            "оборвал",
            "не ответил",
            "пустой ответ",
            "timeout",
            "json",
            "connection",
            "transport",
            "соедин",
        )
    )


def _is_splittable_chunk_error(exc):
    if isinstance(exc, SortChunkValidationError):
        return True
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "stream",
            "finish_reason",
            "оборвал",
            "не ответил",
            "пустой ответ",
            "timeout",
            "json",
        )
    )


def _split_chunk(chunk, error_message):
    kits = list(chunk.input_kits or [])
    midpoint = (len(kits) + 1) // 2
    now = timezone.now()
    children = [
        ChecklistSortChunk(
            run_id=chunk.run_id,
            parent=chunk,
            order_key=f"{chunk.order_key}.{index}",
            kind=ChecklistSortChunk.Kind.DSH,
            status=ChecklistSortChunk.Status.PENDING,
            input_kits=part,
        )
        for index, part in enumerate((kits[:midpoint], kits[midpoint:]))
        if part
    ]
    with transaction.atomic():
        locked = ChecklistSortChunk.objects.select_for_update().get(pk=chunk.pk)
        locked.status = ChecklistSortChunk.Status.SPLIT
        locked.error_message = error_message
        locked.finished_at = now
        locked.save(update_fields=["status", "error_message", "finished_at"])
        ChecklistSortChunk.objects.bulk_create(children)


def _finish_chunk_error(chunk, error_message, started_monotonic):
    rows = fallback_rows(
        chunk.input_kits or [],
        section_folder_name(chunk.run.project, chunk.run.section),
    )
    ChecklistSortChunk.objects.filter(pk=chunk.pk).update(
        status=ChecklistSortChunk.Status.ERROR,
        result_rows=rows,
        error_message=error_message,
        finished_at=timezone.now(),
        duration_ms=max(int((time.monotonic() - started_monotonic) * 1000), 0),
    )


def _max_proposal_files():
    return max(int(getattr(settings, "DSH_SORT_MAX_PROPOSAL_FILES", 100) or 100), 1)


def _max_refinement_depth():
    return max(int(getattr(settings, "DSH_SORT_MAX_REFINEMENT_DEPTH", 4) or 4), 1)


def _normalized_section_label(value, section):
    normalized = unicodedata.normalize("NFC", str(value or "")).casefold().strip()
    normalized = re.sub(r"^\d+\s+", "", normalized)
    code = unicodedata.normalize(
        "NFC",
        str(getattr(section, "code", "") or ""),
    ).casefold().strip()
    if code and normalized.startswith(code + " "):
        normalized = normalized[len(code):].strip()
    return re.sub(r"\s+", " ", normalized)


def _kit_under_section_label(kit, section):
    first = str(kit.get("kit_path") or "").strip("/").split("/", 1)[0]
    if not first:
        return False
    source = _normalized_section_label(first, section)
    labels = {
        _normalized_section_label(getattr(section, "short_name_ru", ""), section),
        _normalized_section_label(getattr(section, "name_ru", ""), section),
        _normalized_section_label(_dest_section_label(section), section),
    }
    return bool(source and source in {label for label in labels if label})


def _kit_matches_section_label(kit, section):
    path = str(kit.get("kit_path") or "").strip("/")
    return "/" not in path and _kit_under_section_label(kit, section)


def _add_section_review_rows(rows, kits, section, section_folder):
    covered = {_kit_key(row.get("kit_path")) for row in rows}
    enriched = list(rows)
    for kit in kits:
        key = _kit_key(kit.get("kit_path"))
        if any(row_key == key or row_key.startswith(key + "/") for row_key in covered):
            continue
        if not _kit_under_section_label(kit, section):
            continue
        enriched.append({
            "kit_path": str(kit.get("kit_path") or ""),
            "file_count": int(kit.get("file_count") or 0),
            "dest_path": f"dest/{section_folder}".replace("//", "/"),
            "request_name": "",
            "quote": "",
            "confidence": "низкая",
            "action": "review",
        })
    return enriched


def _refine_large_chunk_results(
    chunk,
    rows,
    output,
    root,
    worker_id,
    started_monotonic,
):
    rows_by_key = {_kit_key(row.get("kit_path")): row for row in rows}
    refinements = []
    blocked_keys = set()
    for kit in chunk.input_kits or []:
        key = _kit_key(kit.get("kit_path"))
        if not kit.get("is_dir") or int(kit.get("file_count") or 0) <= _max_proposal_files():
            continue
        row = rows_by_key.get(key)
        deterministic_relevance = _kit_under_section_label(kit, chunk.run.section)
        model_move = row is not None and str(row.get("action") or "").casefold() == "move"
        if not deterministic_relevance and not model_move:
            if row is not None:
                blocked_keys.add(key)
            continue
        source_depth = len(
            [part for part in str(kit.get("source_path") or "").split("/") if part]
        )
        children = []
        if source_depth < _max_refinement_depth():
            children = expand_inventory_kit(
                root,
                kit,
                heartbeat=lambda: renew_sort_lease(chunk.run_id, worker_id),
            )
        if children:
            refinements.append((key, kit, children))
        else:
            blocked_keys.add(key)

    if not refinements and not blocked_keys:
        return False

    refined_keys = {key for key, _, _ in refinements}
    removed_keys = refined_keys | blocked_keys
    retained_inputs = [
        kit
        for kit in chunk.input_kits or []
        if _kit_key(kit.get("kit_path")) not in refined_keys
    ]
    retained_rows = [
        row
        for row in rows
        if _kit_key(row.get("kit_path")) not in removed_keys
    ]
    children_to_process = [
        child
        for _, _, children in refinements
        for child in children
    ]
    replacement_chunks = []
    suffix = 0
    if retained_inputs:
        replacement_chunks.append(
            ChecklistSortChunk(
                run_id=chunk.run_id,
                parent_id=chunk.id,
                order_key=f"{chunk.order_key}.r{suffix:03d}",
                kind=ChecklistSortChunk.Kind.DSH,
                status=ChecklistSortChunk.Status.DONE,
                input_kits=retained_inputs,
                result_rows=retained_rows,
                started_at=timezone.now(),
                finished_at=timezone.now(),
            )
        )
        suffix += 1
    for refined_chunk in _chunked(children_to_process, _chunk_size()):
        replacement_chunks.append(
            ChecklistSortChunk(
                run_id=chunk.run_id,
                parent_id=chunk.id,
                order_key=f"{chunk.order_key}.r{suffix:03d}",
                kind=ChecklistSortChunk.Kind.DSH,
                status=ChecklistSortChunk.Status.PENDING,
                input_kits=refined_chunk,
            )
        )
        suffix += 1

    delta = sum(len(children) - 1 for _, _, children in refinements)
    now = timezone.now()
    with transaction.atomic():
        locked = ChecklistSortChunk.objects.select_for_update().get(pk=chunk.pk)
        run = ChecklistSortRun.objects.select_for_update().get(pk=chunk.run_id)
        if (
            locked.status != ChecklistSortChunk.Status.RUNNING
            or run.status != ChecklistSortRun.Status.RUNNING
            or run.worker_id != worker_id
        ):
            return False
        locked.status = ChecklistSortChunk.Status.SPLIT
        locked.result_rows = []
        locked.raw_response = output
        locked.error_message = (
            f"Детализация крупных комплектов: {len(refinements)}; "
            f"широких результатов отброшено: {len(blocked_keys)}."
        )
        locked.finished_at = now
        locked.duration_ms = max(int((time.monotonic() - started_monotonic) * 1000), 0)
        locked.save(update_fields=[
            "status",
            "result_rows",
            "raw_response",
            "error_message",
            "finished_at",
            "duration_ms",
        ])
        ChecklistSortChunk.objects.bulk_create(replacement_chunks)
        if delta:
            run.kits_total += delta
            run.save(update_fields=["kits_total"])
    logger.info(
        "Checklist sort refined broad results run=%s chunk=%s broad=%s children=%s blocked=%s",
        chunk.run_id,
        chunk.id,
        len(refinements),
        len(children_to_process),
        len(blocked_keys),
    )
    return True


def execute_sort_chunk(chunk_id, worker_id):
    now = timezone.now()
    with transaction.atomic():
        chunk = (
            ChecklistSortChunk.objects.select_for_update()
            .select_related("run", "run__project", "run__section")
            .get(pk=chunk_id)
        )
        if chunk.status != ChecklistSortChunk.Status.PENDING:
            return False
        if chunk.run.status != ChecklistSortRun.Status.RUNNING or chunk.run.worker_id != worker_id:
            return False
        chunk.status = ChecklistSortChunk.Status.RUNNING
        chunk.attempts += 1
        chunk.started_at = now
        chunk.finished_at = None
        chunk.error_message = ""
        chunk.save(update_fields=[
            "status",
            "attempts",
            "started_at",
            "finished_at",
            "error_message",
        ])
    run = chunk.run
    root = Path(run.workspace_path)
    started_monotonic = time.monotonic()
    try:
        if sum(
            value or 0
            for value in ChecklistSortChunk.objects.filter(run=run).values_list("attempts", flat=True)
        ) > _max_dsh_calls():
            raise DshRunError("Превышен лимит вызовов DSH для одного прогона.")
        artifact = _write_chunk_artifact(root, chunk, run)
        chunk_json = (Path(root) / artifact).read_text(encoding="utf-8")
        output = run_headless(
            _sort_prompt(
                run.section,
                chunk_file=artifact,
                chunk_json=chunk_json,
                leftover_kits=chunk.input_kits,
            ),
            cwd=root,
            heartbeat=lambda: renew_sort_lease(run.id, worker_id),
            heartbeat_interval=_heartbeat_seconds(),
        )
        if output.count("```") % 2:
            raise SortChunkValidationError("DSH вернул незакрытый JSON fence.")
        if not contains_complete_json_array(output):
            raise SortChunkValidationError("DSH не вернул целый JSON-массив.")
        parsed = parse_json_proposals(output)
        dest_items = _section_dest_items(run.project_id, run.section_id)
        dest_section_folder = section_folder_name(run.project, run.section)
        rows = validate_chunk_rows(
            parsed,
            chunk.input_kits,
            dest_index=build_dest_index(run.project),
            section_folder=dest_section_folder,
            require_complete=False,
        )
        rows = _add_request_name_rows(
            rows,
            chunk.input_kits,
            dest_items,
            dest_section_folder,
        )
        rows = _add_section_review_rows(
            rows,
            chunk.input_kits,
            run.section,
            dest_section_folder,
        )
        if not renew_sort_lease(run.id, worker_id):
            logger.warning(
                "Checklist sort chunk result discarded after lease loss run=%s chunk=%s",
                run.id,
                chunk.id,
            )
            return False
        if _refine_large_chunk_results(
            chunk,
            rows,
            output,
            root,
            worker_id,
            started_monotonic,
        ):
            return True
        ChecklistSortChunk.objects.filter(pk=chunk.pk).update(
            status=ChecklistSortChunk.Status.DONE,
            result_rows=rows,
            raw_response=output,
            error_message="",
            finished_at=timezone.now(),
            duration_ms=max(int((time.monotonic() - started_monotonic) * 1000), 0),
        )
        logger.info(
            "Checklist sort chunk done run=%s chunk=%s attempt=%s kits=%s duration_ms=%s",
            run.id,
            chunk.id,
            chunk.attempts,
            len(chunk.input_kits or []),
            max(int((time.monotonic() - started_monotonic) * 1000), 0),
        )
    except Exception as exc:
        if not owns_sort_lease(run.id, worker_id):
            logger.warning(
                "Checklist sort chunk error discarded after lease loss run=%s chunk=%s",
                run.id,
                chunk.id,
            )
            return False
        error_message = str(exc)
        retriable = _is_retriable_chunk_error(exc)
        is_fast_first = (
            chunk.parent_id is None
            and len(chunk.input_kits or []) > _chunk_size()
        )
        if retriable and not is_fast_first and chunk.attempts <= _max_chunk_retries():
            ChecklistSortChunk.objects.filter(pk=chunk.pk).update(
                status=ChecklistSortChunk.Status.PENDING,
                error_message=error_message,
                duration_ms=max(int((time.monotonic() - started_monotonic) * 1000), 0),
            )
        elif (
            retriable
            and len(chunk.input_kits or []) > 1
            and _is_splittable_chunk_error(exc)
        ):
            _split_chunk(chunk, error_message)
        elif retriable:
            _finish_chunk_error(chunk, error_message, started_monotonic)
        else:
            ChecklistSortChunk.objects.filter(pk=chunk.pk).update(
                status=ChecklistSortChunk.Status.ERROR,
                error_message=error_message,
                finished_at=timezone.now(),
                duration_ms=max(int((time.monotonic() - started_monotonic) * 1000), 0),
            )
            raise
        logger.warning(
            "Checklist sort chunk failed run=%s chunk=%s attempt=%s retriable=%s error=%s",
            run.id,
            chunk.id,
            chunk.attempts,
            retriable,
            error_message,
        )
    finally:
        renew_sort_lease(run.id, worker_id)
        _update_run_progress(run.id)
    return True


def finalize_sort_run(run_id, worker_id):
    leaf_chunks = list(
        ChecklistSortChunk.objects.filter(run_id=run_id)
        .exclude(status=ChecklistSortChunk.Status.SPLIT)
        .order_by("order_key", "id")
    )
    if any(
        chunk.status in {ChecklistSortChunk.Status.PENDING, ChecklistSortChunk.Status.RUNNING}
        for chunk in leaf_chunks
    ):
        return False
    rows = []
    raw_parts = []
    errors = []
    for chunk in leaf_chunks:
        for row in chunk.result_rows or []:
            payload = dict(row)
            payload["_chunk_id"] = chunk.id
            rows.append(payload)
        if chunk.raw_response:
            raw_parts.append(f"--- chunk {chunk.id} ---\n{chunk.raw_response}")
        if chunk.status == ChecklistSortChunk.Status.ERROR:
            errors.append(chunk.error_message or f"Чанк {chunk.id} завершился с ошибкой.")
    rows = dedupe_rows(rows)
    now = timezone.now()
    with transaction.atomic():
        run = ChecklistSortRun.objects.select_for_update().get(pk=run_id)
        if run.status != ChecklistSortRun.Status.RUNNING or run.worker_id != worker_id:
            return False
        ChecklistSortProposal.objects.filter(run=run).delete()
        ChecklistSortProposal.objects.bulk_create(
            [
                ChecklistSortProposal(
                    run=run,
                    chunk_id=row.pop("_chunk_id", None),
                    kit_key=_kit_key(row["kit_path"]),
                    kit_path=row["kit_path"],
                    file_count=min(int(row["file_count"] or 0), 2147483647),
                    dest_path=row["dest_path"],
                    request_name=row["request_name"],
                    quote=row["quote"],
                    confidence=row["confidence"],
                    action=row["action"],
                    position=row["position"],
                )
                for row in rows
            ]
        )
        run.raw_response = "\n\n".join(raw_parts)
        run.status = ChecklistSortRun.Status.PARTIAL if errors else ChecklistSortRun.Status.DONE
        run.error_message = (
            f"{len(errors)} чанков завершились с ошибкой. "
            "Проблемные комплекты оставлены для ручной проверки. "
            f"Последняя ошибка: {errors[-1]}"
            if errors
            else ""
        )
        run.finished_at = now
        run.heartbeat_at = now
        run.lease_expires_at = None
        run.worker_id = ""
        run.save(update_fields=[
            "raw_response",
            "status",
            "error_message",
            "finished_at",
            "heartbeat_at",
            "lease_expires_at",
            "worker_id",
        ])
    _update_run_progress(run_id)
    logger.info(
        "Checklist sort finalized run=%s status=%s proposals=%s failed_chunks=%s",
        run_id,
        run.status,
        len(rows),
        len(errors),
    )
    return True


def fail_sort_run(run_id, worker_id, exc):
    logger.exception("Checklist sort run %s failed", run_id)
    now = timezone.now()
    ChecklistSortRun.objects.filter(
        pk=run_id,
        status=ChecklistSortRun.Status.RUNNING,
        worker_id=worker_id,
    ).update(
        status=ChecklistSortRun.Status.ERROR,
        error_message=str(exc),
        finished_at=now,
        heartbeat_at=now,
        lease_expires_at=None,
        worker_id="",
    )


def process_sort_step(run_id, worker_id, user=None):
    run = (
        ChecklistSortRun.objects.select_related("project", "section", "started_by")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        return False
    if run.status == ChecklistSortRun.Status.QUEUED:
        if not claim_sort_run(run_id, worker_id):
            return False
        run.refresh_from_db()
    if run.status != ChecklistSortRun.Status.RUNNING or run.worker_id != worker_id:
        return False
    if user is None:
        user = run.started_by
    try:
        renew_sort_lease(run.id, worker_id)
        if not run.chunks.exists():
            root, _ = _prepare_workspace(
                run,
                user,
                heartbeat=lambda: renew_sort_lease(run.id, worker_id),
            )
            if not renew_sort_lease(run.id, worker_id):
                return False
            plan_sort_chunks(run, root)
        pending = run.chunks.filter(status=ChecklistSortChunk.Status.PENDING).order_by(
            "order_key", "id"
        ).first()
        if pending is not None:
            execute_sort_chunk(pending.id, worker_id)
        has_running = run.chunks.filter(
            status=ChecklistSortChunk.Status.RUNNING
        ).exists()
        if has_running:
            return False
        if not run.chunks.filter(
            status__in=[ChecklistSortChunk.Status.PENDING, ChecklistSortChunk.Status.RUNNING]
        ).exists():
            finalize_sort_run(run.id, worker_id)
        return True
    except Exception as exc:
        fail_sort_run(run.id, worker_id, exc)
        return True


def execute_sort_run(run_id, user=None, *, close_connections=False, worker_id=None):
    identity = worker_id or f"inline:{os.getpid()}"
    if close_connections:
        close_old_connections()
    processed = False
    try:
        while True:
            run = ChecklistSortRun.objects.filter(pk=run_id).only("status").first()
            if run is None or run.status in {
                ChecklistSortRun.Status.DONE,
                ChecklistSortRun.Status.PARTIAL,
                ChecklistSortRun.Status.ERROR,
            }:
                return processed
            step = process_sort_step(run_id, identity, user=user)
            if not step:
                return processed
            processed = True
    finally:
        if close_connections:
            close_old_connections()


def start_sort_run(*, project, section, asset_name, user, source_kind="cloud", local_inbox_path=""):
    asset = (asset_name or "").strip()
    if asset == "all":
        asset = ""
    kind = (source_kind or "cloud").strip() or "cloud"
    if kind not in {"cloud", "local"}:
        kind = "cloud"
    local_path = (local_inbox_path or "").strip()
    if kind == "local":
        try:
            resolve_local_inbox_dir(local_path, project, section)
        except LocalInboxError as exc:
            raise SortConfigError(str(exc)) from exc
    if not (getattr(settings, "DSH_HEADLESS_CMD", "") or "").strip():
        raise SortConfigError(
            "DSH для сортировки не настроен. Локально запустите ./scripts/dev_dsh.sh; "
            "на проде задайте DSH_HEADLESS_CMD из deploy/dsh/prod.env.dsh.example."
        )
    with transaction.atomic():
        lock_sort_scope(project, section, asset)
        existing = active_run_for(project, section, asset)
        if existing:
            raise SortRunConflict("Сортировка этого раздела уже выполняется.")
        if active_verify_for(project, section, asset):
            raise SortRunConflict("Дождитесь окончания проверки файлов.")
        run = ChecklistSortRun.objects.create(
            project=project,
            section=section,
            asset_name=asset,
            started_by=user,
            status=ChecklistSortRun.Status.QUEUED,
            source_kind=kind,
            local_inbox_path=local_path if kind == "local" else "",
        )
    inline = bool(getattr(settings, "DSH_SORT_INLINE", False))
    if inline:
        execute_sort_run(run.id, user=user)
        run.refresh_from_db()
        return run

    return run
