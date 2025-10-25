# ai_app/onedrive_app/service.py
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Dict, Iterable

from .graph import (
    list_children,
    search_in_folder,     # убедись, что он есть в graph.py (см. ниже)
    create_link,
    invite_recipients,
)

DOC_EXTS = (".docx", ".doc")

# ---------- утилиты имени/поиска ----------

def _norm_prefix(code: str, company: str, section: str) -> str:
    # пример имени: "8888RU_ООО «Горная компания»_HR"
    return f"{code}_{company}_{section}"

def _startswith_ci(s: str, prefix: str) -> bool:
    return (s or "").lower().startswith((prefix or "").lower())

def _norm(s: str) -> str:
    # унификация: пробелы/подчёркивания/дефисы → пробел, нижний регистр
    return re.sub(r"[\s_\-]+", " ", (s or "").strip(), flags=re.I).casefold()

def _parse_dt(iso: str) -> datetime:
    try:
        return datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------- обход содержимого папок ----------

def _iter_children(user, parent_id: str) -> Iterable[Dict]:
    """Одноуровневый проход по детям (без пагинации)."""
    data = list_children(user, parent_id) or {}
    for it in data.get("value", []):
        yield it

def find_child_folder_by_prefix(user, parent_id: str, prefix: str) -> Optional[Dict]:
    pfx = (prefix or "").strip()
    for it in _iter_children(user, parent_id):
        if it.get("folder") and (it.get("name", "") or "").startswith(pfx):
            return it
    return None

def _score_candidate(name: str, code6: str, company: Optional[str], section: Optional[str]) -> int:
    """
    Чем больше балл — тем точнее совпадение.
    3 — матч по всем частям, 2 — по коду+одной части, 1 — только по коду.
    0 — не подходит.
    """
    n = name or ""
    if not n.lower().endswith(DOC_EXTS):
        return 0
    if not n.startswith(code6):
        return 0

    want_company = _norm(company) if company else None
    want_section = _norm(section) if section else None
    n_norm = _norm(n)

    hit_company = (want_company and want_company in n_norm)
    hit_section = (want_section and re.search(rf"(\s|^)({re.escape(want_section)})($|\s|\.)", n_norm))

    if want_company and want_section:
        return 3 if (hit_company and hit_section) else 0
    if want_company or want_section:
        return 2 if (hit_company or hit_section) else 0
    return 1  # только код

def find_target_doc_in_folder(user, folder_id: str, code6: str,
                              company: Optional[str], section: Optional[str]) -> Optional[Dict]:
    """
    Ищем .docx/.doc, имя начинается с кода проекта и (опционально) содержит компанию/секцию.
    Если несколько — берём с максимальным score, затем с последней модификацией.
    """
    best = None
    best_score = -1
    best_mtime = datetime(1970, 1, 1, tzinfo=timezone.utc)

    for it in _iter_children(user, folder_id):
        if not it.get("file"):  # только файлы
            continue
        name = it.get("name", "")
        sc = _score_candidate(name, code6, company, section)
        if sc <= 0:
            continue
        mt = _parse_dt(it.get("lastModifiedDateTime", "1970-01-01T00:00:00Z"))
        if (sc > best_score) or (sc == best_score and mt > best_mtime):
            best, best_score, best_mtime = it, sc, mt

    return best


# ---------- основной резолвер ----------

def resolve_doc_info(user, selection, code: str, company: str, section: str) -> Dict[str, str]:
    """
    Возвращает {'driveId','itemId','name','webUrl'} для файла вида:
    {CODE}_{COMPANY}_{SECTION}*.docx внутри папки проекта, имя которой начинается с CODE.
    selection — это OneDriveSelection (базовая папка).
    """
    if not selection or not selection.item_id:
        raise RuntimeError("OneDrive base folder is not selected")

    base_id = selection.item_id

    # 1) Ищем подпапку проекта по префиксу CODE (быстрое search, затем fallback на list_children)
    sr = search_in_folder(user, base_id, code) or {"value": []}
    proj_folders = [
        it for it in sr.get("value", [])
        if it.get("folder") and _startswith_ci(it.get("name", ""), code)
    ]
    if not proj_folders:
        ls = list_children(user, base_id) or {"value": []}
        proj_folders = [
            it for it in ls.get("value", [])
            if it.get("folder") and _startswith_ci(it.get("name", ""), code)
        ]
    if not proj_folders:
        raise RuntimeError(f"Папка проекта с префиксом '{code}' не найдена в выбранной базовой папке.")

    proj = sorted(proj_folders, key=lambda x: x.get("name", ""))[0]
    proj_id = proj["id"]

    # 2) Внутри папки проекта ищем .docx с именем-префиксом "{code}_{company}_{section}"
    prefix = _norm_prefix(code, company, section)
    ls2 = list_children(user, proj_id) or {"value": []}
    candidates = [
        it for it in ls2.get("value", [])
        if not it.get("folder")
           and it.get("name", "").lower().endswith(".docx")
           and _startswith_ci(it.get("name", ""), prefix)
    ]
    if not candidates:
        raise RuntimeError(f"Файл с префиксом '{prefix}' (.docx) не найден в папке проекта '{proj.get('name')}'.")

    # Если несколько — точное начало "{prefix}.docx" приоритетнее, затем короче имя
    def score(it):
        n = (it.get("name") or "")
        return (0 if n.lower().startswith((prefix + ".docx").lower()) else 1, len(n))

    doc = sorted(candidates, key=score)[0]

    drive_id = (doc.get("parentReference") or {}).get("driveId")
    item_id  = doc.get("id")
    web_url  = doc.get("webUrl")
    name     = doc.get("name")

    if not (drive_id and item_id and web_url):
        raise RuntimeError("Недостаточно метаданных файла (driveId/itemId/webUrl).")

    return {"driveId": drive_id, "itemId": item_id, "name": name, "webUrl": web_url}


def resolve_doc_web_url(user, selection, code: str, company: str, section: str) -> str:
    """Тонкая обёртка для совместимости — возвращает только webUrl."""
    return resolve_doc_info(user, selection, code, company, section)["webUrl"]


# ---------- шэринг ----------

def ensure_share_link_for_doc(user, drive_id: str, item_id: str, *,
                              prefer: str = "organization",
                              grant_emails: list[str] | None = None) -> str:
    """
    Возвращает webUrl, по которому документ будет открываться у нужных людей.
    1) Создаёт ссылку редактирования для организации (или anonymous — если нужно и разрешено).
    2) Дополнительно может выдать точечные права конкретным email.
    """

    if prefer in ("organization", None):
        data = create_link(user, drive_id, item_id, link_type="edit", scope="organization")
    else:
        data = create_link(user, drive_id, item_id, link_type="edit", scope="anonymous")
    share_url = (data.get("link") or {}).get("webUrl")

    if grant_emails:
        try:
            invite_recipients(user, drive_id, item_id, grant_emails, role="write", send_invitation=False)
        except Exception as e:
            # Лог — но не мешаем основному сценарию
            print("invite_recipients skipped:", e)

    return share_url