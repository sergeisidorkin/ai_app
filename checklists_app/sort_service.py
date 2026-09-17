import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Max
from django.utils import timezone

from core.cloud_storage import CloudStorageNotReadyError
from core.dsh_run import DshRunError, run_headless

from yandexdisk_app.workspace import _build_item_folder_name

from .models import ChecklistItem, ChecklistSortProposal, ChecklistSortRun
from .sort_parse import decorate_dest_rows, parse_sort_response
from .sort_workspace import (
    LocalInboxError,
    build_requests_markdown,
    cleanup_stale_sort_workspaces,
    create_dest_tree,
    inbox_section_label,
    materialize_inbox_tree,
    materialize_local_inbox,
    project_sections,
    resolve_inbox_folder,
    resolve_local_inbox_dir,
    workspace_root_for,
)

logger = logging.getLogger(__name__)


class SortRunConflict(Exception):
    pass


class SortConfigError(Exception):
    pass


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


def _sort_prompt(section, *, scan_all_inbox=False, inbox_folder=""):
    dest_label = _dest_section_label(section)
    chosen = (
        f"Раздел dest уже выбран: {dest_label}. "
        "Не спрашивай, какой раздел обрабатывать, и не предлагай варианты GEO/TSF/… "
        "Сразу dry-run только по этому разделу: инвентарь, таблица, JSON.\n\n"
    )
    if scan_all_inbox:
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
        "список запросов: requests.md\n\n"
        "Режим: только dry-run. Файлы не копировать и не перемещать.\n"
        "Читай актуальный requests.md. Класть можно только в папки dest, для которых есть строка в списке.\n"
        "После таблицы выведи блок ```json: по одному объекту на каждый комплект "
        "из таблицы, включая review. Число объектов JSON = число строк таблицы. "
        "Поля: kit, files, dest, name, quote, confidence, action. "
        "У review с пунктом dest заполни dest/name/quote. "
        "У review без пункта dest пиши dest = папка раздела, name/quote пустые, "
        "action всё равно review. Нельзя оставлять в JSON только move.\n"
        "Неуверенные — review. высокая + конкретный пункт dest → move; "
        "средняя/низкая + пункт dest → review; "
        "комплект относится к разделу, но пункт неясен → review, dest = папка раздела, не пункт CODE-NN. "
        "Такие комплекты не опускай. Пункты dest без комплектов в таблицу не выдумывай.\n\n"
        f"{scope}"
        "Комплект = папка или pdf+подпись. Без масок *.\n"
    )


def active_run_for(project, section, asset_name):
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


def serialize_run(run):
    from .sort_verify import reclaim_stale_verifies

    reclaim_stale_verifies(run_id=run.pk)
    if hasattr(run, "_prefetched_objects_cache"):
        run._prefetched_objects_cache.pop("proposals", None)
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
            "verifying": row.verify_status == "running",
            "verify_error": row.verify_error if row.verify_status == "error" else "",
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
        "status": run.status,
        "error_message": run.error_message,
        "section_id": run.section_id,
        "section_name": section_label(getattr(run, "section", None)),
        "inbox_section_name": run.inbox_section_name,
        "source_kind": getattr(run, "source_kind", "") or "cloud",
        "local_inbox_path": getattr(run, "local_inbox_path", "") or "",
        "created_at": run.created_at.isoformat() if run.created_at else "",
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "proposals": proposals,
    }


def _prepare_workspace(run, user):
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
    root.mkdir(parents=True, exist_ok=True)
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
            materialize_inbox_tree(inbox_dir, user, source_folder, inbox_folder)
        except CloudStorageNotReadyError as exc:
            raise DshRunError(str(exc)) from exc

    run.workspace_path = str(root)
    run.inbox_section_name = inbox_folder
    run.save(update_fields=["workspace_path", "inbox_section_name"])
    return root, {"scan_all_inbox": scan_all_inbox, "inbox_folder": inbox_folder}


def execute_sort_run(run_id, user=None, *, close_connections=False):
    if close_connections:
        close_old_connections()
    run = ChecklistSortRun.objects.select_related("project", "section", "started_by").filter(pk=run_id).first()
    if run is None:
        return
    if user is None:
        user = run.started_by
    run.status = ChecklistSortRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        root, prompt_scope = _prepare_workspace(run, user)
        output = run_headless(
            _sort_prompt(
                run.section,
                scan_all_inbox=prompt_scope["scan_all_inbox"],
                inbox_folder=prompt_scope["inbox_folder"],
            ),
            cwd=root,
        )
        rows = parse_sort_response(output)
        ChecklistSortProposal.objects.filter(run=run).delete()
        ChecklistSortProposal.objects.bulk_create(
            [
                ChecklistSortProposal(
                    run=run,
                    kit_path=row["kit_path"],
                    file_count=row["file_count"],
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
        run.raw_response = output
        run.status = ChecklistSortRun.Status.DONE
        run.error_message = ""
        run.finished_at = timezone.now()
        run.save(update_fields=["raw_response", "status", "error_message", "finished_at"])
    except Exception as exc:
        logger.exception("Checklist sort run %s failed", run_id)
        run.status = ChecklistSortRun.Status.ERROR
        run.error_message = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
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
    existing = active_run_for(project, section, asset)
    if existing:
        raise SortRunConflict("Сортировка этого раздела уже выполняется.")

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

    def _worker():
        execute_sort_run(run.id, user=user, close_connections=True)

    transaction.on_commit(lambda: threading.Thread(target=_worker, daemon=True).start())
    return run
