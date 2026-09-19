import json
import hashlib
import os
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from core.cloud_storage import CloudStorageNotReadyError, list_folder_resources
from policy_app.models import TypicalSection
from yandexdisk_app.workspace import _build_item_folder_name, _build_numbered_section_folder_name

from .models import ChecklistItem, ChecklistItemFolder, ChecklistSortRun, SourceDataSectionFolder


class LocalInboxError(ValueError):
    pass


class SortWorkspaceError(ValueError):
    pass


CLOUD_FILE_SIZES_NAME = ".cloud-file-sizes.json"
INVENTORY_NAME = "inbox-inventory.json"
INVENTORY_SCHEMA_VERSION = 1
INVENTORY_SAMPLE_LIMIT = 16
INVENTORY_TEXT_EXCERPT_LIMIT = 3
INVENTORY_TEXT_EXCERPT_CHARS = 500
INVENTORY_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
INVENTORY_PAGE_SIZE = 500


def project_sections(project):
    product_rank_map = getattr(project, "product_rank_map", {}) or {}
    product_ids = list(product_rank_map.keys())
    if not product_ids and getattr(project, "type_id", None):
        product_ids = [project.type_id]
        product_rank_map = {project.type_id: 1}
    if not product_ids:
        return []
    sections = list(
        TypicalSection.objects.filter(product_id__in=product_ids)
        .exclude(is_system=True)
        .exclude(code__iexact="DSC")
        .filter(accounting_type="Раздел")
        .order_by("position", "id")
    )
    sections.sort(
        key=lambda section: (
            product_rank_map.get(section.product_id, 999999),
            section.position,
            section.id,
        )
    )
    return sections


def section_nn_map(project):
    return {section.id: index for index, section in enumerate(project_sections(project), start=1)}


def section_folder_name(project, section):
    nn = section_nn_map(project).get(section.id) or 1
    return _build_numbered_section_folder_name(nn, section)


def request_folder_key(project, item):
    parent = section_folder_name(project, item.section)
    return f"{parent}/{_build_item_folder_name(item)}"


def build_requests_markdown(project):
    lines = [
        "# Запросы исходных данных",
        "",
        "Класть файлы только в папки из колонки «Папка». Не создавать узлы, которых нет в dest/.",
        "",
        "| Папка | Наименование запроса | Текст запроса |",
        "|---|---|---|",
    ]
    items = (
        ChecklistItem.objects.filter(project=project)
        .select_related("section")
        .order_by("section__position", "section_id", "position", "id")
    )
    for item in items:
        folder = request_folder_key(project, item).replace("|", " ")
        name = (item.short_name or item.name or "").replace("|", " ")
        text = (item.name or "").replace("|", " ").replace("\n", " ")
        lines.append(f"| {folder} | {name} | {text} |")
    return "\n".join(lines) + "\n"


def _safe_relpath(value):
    cleaned = str(value or "").replace("\\", "/").strip("/")
    parts = [part for part in cleaned.split("/") if part and part not in {".", ".."}]
    return Path(*parts) if parts else None


def create_dest_tree(dest_root: Path, project):
    dest_root.mkdir(parents=True, exist_ok=True)
    nn_map = section_nn_map(project)
    folders = ChecklistItemFolder.objects.filter(project=project).select_related("checklist_item", "checklist_item__section")
    created = 0
    for folder in folders:
        item = folder.checklist_item
        if item is None or item.deleted_at:
            continue
        nn = nn_map.get(item.section_id) or 1
        section_name = _build_numbered_section_folder_name(nn, item.section)
        rel = _safe_relpath(f"{section_name}/{_build_item_folder_name(item)}")
        if rel is None:
            continue
        (dest_root / rel).mkdir(parents=True, exist_ok=True)
        created += 1
    if created:
        return created
    for item in ChecklistItem.objects.filter(project=project).select_related("section"):
        nn = nn_map.get(item.section_id) or 1
        section_name = _build_numbered_section_folder_name(nn, item.section)
        rel = _safe_relpath(f"{section_name}/{_build_item_folder_name(item)}")
        if rel is None:
            continue
        (dest_root / rel).mkdir(parents=True, exist_ok=True)
        created += 1
    return created


def _list_children(user, path, heartbeat=None):
    children = []
    offset = 0
    while True:
        try:
            page = list_folder_resources(
                user,
                path,
                limit=INVENTORY_PAGE_SIZE,
                offset=offset,
            ) or []
        except CloudStorageNotReadyError:
            raise
        children.extend(page)
        if heartbeat is not None and heartbeat() is False:
            raise SortWorkspaceError("Lease прогона потерян при чтении облачного inbox.")
        if len(page) < INVENTORY_PAGE_SIZE:
            return children
        offset += len(page)


def list_cloud_tree(user, root_path, heartbeat=None):
    root = str(root_path or "").rstrip("/")
    if not root:
        return []
    entries = []
    queue = [root]
    seen = {root}
    while queue:
        current = queue.pop(0)
        children = _list_children(user, current, heartbeat=heartbeat)
        for child in children:
            path = str(child.get("path") or "").rstrip("/")
            if not path or path in seen:
                continue
            seen.add(path)
            name = child.get("name") or path.split("/")[-1]
            rel = path[len(root):].lstrip("/") if path.startswith(root) else name
            is_dir = child.get("type") == "dir"
            entries.append({"name": name, "path": path, "rel": rel, "is_dir": is_dir, "size": child.get("size") or 0})
            if is_dir:
                queue.append(path)
    return entries


def resolve_inbox_folder(project, section, asset_name):
    asset = (asset_name or "").strip()
    qs = SourceDataSectionFolder.objects.filter(project=project, section=section)
    if asset and asset != "all":
        match = qs.filter(asset_name=asset).first()
        if match:
            return match
    empty = qs.filter(asset_name="").first()
    if empty:
        return empty
    return qs.first()


def inbox_section_label(project, section, source_folder=None):
    if source_folder and source_folder.disk_path:
        return Path(str(source_folder.disk_path).rstrip("/")).name
    return section_folder_name(project, section)


def _path_is_allowed(resolved: Path):
    roots = getattr(settings, "DSH_SORT_LOCAL_ROOTS", ()) or ()
    for raw in roots:
        try:
            root = Path(raw).expanduser().resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve_local_inbox_dir(raw_path, project=None, section=None):
    if not getattr(settings, "DSH_SORT_ALLOW_LOCAL_INBOX", False):
        raise LocalInboxError("Локальный inbox на этом стенде выключен.")
    text = str(raw_path or "").strip()
    if not text:
        raise LocalInboxError("Укажите путь к локальной папке inbox.")
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError as exc:
        raise LocalInboxError(f"Не удалось прочитать путь: {exc}") from exc
    if not resolved.is_dir():
        raise LocalInboxError(f"Папка не найдена: {resolved}")
    if not _path_is_allowed(resolved):
        raise LocalInboxError(
            "Путь вне разрешённых корней локального тестирования. "
            "Ожидается каталог внутри Desktop/Workspace."
        )
    return resolved


def _remove_existing(path: Path):
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    if os.path.lexists(path):
        os.unlink(path)


def _replace_with_symlink(link: Path, target: Path):
    _remove_existing(link)
    os.symlink(os.fspath(target), os.fspath(link), target_is_directory=True)


def materialize_local_inbox(inbox_root: Path, source_dir: Path, section_label: str = ""):
    inbox_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        _replace_with_symlink(inbox_root, source_dir)
        return 1
    except OSError:
        _remove_existing(inbox_root)
        inbox_root.mkdir(parents=True, exist_ok=True)
        count = 0
        for dirpath, dirnames, filenames in os.walk(source_dir):
            rel = Path(dirpath).relative_to(source_dir)
            dest_dir = inbox_root if rel == Path(".") else inbox_root / rel
            dest_dir.mkdir(parents=True, exist_ok=True)
            for name in filenames:
                if name.startswith("."):
                    continue
                (dest_dir / name).touch()
                count += 1
        return count


def materialize_inbox_tree(
    inbox_root: Path,
    user,
    source_folder,
    section_label,
    *,
    heartbeat=None,
):
    if inbox_root.is_symlink() or inbox_root.is_file():
        inbox_root.unlink()
    elif os.path.lexists(inbox_root) and not inbox_root.is_dir():
        os.unlink(inbox_root)
    inbox_root.mkdir(parents=True, exist_ok=True)
    section_rel = _safe_relpath(section_label) or Path("section")
    section_dir = inbox_root / section_rel
    section_dir.mkdir(parents=True, exist_ok=True)
    sizes_path = inbox_root / CLOUD_FILE_SIZES_NAME
    if source_folder is None or not source_folder.disk_path:
        sizes_path.write_text("{}", encoding="utf-8")
        return 0
    entries = list_cloud_tree(user, source_folder.disk_path, heartbeat=heartbeat)
    count = 0
    file_sizes = {}
    for entry in entries:
        rel = _safe_relpath(entry["rel"])
        if rel is None:
            continue
        target = section_dir / rel
        if entry["is_dir"]:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
            try:
                size = max(0, int(entry.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            file_sizes[target.relative_to(inbox_root).as_posix()] = size
            count += 1
        if heartbeat is not None and count % 250 == 0 and heartbeat() is False:
            raise SortWorkspaceError("Lease прогона потерян при подготовке облачного inbox.")
    sizes_path.write_text(
        json.dumps(file_sizes, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return count


def _visible_children(path: Path):
    if not path.is_dir():
        return []
    try:
        children = [child for child in path.iterdir() if not child.name.startswith(".")]
    except OSError:
        return []
    return sorted(children, key=lambda child: child.name.casefold())


def _kit_stats(path: Path, heartbeat=None):
    if path.is_file():
        suffix = path.suffix.casefold() or "<none>"
        return 1, {suffix: 1}
    total = 0
    extensions = Counter()
    if not path.is_dir():
        return total, {}
    for _, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            total += 1
            suffix = Path(name).suffix.casefold() or "<none>"
            extensions[suffix] += 1
            if total % 250 == 0 and heartbeat is not None and heartbeat() is False:
                raise SortWorkspaceError("Lease прогона потерян при построении inventory.")
    return total, dict(sorted(extensions.items()))


def _kit_samples(path: Path):
    if path.is_file():
        return [path.name]
    samples = []
    children = _visible_children(path)
    for child in children:
        if len(samples) >= INVENTORY_SAMPLE_LIMIT:
            break
        samples.append(f"{child.name}/" if child.is_dir() else child.name)
        if child.is_dir():
            for grandchild in _visible_children(child):
                if len(samples) >= INVENTORY_SAMPLE_LIMIT:
                    break
                suffix = "/" if grandchild.is_dir() else ""
                samples.append(f"{child.name}/{grandchild.name}{suffix}")
    if len(children) > INVENTORY_SAMPLE_LIMIT:
        samples.append(f"+{len(children) - INVENTORY_SAMPLE_LIMIT}")
    return samples


def _kit_text_excerpts(path: Path, heartbeat=None):
    candidates = []
    if path.is_file() and path.suffix.casefold() in INVENTORY_TEXT_EXTENSIONS:
        candidates = [path]
    elif path.is_dir():
        for current, dirnames, filenames in os.walk(path, followlinks=False):
            dirnames[:] = sorted(
                (name for name in dirnames if not name.startswith(".")),
                key=str.casefold,
            )
            for name in sorted(filenames, key=str.casefold):
                if name.startswith(".") or Path(name).suffix.casefold() not in INVENTORY_TEXT_EXTENSIONS:
                    continue
                candidates.append(Path(current) / name)
                if len(candidates) >= INVENTORY_TEXT_EXCERPT_LIMIT:
                    break
            if len(candidates) >= INVENTORY_TEXT_EXCERPT_LIMIT:
                break
    excerpts = []
    for candidate in candidates[:INVENTORY_TEXT_EXCERPT_LIMIT]:
        try:
            if candidate.stat().st_size > 64 * 1024:
                continue
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = re.sub(r"\s+", " ", text.replace("\x00", "")).strip()
        if not text:
            continue
        excerpts.append({
            "path": candidate.relative_to(path.parent if path.is_file() else path).as_posix(),
            "text": text[:INVENTORY_TEXT_EXCERPT_CHARS],
        })
        if heartbeat is not None and heartbeat() is False:
            raise SortWorkspaceError("Lease прогона потерян при чтении текстового inventory.")
    return excerpts


def _kit_id(relative_path):
    normalized = str(relative_path or "").replace("\\", "/").strip("/").casefold()
    return "k-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _inventory_record(
    path: Path,
    inbox_root: Path,
    kit_root: Path,
    *,
    parent_path="",
    heartbeat=None,
):
    relative = path.relative_to(kit_root).as_posix()
    source_path = path.relative_to(inbox_root).as_posix()
    file_count, extensions = _kit_stats(path, heartbeat=heartbeat)
    samples = _kit_samples(path)
    text_excerpts = _kit_text_excerpts(path, heartbeat=heartbeat)
    structural = json.dumps(
        {
            "path": relative.casefold(),
            "files": file_count,
            "extensions": extensions,
            "samples": samples,
            "text_excerpts": text_excerpts,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "id": _kit_id(source_path),
        "kit_path": relative,
        "source_path": source_path,
        "parent_path": parent_path,
        "is_dir": path.is_dir(),
        "file_count": file_count,
        "extensions": extensions,
        "samples": samples,
        "text_excerpts": text_excerpts,
        "fingerprint": hashlib.sha256(structural.encode("utf-8")).hexdigest(),
    }


def build_inbox_inventory(
    inbox_root: Path,
    scan_root: Path = None,
    *,
    canonical_folders=None,
    heartbeat=None,
):
    target = scan_root if scan_root is not None else inbox_root
    canonical = {str(name or "").strip().casefold() for name in (canonical_folders or []) if str(name or "").strip()}
    kit_paths = []
    if target.is_dir():
        for child in _visible_children(target):
            has_code_prefix = bool(re.match(r"^[A-Za-z]{2,}-\d+\b", child.name))
            if (
                child.is_dir()
                and canonical
                and child.name.casefold() not in canonical
                and not has_code_prefix
            ):
                nested = _visible_children(child)
                should_expand = (
                    len(nested) == 1
                    or (nested and all(entry.is_dir() for entry in nested))
                )
                if should_expand:
                    kit_paths.extend((entry, child.relative_to(target).as_posix()) for entry in nested)
                    continue
            kit_paths.append((child, ""))
    records = [
        _inventory_record(
            path,
            inbox_root,
            target,
            parent_path=parent_path,
            heartbeat=heartbeat,
        )
        for path, parent_path in kit_paths
    ]
    scan_rel = ""
    try:
        scan_rel = target.relative_to(inbox_root).as_posix()
    except ValueError:
        scan_rel = ""
    return {
        "version": INVENTORY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_root": "" if scan_rel == "." else scan_rel,
        "kits": records,
    }


def expand_inventory_kit(workspace_root: Path, kit, *, heartbeat=None):
    workspace_root = Path(workspace_root)
    inventory_path = workspace_root / INVENTORY_NAME
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SortWorkspaceError("Не удалось прочитать inventory для детализации.") from exc
    inbox_root = workspace_root / "inbox"
    scan_rel = _safe_relpath(payload.get("scan_root"))
    scan_root = inbox_root / scan_rel if scan_rel is not None else inbox_root
    source_rel = _safe_relpath((kit or {}).get("source_path"))
    if source_rel is None:
        return []
    target = inbox_root / source_rel
    if not target.is_dir():
        return []
    children = _visible_children(target)
    return [
        _inventory_record(
            child,
            inbox_root,
            scan_root,
            parent_path=str((kit or {}).get("kit_path") or ""),
            heartbeat=heartbeat,
        )
        for child in children
    ]


def write_inbox_inventory(
    workspace_root: Path,
    inbox_root: Path,
    scan_root: Path = None,
    *,
    canonical_folders=None,
    heartbeat=None,
):
    inventory = build_inbox_inventory(
        inbox_root,
        scan_root,
        canonical_folders=canonical_folders,
        heartbeat=heartbeat,
    )
    (workspace_root / INVENTORY_NAME).write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return len(inventory["kits"])


def parse_inbox_inventory(text):
    try:
        payload = json.loads(str(text or ""))
    except (TypeError, ValueError) as exc:
        raise SortWorkspaceError("Inventory содержит некорректный JSON.") from exc
    if not isinstance(payload, dict) or payload.get("version") != INVENTORY_SCHEMA_VERSION:
        raise SortWorkspaceError("Версия inventory не поддерживается.")
    kits = payload.get("kits")
    if not isinstance(kits, list):
        raise SortWorkspaceError("В inventory отсутствует массив kits.")
    normalized = []
    seen_ids = set()
    seen_paths = set()
    for item in kits:
        if not isinstance(item, dict):
            raise SortWorkspaceError("Inventory содержит комплект неверного формата.")
        raw_path = str(item.get("kit_path") or "").replace("\\", "/")
        kit_path = raw_path.strip("/")
        kit_id = str(item.get("id") or "").strip()
        if (
            not kit_path
            or not kit_id
            or raw_path.startswith("/")
            or any(part in {"", ".", ".."} for part in kit_path.split("/"))
        ):
            raise SortWorkspaceError("Inventory содержит небезопасный путь комплекта.")
        key = kit_path.casefold()
        if kit_id in seen_ids or key in seen_paths:
            raise SortWorkspaceError("Inventory содержит повторяющийся комплект.")
        seen_ids.add(kit_id)
        seen_paths.add(key)
        try:
            file_count = max(int(item.get("file_count") or 0), 0)
        except (TypeError, ValueError) as exc:
            raise SortWorkspaceError("Inventory содержит неверный file_count.") from exc
        normalized.append(
            {
                "id": kit_id,
                "kit_path": kit_path,
                "parent_path": str(item.get("parent_path") or ""),
                "source_path": str(item.get("source_path") or kit_path),
                "is_dir": bool(item.get("is_dir")),
                "file_count": file_count,
                "extensions": item.get("extensions") if isinstance(item.get("extensions"), dict) else {},
                "samples": item.get("samples") if isinstance(item.get("samples"), list) else [],
                "text_excerpts": (
                    item.get("text_excerpts")
                    if isinstance(item.get("text_excerpts"), list)
                    else []
                ),
                "fingerprint": str(item.get("fingerprint") or ""),
            }
        )
    return normalized


def load_cloud_file_sizes(path: Path):
    current = path if path.is_dir() else path.parent
    for parent in (current, *current.parents):
        manifest_path = parent / CLOUD_FILE_SIZES_NAME
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None, {}
        if not isinstance(payload, dict):
            return None, {}
        sizes = {}
        for key, value in payload.items():
            try:
                sizes[str(key).replace("\\", "/")] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        return parent, sizes
    return None, {}


def workspace_root_for(run_id):
    base = (getattr(settings, "DSH_SORT_WORKSPACE", "") or "").strip()
    if base:
        return Path(base) / str(run_id)
    if getattr(settings, "DEBUG", False):
        return Path(settings.BASE_DIR) / "deploy" / "dsh" / "data" / "sort-runs" / str(run_id)
    raise SortWorkspaceError(
        "На проде не задан DSH_SORT_WORKSPACE. Укажите каталог на общем volume "
        "с контейнером DSH, обычно /opt/dsh/workspace/sort-runs."
    )


def _sort_workspace_roots():
    roots = []
    configured = (getattr(settings, "DSH_SORT_WORKSPACE", "") or "").strip()
    if configured:
        roots.append(Path(configured).expanduser())
    roots.append(Path(settings.BASE_DIR) / "deploy" / "dsh" / "data" / "sort-runs")
    resolved = []
    for raw in roots:
        try:
            resolved.append(raw.resolve())
        except OSError:
            continue
    return resolved


def remove_run_workspace(run):
    raw = (getattr(run, "workspace_path", "") or "").strip()
    if not raw:
        return
    try:
        path = Path(raw).expanduser().resolve()
    except OSError:
        return
    allowed = False
    for root in _sort_workspace_roots():
        try:
            path.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    if run.workspace_path:
        run.workspace_path = ""
        run.save(update_fields=["workspace_path"])


def cleanup_stale_sort_workspaces(run):
    old_runs = ChecklistSortRun.objects.filter(
        project_id=run.project_id,
        section_id=run.section_id,
        asset_name=run.asset_name,
    ).exclude(pk=run.pk)
    for old in old_runs:
        if old.proposals.filter(verify_status__in=["queued", "running"]).exists():
            continue
        try:
            remove_run_workspace(old)
        except OSError:
            continue


def reset_sort_workspace(path: Path):
    _remove_existing(path)
    path.mkdir(parents=True, exist_ok=True)
