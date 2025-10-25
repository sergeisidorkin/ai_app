# office_addin/utils.py
import json, re, logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from typing import Iterable

try:
    from docops_app.parsers import try_extract_docops_json
except Exception:
    # Фолбэк (на случай, если docops_app не установлен)
    def try_extract_docops_json(_):  # type: ignore
        return None


log = logging.getLogger(__name__)

def try_extract_docops_json(raw: str):
    if not raw:
        return None
    s = raw.strip()

    # 1) Найти fenced-блок в любом месте (```docops ... ```)
    fence_pat = re.compile(r"```(?:docops|json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    m = fence_pat.search(s)
    if m:
        s = m.group(1).strip()

    # 2) Если это JSON-строковый литерал, попробуем "разэскейпить" один раз
    #    Признак: начинается и заканчивается кавычкой И внутри есть экранированные поля DocOps
    if (s.startswith('"') and s.endswith('"') and '\\"type\\":\\"DocOps\\"' in s):
        try:
            s = json.loads(s)  # теперь s — внутренняя строка с JSON
        except Exception:
            pass

    # 3) Если уже словарь — хорошо; если строка — вырезаем от { ... } и парсим
    if isinstance(s, dict):
        obj = s
    else:
        # Вырезать подстроку от первого '{' до последней '}'
        start = s.find("{"); end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        fragment = s[start:end+1]
        try:
            obj = json.loads(fragment)
        except Exception:
            return None

    # 4) Валидация формы DocOps
    if obj.get("type") != "DocOps" or obj.get("version") != "v1" or not isinstance(obj.get("ops"), list):
        return None

    allowed = {"paragraph.insert","list.start","list.item","list.end"}
    for op in obj["ops"]:
        if not isinstance(op, dict):
            return None
        if op.get("op") not in allowed:
            return None
    if isinstance(obj, dict) and "program" in obj and isinstance(obj["program"], dict):
        obj = obj["program"]
    if isinstance(obj, dict) and "docops" in obj and isinstance(obj["docops"], dict):
        obj = obj["docops"]

    return obj



def text_to_ops_fallback(txt: str):
    """Преобразует чистый текст (абзац=строка; список начинается с '- ') в ops."""
    lines = [l.strip() for l in (txt or "").splitlines()]
    ops = []
    in_list = False

    def start_list():
        nonlocal in_list
        if not in_list:
            ops.append({"op":"list.start","styleId":"a","styleName":"Маркированный список"})
            in_list = True

    def end_list():
        nonlocal in_list
        if in_list:
            ops.append({"op":"list.end"})
            in_list = False

    for line in lines:
        if not line:  # пустая строка → разрыв списка и пустой абзац (если нужен)
            end_list()
            continue

        if line.startswith("- "):  # список
            start_list()
            ops.append({"op":"list.item","text":line[2:].strip()})
        else:
            end_list()
            ops.append({"op":"paragraph.insert","text":line})

    end_list()
    return {"type":"DocOps","version":"v1","ops":ops}

def group_for_email(email: str) -> str:
    e = (email or "").strip().lower().replace("@", ".")
    e = re.sub(r"[^a-z0-9._-]+", ".", e)
    return f"user_{e}"

def send_addin_block(email: str, block: dict):
    grp = group_for_email(email)
    payload = {"type": "addin.block", "block": block}
    log.warning("WS SEND group=%s payload=%s", grp, payload)
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(grp, payload)

def send_paragraph(email: str, text: str, style: str | None = None, styleBuiltIn: str | None = None) -> None:
    """
    Отправляет один абзац в Word Add-in по e-mail-группе.
    styleBuiltIn — имя встроенного стиля Word (например, 'Normal', 'Heading1').
    style — обычное имя стиля (кастом).
    """
    group = group_for_email(email)
    block = {"type": "paragraph", "text": text}
    if styleBuiltIn:
        block["styleBuiltIn"] = styleBuiltIn
    elif style:
        block["style"] = style

    payload = {"type": "addin.block", "block": block}
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(group, payload)
    print("WS SEND", "group=", group, "payload=", payload)

def send_text_as_paragraphs(email: str, text: str, *, style: str | None = None, styleBuiltIn: str | None = "Normal") -> int:
    from .utils import group_for_email as _group_for_email
    group = _group_for_email(email)
    layer = get_channel_layer()

    chunks = [s.strip() for s in re.split(r"\n{2,}", text or "") if s.strip()]
    if not chunks:
        chunks = [text or ""]

    sent = 0
    for ch in chunks:
        block = {"kind": "paragraph.insert", "text": ch}
        if styleBuiltIn:
            block["styleBuiltIn"] = styleBuiltIn
        if style:
            block["styleNameHint"] = style

        async_to_sync(layer.group_send)(group, {
            "type": "addin.block",
            "block": block,
        })
        sent += 1
    return sent

def send_addin_block_group(group: str, block: dict):
    """Отправка одного DocOps-«опа» (addin.block) прямо по имени группы."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(group, {"type": "addin.block", "block": block})

def handle_llm_answer(raw_text: str, group: str) -> int:
    """
    Универсальная обработка ответа LLM:
    - пытаемся вытащить DocOps JSON из raw (включая fenced-блоки ```docops/```json)
    - если нет — превращаем чистый текст в DocOps (параграфы и пункты списка по «- »)
    - шлём ops по WS как addin.block (один op = одно сообщение)
    Возвращаем количество отправленных op'ов.
    """

    log.warning("LLM RAW head=%s", (raw_text or "")[:160].replace("\n","⏎"))
    docops = try_extract_docops_json(raw_text)
    used_fallback = False
    if not docops:
        used_fallback = True
        docops = text_to_ops_fallback(raw_text or "")

    ops = docops.get("ops") or []
    log.warning("DocOps parsed: ops=%d fallback=%s first_op_keys=%s",
                len(ops), used_fallback, (list(ops[0].keys()) if ops else []))

    sent = 0
    for op in ops:
        if isinstance(op, dict) and "op" in op:
            send_addin_block_group(group, op)
            sent += 1
    log.warning("DocOps sent_ops=%d", sent)
    return sent

def send_llm_answer_to_addin(email: str, raw_text: str) -> int:
    """Удобная обёртка: конвертируем email → group и вызываем handle_llm_answer."""
    grp = group_for_email(email)
    return handle_llm_answer(raw_text, grp)