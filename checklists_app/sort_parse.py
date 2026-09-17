import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)
_FENCE_OBJECT_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)
_CODE_NN_RE = re.compile(r"^([A-Za-z]{2,})-(\d+)\b")


def _clean_cell(value):
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _parse_file_count(value):
    raw = _clean_cell(value).lstrip("~")
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def _clean_dest(value):
    dest = _clean_cell(value)
    if dest.casefold() in {"—", "–", "-", "_needs_review/", "_needs_review"}:
        return ""
    return dest


def _kit_key(kit):
    return _clean_cell(kit).rstrip("/").casefold()


def dest_leaf_name(path):
    text = str(path or "").replace("\\", "/").strip().rstrip("/")
    if not text:
        return ""
    leaf = text.split("/")[-1].strip()
    if not leaf or leaf.casefold() in {"dest", "—", "–", "-"}:
        return ""
    return leaf


def dest_code_nn(leaf):
    match = _CODE_NN_RE.match(str(leaf or "").strip())
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}".casefold()


def _norm_dest_key(value):
    return " ".join(str(value or "").casefold().replace("_", " ").split())


def _confidence_band(value):
    text = _clean_cell(value).casefold().rstrip(".")
    if text in {"высокая", "high"}:
        return "high"
    if text in {"средняя", "medium"}:
        return "medium"
    if text in {"низкая", "low"}:
        return "low"
    return ""


def dest_is_item_folder(path):
    return bool(dest_code_nn(dest_leaf_name(path)))


def normalize_proposal_action(confidence, dest_path, action=""):
    cleaned = _clean_cell(action).lower()
    if cleaned not in {"move", "review", "confirm"}:
        cleaned = "review"
    if not dest_is_item_folder(dest_path):
        return "review" if cleaned != "confirm" else "confirm"
    band = _confidence_band(confidence)
    if band == "high":
        return "move"
    if cleaned == "confirm":
        return "confirm"
    return "review"


def finalize_verify_action(_previous_confidence, confidence, dest_path, action=""):
    if normalize_proposal_action(confidence, dest_path, action) == "move":
        return "move"
    return "confirm"


def _normalize_dest_items(item_folders):
    items = []
    for index, entry in enumerate(item_folders or []):
        if isinstance(entry, dict):
            folder = str(entry.get("folder") or entry.get("dest_folder") or "").strip()
            request_name = str(entry.get("request_name") or "").strip()
            quote = str(entry.get("quote") or "").strip()
        else:
            folder = str(entry or "").strip()
            request_name = ""
            quote = ""
        if not folder:
            continue
        items.append({
            "folder": folder,
            "request_name": request_name,
            "quote": quote,
            "dest_order": index,
        })
    return items


def decorate_dest_rows(rows, item_folders, section_folder=""):
    items = _normalize_dest_items(item_folders)
    order = {}
    canonical = {}
    labels = {}
    for item in items:
        name = item["folder"]
        key = _norm_dest_key(name)
        order[key] = item["dest_order"]
        canonical[key] = name
        labels[key] = item
        code = dest_code_nn(name)
        if code:
            order.setdefault(code, item["dest_order"])
            canonical.setdefault(code, name)
            labels.setdefault(code, item)

    decorated = []
    covered = set()
    for index, row in enumerate(rows or []):
        payload = dict(row)
        leaf = dest_leaf_name(payload.get("dest_path") or payload.get("dest_folder") or "")
        key = _norm_dest_key(leaf)
        code = dest_code_nn(leaf)
        dest_order = order.get(key)
        lookup = key
        if dest_order is None and code:
            dest_order = order.get(code)
            lookup = code if dest_order is not None else key
        if dest_order is None:
            payload["dest_folder"] = str(section_folder or "").strip()
            payload["dest_order"] = 2_000_000
            if str(payload.get("action") or "").lower() != "confirm":
                payload["action"] = "review"
            payload["request_name"] = payload.get("request_name") or ""
            payload["quote"] = payload.get("quote") or ""
        else:
            payload["dest_folder"] = canonical.get(lookup, leaf)
            payload["dest_order"] = dest_order
            payload["action"] = normalize_proposal_action(
                payload.get("confidence"),
                payload.get("dest_path") or payload.get("dest_folder") or "",
                payload.get("action"),
            )
            covered.add(dest_order)
            meta = labels.get(lookup) or {}
            if meta.get("request_name") and not payload.get("request_name"):
                payload["request_name"] = meta["request_name"]
            if meta.get("quote") and not payload.get("quote"):
                payload["quote"] = meta["quote"]
        payload["_stable"] = index
        decorated.append(payload)

    extra_index = len(rows or [])
    for item in items:
        if item["dest_order"] in covered:
            continue
        decorated.append({
            "kit_path": "",
            "file_count": 0,
            "dest_path": "",
            "dest_folder": item["folder"],
            "request_name": item["request_name"],
            "quote": item["quote"],
            "confidence": "",
            "action": "",
            "dest_order": item["dest_order"],
            "placeholder": True,
            "_stable": extra_index,
        })
        extra_index += 1

    decorated.sort(key=lambda row: (row["dest_order"], row["_stable"]))
    for row in decorated:
        row.pop("_stable", None)
    return decorated


def _row_from_mapping(item, position):
    if not isinstance(item, dict):
        return None
    kit = _clean_cell(
        item.get("kit")
        or item.get("kit_path")
        or item.get("комплект")
        or item.get("inbox")
        or ""
    )
    if not kit or kit.startswith("-"):
        return None
    dest = _clean_dest(item.get("dest") or item.get("dest_path") or item.get("папка dest") or "")
    confidence = _clean_cell(item.get("confidence") or item.get("уверенность") or "")
    action = _clean_cell(item.get("action") or item.get("действие") or "review").lower()
    return {
        "kit_path": kit,
        "file_count": _parse_file_count(item.get("files") or item.get("file_count") or item.get("файлов") or 0),
        "dest_path": dest,
        "request_name": _clean_cell(item.get("name") or item.get("request_name") or item.get("наименование запроса") or ""),
        "quote": _clean_cell(item.get("quote") or item.get("цитата") or item.get("цитата из requests.md") or ""),
        "confidence": confidence,
        "action": normalize_proposal_action(confidence, dest, action),
        "position": position,
    }


def parse_json_proposals(text):
    payload = str(text or "")
    candidates = []
    for match in _FENCE_RE.finditer(payload):
        candidates.append(match.group(1))
    if not candidates:
        match = _JSON_ARRAY_RE.search(payload)
        if match:
            candidates.append(match.group(0))
    for raw in candidates:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        rows = []
        for index, item in enumerate(parsed, start=1):
            row = _row_from_mapping(item, index)
            if row:
                rows.append(row)
        if rows:
            return rows
    return []


def parse_markdown_table(text):
    rows = []
    header = None
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 3:
            continue
        cells = [_clean_cell(part) for part in stripped.strip("|").split("|")]
        if not cells:
            continue
        joined = " ".join(cells).lower()
        if set(joined) <= {"-", ":", " "} or re.fullmatch(r"[-:| ]+", stripped):
            continue
        if header is None:
            header = [cell.casefold() for cell in cells]
            continue

        mapping = {}
        for index, key in enumerate(header):
            if index < len(cells):
                mapping[key] = cells[index]
        aliases = {
            "kit": mapping.get("комплект (путь относительно inbox)")
            or mapping.get("комплект")
            or mapping.get("kit")
            or cells[0],
            "files": mapping.get("файлов") or mapping.get("files") or (cells[1] if len(cells) > 1 else 0),
            "dest": mapping.get("папка dest (точный путь)")
            or mapping.get("папка dest")
            or mapping.get("dest")
            or (cells[2] if len(cells) > 2 else ""),
            "name": mapping.get("наименование запроса") or mapping.get("name") or (cells[3] if len(cells) > 3 else ""),
            "quote": mapping.get("цитата из requests.md") or mapping.get("цитата") or mapping.get("quote") or (cells[4] if len(cells) > 4 else ""),
            "confidence": mapping.get("уверенность") or mapping.get("confidence") or (cells[5] if len(cells) > 5 else ""),
            "action": mapping.get("действие") or mapping.get("action") or (cells[6] if len(cells) > 6 else "review"),
        }
        row = _row_from_mapping(aliases, len(rows) + 1)
        if row:
            rows.append(row)
    return rows


def normalize_rel_path(value, *, kit_prefix=""):
    text = str(value or "").replace("\\", "/").strip().lstrip("./")
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    prefix = [
        part
        for part in str(kit_prefix or "").replace("\\", "/").strip("/").split("/")
        if part and part not in {".", ".."}
    ]
    if prefix and parts[: len(prefix)] == prefix:
        parts = parts[len(prefix) :]
    return "/".join(parts)


def _peek_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return []
    seen = set()
    paths = []
    for item in items:
        rel = normalize_rel_path(item)
        if not rel:
            continue
        key = rel.casefold()
        if key in seen:
            continue
        seen.add(key)
        paths.append(rel)
    return paths


def parse_json_objects(text):
    payload = str(text or "")
    objects = []
    for match in _FENCE_OBJECT_RE.finditer(payload):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
    decoder = json.JSONDecoder()
    idx = payload.find("{")
    while idx != -1:
        try:
            parsed, end = decoder.raw_decode(payload, idx)
        except json.JSONDecodeError:
            idx = payload.find("{", idx + 1)
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
        idx = payload.find("{", end)
    return objects


def parse_verify_select_response(text):
    for obj in parse_json_objects(text):
        if "peek" in obj:
            return _peek_list(obj.get("peek"))
    rows = parse_json_proposals(text)
    if rows:
        return _peek_list([row.get("kit_path") for row in rows])
    return []


def parse_verify_classify_response(text, kit_path=""):
    rows = parse_sort_response(text)
    if not rows:
        for obj in parse_json_objects(text):
            row = _row_from_mapping(obj, 1)
            if row:
                rows = [row]
                break
    if not rows:
        return None
    wanted = _kit_key(kit_path)
    if wanted:
        for row in rows:
            if _kit_key(row.get("kit_path")) == wanted:
                return row
    return rows[0]


def parse_sort_response(text):
    json_rows = parse_json_proposals(text)
    table_rows = parse_markdown_table(text)
    if not json_rows:
        return table_rows
    if not table_rows:
        return json_rows
    seen = {_kit_key(row["kit_path"]) for row in json_rows}
    merged = list(json_rows)
    for row in table_rows:
        key = _kit_key(row["kit_path"])
        if key in seen:
            continue
        extra = dict(row)
        extra["position"] = len(merged) + 1
        merged.append(extra)
        seen.add(key)
    return merged
