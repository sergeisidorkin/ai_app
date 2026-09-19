from dataclasses import dataclass

from yandexdisk_app.workspace import _build_item_folder_name

from .models import ChecklistItem
from .sort_parse import (
    _kit_key,
    dest_code_nn,
    dest_leaf_name,
    normalize_proposal_action,
)
from .sort_workspace import section_folder_name


class SortChunkValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DestRecord:
    path: str
    folder: str
    request_name: str
    quote: str
    section_id: int


def build_dest_index(project):
    records = []
    for item in (
        ChecklistItem.objects.filter(project=project)
        .select_related("section")
        .order_by("section_id", "position", "id")
    ):
        folder = _build_item_folder_name(item)
        records.append(
            DestRecord(
                path=f"dest/{section_folder_name(project, item.section)}/{folder}",
                folder=folder,
                request_name=item.short_name or "",
                quote=item.name or "",
                section_id=item.section_id,
            )
        )

    by_leaf = {record.folder.casefold(): record for record in records}
    code_groups = {}
    for record in records:
        code = dest_code_nn(record.folder)
        if code:
            code_groups.setdefault(code, []).append(record)
    by_code = {
        code: grouped[0]
        for code, grouped in code_groups.items()
        if len(grouped) == 1
    }
    return {"records": records, "by_leaf": by_leaf, "by_code": by_code}


def resolve_dest_record(dest_path, dest_index):
    leaf = dest_leaf_name(dest_path)
    if not leaf:
        return None
    record = dest_index["by_leaf"].get(leaf.casefold())
    if record is not None:
        return record
    code = dest_code_nn(leaf)
    return dest_index["by_code"].get(code) if code else None


def _fallback_row(kit, section_folder):
    return {
        "kit_path": kit["kit_path"],
        "file_count": kit.get("file_count") or 0,
        "dest_path": f"dest/{str(section_folder or '').strip('/')}",
        "request_name": "",
        "quote": "",
        "confidence": "",
        "action": "review",
        "position": 0,
    }


def fallback_rows(kits, section_folder):
    return [_fallback_row(kit, section_folder) for kit in kits]


def validate_chunk_rows(
    rows,
    expected_kits,
    *,
    dest_index,
    section_folder,
    require_complete=True,
):
    expected = {_kit_key(kit["kit_path"]): kit for kit in expected_kits}
    expected_by_id = {str(kit.get("id") or ""): key for key, kit in expected.items()}
    seen = set()
    validated = []
    extras = []
    for row in rows or []:
        row_key = _kit_key(row.get("kit_path"))
        row_id = str(row.get("kit_id") or "").strip()
        id_key = expected_by_id.get(row_id) if row_id else None
        if row_id and id_key is None:
            extras.append(f"id={row_id}")
            continue
        path_key = row_key if row_key in expected else next(
            (
                candidate
                for candidate in sorted(expected, key=len, reverse=True)
                if row_key.startswith(candidate + "/")
            ),
            "",
        )
        if id_key is not None and path_key and path_key != id_key:
            extras.append(f"id={row_id}, kit={row.get('kit_path') or ''}")
            continue
        key = id_key or path_key
        if not key:
            extras.append(str(row.get("kit_path") or ""))
            continue
        if key in seen:
            raise SortChunkValidationError(
                f"DSH вернул комплект повторно: {row.get('kit_path') or key}"
            )
        seen.add(key)
        kit = expected[key]
        if str(row.get("action") or "").casefold() == "ignore":
            continue
        record = resolve_dest_record(row.get("dest_path"), dest_index)
        if record is None:
            payload = _fallback_row(kit, section_folder)
            payload["confidence"] = str(row.get("confidence") or "")
        else:
            payload = {
                "kit_path": (
                    kit["kit_path"]
                    if row_id
                    else str(row.get("kit_path") or kit["kit_path"])
                ),
                "file_count": kit.get("file_count") or 0,
                "dest_path": record.path,
                "request_name": record.request_name,
                "quote": record.quote,
                "confidence": str(row.get("confidence") or ""),
                "action": normalize_proposal_action(
                    row.get("confidence"),
                    record.path,
                    row.get("action"),
                ),
                "position": 0,
            }
        validated.append(payload)

    if extras:
        raise SortChunkValidationError(
            "DSH вернул комплекты вне текущего чанка: " + ", ".join(extras[:3])
        )
    missing = [kit["kit_path"] for key, kit in expected.items() if key not in seen]
    if missing and require_complete:
        raise SortChunkValidationError(
            "DSH не вернул часть комплектов: " + ", ".join(missing[:3])
        )
    return validated


def dedupe_rows(rows):
    selected = {}
    order = []
    for row in rows or []:
        key = _kit_key(row.get("kit_path"))
        if not key:
            continue
        if key not in selected:
            order.append(key)
            selected[key] = dict(row)
            continue
        current = selected[key]
        current_review = str(current.get("action") or "").casefold() == "review"
        candidate_review = str(row.get("action") or "").casefold() == "review"
        if current_review and not candidate_review:
            selected[key] = dict(row)
    numbered = []
    for position, key in enumerate(order, start=1):
        payload = selected[key]
        payload["position"] = position
        numbered.append(payload)
    return numbered
