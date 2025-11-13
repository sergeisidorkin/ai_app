import json, re, os, logging
import uuid
from uuid import UUID, uuid4

from io import BytesIO
from docx import Document
from importlib import import_module
from django.core.cache import cache
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from django.conf import settings
from openai import OpenAI


from googledrive_app.service import get_access_token as gdrive_get_access_token
from googledrive_app.service import list_children as gdrive_list_children
from googledrive_app.service import download_file as gdrive_download_file

from .forms import BlockForm
from .models import Block

import office_addin.utils as addin_utils

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from office_addin.utils import group_for_email
from office_addin.utils import send_text_as_paragraphs

from docops_app.structured import extract_docops_control, synthesize_docops_from_text
from docops_app.ir import program_from_dict
from docops_app.compile_addin import compile_to_addin_blocks
from docops_app.pipeline import process_answer_through_pipeline

from macroops_app.service import (
    docops_to_addin_job,
    deliver_addin_job,
    snapshot_for_log,
    push_addin_job_via_ws,
    enqueue_addin_job,
)

from policy_app.models import Product, TypicalSection
from requests_app.models import RequestTable, RequestItem

from onedrive_app.models import OneDriveSelection, OneDriveAccount
from onedrive_app.graph import (
    download_item_bytes,
    upload_item_bytes,
    list_children as od_list_children,
    upload_new_file_in_folder,
)
from onedrive_app.service import resolve_doc_info, ensure_share_link_for_doc

from logs_app.utils import new_trace_id
from logs_app import utils as plog


# === OpenAI service (импорт + надёжные заглушки) ===
try:
    from openai_app.models import OpenAIAccount
except Exception:
    OpenAIAccount = None  # чтобы не было NameError

try:
    from openai_app.service import (
        get_client as get_openai_client_for,
        get_available_models,
        run_prompt,
        run_prompt_with_files,
    )
    HAS_OPENAI_SERVICE = True
except Exception:
    # Надёжные заглушки, чтобы не падать при отсутствии openai_app.service
    HAS_OPENAI_SERVICE = False
    from openai import OpenAI
    import io
    def get_openai_client_for(user):
        try:
            org = getattr(settings, "OPENAI_ORG_ID", "") or os.environ.get("OPENAI_ORG_ID") or ""
            kwargs = {}
            if org:
                kwargs["organization"] = org  # ← ключевой момент
            # при необходимости можно также пробросить кастомный base_url
            api_base = getattr(settings, "OPENAI_BASE_URL", "") or getattr(settings, "OPENAI_API_BASE", "")
            if api_base:
                kwargs["base_url"] = api_base
            return OpenAI(**kwargs)
        except Exception:
            return None
    def get_available_models(user):
        return []
    def _responses_call(model, prompt, file_ids=None, temperature=None):
        client = OpenAI()
        content = [{"type": "input_text", "text": prompt}]
        for fid in (file_ids or []):
            content.append({"type": "input_file", "file_id": fid})
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": content}],
            **({"temperature": float(temperature)} if temperature is not None else {}),
        )
        return getattr(r, "output_text", "") or ""
    def run_prompt(user, model, prompt, temperature=None):
        return _responses_call(model, prompt, file_ids=None, temperature=temperature)
    def run_prompt_with_files(user, model, prompt, attachments, temperature=None):
        # attachments: List[Tuple[str, bytes]]
        client = OpenAI()
        file_ids = []
        for name, data in (attachments or []):
            up = client.files.create(
                file=(name or "file.bin", io.BytesIO(data)),
                purpose="assistants",
            )
            file_ids.append(up.id)
        return _responses_call(model, prompt, file_ids=file_ids, temperature=temperature)

def _one_docx_in_folder_or_error(user, folder_id):
    """
    Возвращает ('ok', <item_id>) если в папке ровно один .docx (исключая временные ~$.docx).
    Иначе ('err', <сообщение>).
    """
    try:
        jd = od_list_children(user, folder_id)
        items = jd.get("value", [])
    except Exception:
        items = []

    docx_items = [
        it for it in items
        if not it.get("folder")
        and isinstance(it.get("name"), str)
        and it["name"].lower().endswith(".docx")
        and not it["name"].startswith("~$")  # игнорим временные файлы Office
    ]

    if not docx_items:
        return ("err", "В выбранной папке OneDrive не найден ни один .docx. "
                       "Выберите конкретный .docx в «Подключениях» или оставьте в папке ровно один .docx.")
    if len(docx_items) > 1:
        names = ", ".join(it.get("name") or "безымянный" for it in docx_items[:5])
        return ("err", "В выбранной папке OneDrive найдено несколько .docx. "
                       "Оставьте один .docx или выберите конкретный файл. Найдены: " + names)
    return ("ok", docx_items[0]["id"])

def _latinize(s: str) -> str:
    """
    Грубая транслитерация похожих кириллических букв в латиницу для кодов RU/KZ и пр.
    """
    if not s:
        return ""
    m = {
        "А":"A","В":"B","Е":"E","К":"K","М":"M","Н":"H","О":"O","Р":"P",
        "С":"C","Т":"T","У":"Y","Х":"X","З":"Z","Ё":"E","Й":"I","Ї":"I",
        "І":"I","Ў":"Y","Ѓ":"G","Ќ":"K","Ћ":"C","Ђ":"D","Џ":"J",
    }
    return "".join(m.get(ch, ch) for ch in s)

def _extract_project_code6(raw: str) -> str:
    """
    Извлекает код вида 4444RU из произвольной строки:
    поддерживает варианты '4444RU', '4444-RU', '4444 RU', '4444_ru',
    кириллицу 'КЗ' -> 'KZ', лишние пробелы и т.п.
    Возвращает '4444RU' либо ''.
    """
    if not raw:
        return ""
    U = _latinize(raw).upper()
    # 1) точное вхождение
    m = re.search(r"\b(\d{4}[A-Z]{2})\b", U)
    if m:
        return m.group(1)
    # 2) через разделители (4444-RU / 4444 RU / 4444.RU / 4444_RU)
    m = re.search(r"\b(\d{4})\s*[-_. ]\s*([A-Z]{2})\b", U)
    if m:
        return m.group(1) + m.group(2)
    # 3) первые 6 алфанумериков
    first6 = re.sub(r"[^0-9A-Z]+", "", U)[:6]
    if re.fullmatch(r"\d{4}[A-Z]{2}", first6 or ""):
        return first6
    return ""

def _project_label_by_id(pid: str) -> str:
    """
    Пытаемся получить подпись проекта по его id.
    Вернём '' если модель недоступна или не нашли.
    """
    if not pid:
        return ""

    # 1) Основной путь — модель Project
    try:
        from projects_app.models import Project  # мягкая зависимость
        pr = Project.objects.filter(pk=pid).first()
        if pr:
            for attr in ("label", "name", "title"):
                v = getattr(pr, attr, None)
                if v:
                    return str(v)
            return str(pr)
    except Exception:
        pass  # модели может не быть — это ок

    # 2) Фолбэк — динамический импорт утилиты (без жёсткой ссылки для IDE)
    try:
        mod = import_module("debugger_app.utils")
        get_project_label = getattr(mod, "get_project_label", None)
        if callable(get_project_label):
            return get_project_label(pid) or ""
    except Exception:
        pass

    # 3) Ничего не нашли
    return ""

def _get_last_nonempty(qd, key: str) -> str:
    try:
        vals = qd.getlist(key)
    except Exception:
        vals = []
    for v in reversed(vals):
        if v not in (None, "", []):
            return str(v)
    return ""

def _folder_code6_from_name(name: str) -> str:
    """
    Нормализует имя папки Google Drive до кода (первые 6 алфанумериков после латинизации).
    """
    if not name:
        return ""
    U = _latinize(name).upper()
    cleaned = re.sub(r"[^0-9A-Z]+", "", U)
    return cleaned[:6]

logger = logging.getLogger(__name__)  # можно настроить уровень/handler в settings.LOGGING

# ──────────────────────────────────────────────────────────────────────────────
# Хелперы диагностики/извлечения project_code на СЕРВЕРЕ
# ──────────────────────────────────────────────────────────────────────────────
def _extract_project_code6_from_label(label: str) -> str:
    """
    Извлекает 4444RU/5555KZ из произвольной подписи проекта (серверный дубль логики из браузера).
    Поддерживаем "4444RU", "4444-RU", "4444 RU".
    """
    s = (label or "").strip().upper()
    if not s:
        return ""
    m = re.search(r"\b(\d{4}[A-Z]{2})\b", s)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4})\s*[-_. ]\s*([A-Z]{2})\b", s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    first6 = re.sub(r"[^0-9A-Z]+", "", s)[:6]
    return first6 if re.fullmatch(r"\d{4}[A-Z]{2}", first6) else ""

def _extract_project_code6_server(request) -> tuple[str, dict]:
    """
    Пытается достать код проекта 4444RU из разных источников запроса.
    Возвращает (code6, debug_info_dict).
    Не зависит жёстко от наличия модели Project.
    """
    # снимки POST/GET

    post = {k: (request.POST.getlist(k) if len(request.POST.getlist(k)) > 1 else request.POST.get(k))
            for k in request.POST.keys()}
    get_ = {k: (request.GET.getlist(k) if len(request.GET.getlist(k)) > 1 else request.GET.get(k))
            for k in request.GET.keys()}

    raw_body = ""
    try:
        if request.method == "POST":
            raw_body = request.body[:2048].decode("utf-8", "ignore")
    except Exception:
        pass

    # то, что прямо пришло
    label = (request.POST.get("project_label")
             or request.GET.get("project_label")
             or "").strip()
    code = (request.POST.get("project_code")
            or request.GET.get("project_code")
            or "").strip().upper()
    proj_id = (request.POST.get("project_id")
               or request.GET.get("project_id")
               or "").strip()

    computed_from_label = ""
    computed_from_pid = ""

    # 1) если code пуст — пробуем вытащить из label
    if not code and label:
        extracted = _extract_project_code6_from_label(label)
        if extracted:
            code = extracted
            computed_from_label = extracted

    # 2) если всё ещё пусто — мягко пробуем по project_id (если в твоём проекте есть такая модель)
    if not code and proj_id:
        try:
            from projects_app.models import Project  # мягкая зависимость
            p = Project.objects.filter(pk=proj_id).first()
            if p:
                # попробуем собрать подпись и вытащить из неё 4444RU
                cand_label = getattr(p, "label", None)
                if not cand_label:
                    prod_short = getattr(getattr(p, "product", None), "short_name", "") or ""
                    cand_label = f"{getattr(p, 'code', '')} {prod_short} {getattr(p, 'name', '')}".strip()
                extracted2 = _extract_project_code6_from_label(cand_label or "")
                if extracted2:
                    code = extracted2
                    computed_from_pid = extracted2
        except Exception:
            # никакого Project — просто пропускаем
            pass

    dbg = {
        "method": request.method,
        "path": request.path,
        "content_type": request.META.get("CONTENT_TYPE", ""),
        "post_keys": list(request.POST.keys()),
        "get_keys": list(request.GET.keys()),
        "recv_project_code": (request.POST.get("project_code") or request.GET.get("project_code") or ""),
        "recv_project_label": label,
        "recv_project_id": proj_id,
        "computed_code_from_label": computed_from_label,
        "computed_code_from_project_id": computed_from_pid,
        "POST_snapshot": post,
        "GET_snapshot": get_,
        "raw_body_2k": raw_body,
    }
    return code, dbg

def _get_block_code(block) -> str:
    """
    Возвращает значение поля «Код» из блока.
    Если поля нет/пусто — вернёт '' (без фолбэков).
    """
    try:
        v = (getattr(block, "code", "") or "").strip()
        return v
    except Exception:
        return ""

def _anchor_for_block(block) -> dict | None:
    """
    Формирует anchor-объект для addin.job:
      {"text": "< {Код}"}
    Если «Код» пуст — вернёт None (якорь не добавляем).
    """
    code = _get_block_code(block)
    if not code:
        return None
    return {"text": f"< {code}"}














def _llm_choices_for(user):
    # Всегда пробуем получить список (service сам решит — ENV или БД)
    try:
        models = get_available_models(user) or []
    except Exception:
        models = []
    return [(m, m) for m in models]

def _extract_project_from_request(request):
    code = (request.POST.get("project_code") or "").strip().upper()
    label = (request.POST.get("project_label") or "").strip()

    U = label.upper()
    if not code and U:
        m = re.search(r"\b(\d{4}[A-Z]{2})\b", U)
        if m:
            code = m.group(1)
    if not code and U:
        m = re.search(r"\b(\d{4})\s*[-_. ]\s*([A-Z]{2})\b", U)
        if m:
            code = (m.group(1) + m.group(2)).upper()
    if not code and U:
        first6 = re.sub(r"[^0-9A-Z]+", "", U)[:6]
        if re.fullmatch(r"\d{4}[A-Z]{2}", first6):
            code = first6

    return code, label


def _redirect_after(request, default_tab="templates"):
    nxt = (request.POST.get("next") or request.GET.get("next") or "").strip()
    return redirect(nxt or (reverse("home") + f"#{default_tab}"))

def _iter_paragraphs(parent):
    """
    Итерируем ВСЕ абзацы в документе: и в теле, и внутри таблиц рекурсивно.
    parent: Document или _Cell
    """
    # абзацы на текущем уровне
    for p in getattr(parent, "paragraphs", []):
        yield p
    # таблицы на текущем уровне
    for tbl in getattr(parent, "tables", []):
        for row in tbl.rows:
            for cell in row.cells:
                # рекурсия внутрь ячейки
                for p in _iter_paragraphs(cell):
                    yield p

def _insert_paragraph_after(paragraph: Paragraph, text: str):
    """
    Вставляет НОВЫЙ абзац сразу после данного paragraph
    (работает и в теле документа, и внутри ячейки таблицы).
    """
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)            # вставка на уровне oxml
    new_para = Paragraph(new_p, paragraph._parent)
    if text:
        new_para.add_run(text)
    return new_para


def _posted_model(request, form=None) -> str:
    """
    Достаём выбранную модель из формы, если поле есть,
    иначе — напрямую из POST. Возвращаем строку.
    """
    # сначала пробуем cleaned_data (если поле объявлено в форме)
    try:
        if form is not None and hasattr(form, "fields") and "model" in form.fields:
            val = form.cleaned_data.get("model", "")
            return (val or "").strip() if isinstance(val, str) else (val or "")
    except Exception:
        pass
    # иначе — из POST
    return (request.POST.get("model") or "").strip()

def _posted_temperature(request, form=None):
    """
    Возвращает float в диапазоне [0,2] или None, если поле пустое/некорректное.
    Берём из form.cleaned_data, если поле объявлено в форме,
    иначе — напрямую из POST.
    """
    # form.cleaned_data (если поле есть в форме)
    try:
        if form is not None and hasattr(form, "fields") and "temperature" in form.fields:
            val = form.cleaned_data.get("temperature", None)
            if val in ("", None):
                return None
            try:
                f = float(val)
                if 0.0 <= f <= 2.0:
                    return f
            except Exception:
                return None
    except Exception:
        pass

    # иначе — из POST
    raw = (request.POST.get("temperature") or "").strip()
    if raw == "":
        return None
    try:
        f = float(raw.replace(",", "."))  # на всякий случай поддержим запятую
        return f if 0.0 <= f <= 2.0 else None
    except Exception:
        return None

@login_required
def dashboard_partial(request):
    """
    Фрагмент для вкладки «Шаблоны» на домашней странице.
    Фильтры:
      ?product=<SHORT_NAME in UPPER>
      ?section=<SECTION_ID>
    """
    # Форма с моделями (как было)
    try:
        form = BlockForm(model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm()

    llm_models = [v for v, _ in _llm_choices_for(request.user)]

    # Фильтры по продукту/разделу
    product_short = (request.GET.get("product") or "").strip().upper()
    section_id = (request.GET.get("section") or "").strip()

    qs = Block.objects.select_related("product", "section").order_by("-id")
    if product_short:
        qs = qs.filter(product__short_name__iexact=product_short)
    if section_id:
        qs = qs.filter(section_id=section_id)

    # --- опции для мультиселекта «Контекст» (из таблицы «Запросы») ---
    context_options: list[tuple[str, str]] = []  # (value=id, label="Код-№ Краткое")
    id2label: dict[str, str] = {}
    label2id: dict[str, str] = {}

    try:
        if product_short and section_id:
            req_qs = (
                RequestItem.objects
                .filter(table__product__short_name__iexact=product_short,
                        table__section_id=section_id)
                .select_related("table__section")
                .order_by("position", "id")
            )
            for ri in req_qs:
                sec_code = getattr(getattr(ri.table, "section", None), "code", "") or ""
                num = f"{ri.number:02d}" if ri.number is not None else ""
                short = (ri.short_name or ri.name or "").strip()
                label = f"{sec_code}-{num} {short}".strip()
                vid = str(ri.pk)
                context_options.append((vid, label))
            id2label = {vid: label for vid, label in context_options}
            label2id = {label: vid for vid, label in context_options}
    except Exception:
        pass  # пустые списки — просто не будет опций

    # Превращаем в список и навешиваем вычисляемые поля
    blocks = list(qs)
    for b in blocks:
        raw = (b.context or "").strip()
        labels: list[str] = []

        if raw.startswith("["):
            # новый формат: JSON-массив строк
            try:
                arr = json.loads(raw)
                labels = [str(x).strip() for x in (arr or []) if str(x).strip()]
            except Exception:
                labels = [raw] if raw else []
        elif raw.isdigit() and raw in id2label:
            # старый формат: хранился id
            labels = [id2label[raw]]
        elif raw:
            # старый формат: одиночная строка
            labels = [raw]

        # что показывать на карточке
        b.context_display = ", ".join(labels) if labels else "— Не выбрано —"
        # какие значения предвыбрать в мультиселекте (id'шники)
        b.context_ids_for_edit = [label2id.get(lbl, "") for lbl in labels if label2id.get(lbl, "")]
        # также пригодится «сырой список» (если вдруг нужно)
        b.context_labels = labels

    selection = OneDriveSelection.objects.filter(user=request.user).first()
    onedrive_connected = OneDriveAccount.objects.filter(user=request.user).exists()
    openai = OpenAIAccount.objects.filter(user=request.user).first() if OpenAIAccount else None

    tab = (request.GET.get("tab") or "").lower()
    next_url = reverse("home") + ("#debugger" if tab == "debugger" else "#templates")

    return render(
        request,
        "blocks_app/dashboard_partial.html",
        {
            "blocks": blocks,
            "form": form,
            "llm_models": llm_models,
            "selection": selection,
            "onedrive_connected": onedrive_connected,
            "openai": openai,
            "context_options": context_options,
            "next_url": next_url,
            "is_debugger": (tab == "debugger"),  # ← вот
        },
    )


def _request_context_options(product_short: str, section_id: str):
    if not product_short or not section_id:
        return []
    from policy_app.models import Product
    prod = Product.objects.filter(short_name__iexact=product_short.strip()).first()
    if not prod:
        return []
    tbl = RequestTable.objects.filter(product=prod, section_id=section_id).first()
    if not tbl:
        return []
    opts = []
    for it in RequestItem.objects.filter(table=tbl).order_by("position", "id"):
        num = f"{it.number:02d}" if it.number is not None else ""
        code = (it.code or "").strip()
        short = (it.short_name or "").strip()
        # формат: "№, Код, Краткое наименование" — в одну строку, без «Наименование»
        label = " — ".join([p for p in (num, code, short) if p])
        # пишем в Block.context ровно эту строку
        opts.append({"value": label, "label": label})
    return opts

def _binding_from_request(request):
    """
    Возвращает (product, section), читая сначала из POST hidden полей
    product_id/section_id, а если их нет — из GET-параметров product (short_name)
    и section (id).
    """
    product_id = (request.POST.get("product_id") or request.GET.get("product_id") or "").strip()
    section_id = (request.POST.get("section_id") or request.GET.get("section_id") or "").strip()

    product_short = (request.POST.get("product") or request.GET.get("product") or "").strip().upper()
    section_qs    = (request.POST.get("section") or request.GET.get("section") or "").strip()

    product = None
    section = None

    if product_id:
        product = Product.objects.filter(id=product_id).first()
    elif product_short:
        product = Product.objects.filter(short_name__iexact=product_short).first()

    if section_id:
        section = TypicalSection.objects.filter(id=section_id).first()
    elif section_qs:
        section = TypicalSection.objects.filter(id=section_qs).first()

    return product, section

@login_required
def block_create(request):
    if request.method != "POST":
        return _redirect_after(request, default_tab="debugger")

    try:
        form = BlockForm(request.POST, model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm(request.POST)

    if form.is_valid():
        obj = form.save(commit=False)

        # Модель/температура (как было)
        mdl = _posted_model(request, form)
        if hasattr(obj, "model"):
            obj.model = mdl
        temp = _posted_temperature(request, form)
        if hasattr(obj, "temperature"):
            obj.temperature = temp

        # Привязка к продукту/разделу: читаем из POST, либо из GET (fallback)
        prod, sect = _binding_from_request(request)
        if prod is not None:
            obj.product = prod
        if sect is not None:
            obj.section = sect

        # --- Контекст: мультивыбор -> JSON-массив "Код-№ Краткое" ---
        selected_ids = request.POST.getlist("context")  # ['12','15',...]
        labels: list[str] = []
        if selected_ids:
            try:
                reqs = (
                    RequestItem.objects
                    .filter(pk__in=selected_ids)
                    .select_related("table__section")
                )
                # сохранить порядок как в selected_ids
                by_id = {str(r.pk): r for r in reqs}
                for sid in selected_ids:
                    ri = by_id.get(str(sid))
                    if not ri:
                        continue
                    sec_code = getattr(getattr(ri.table, "section", None), "code", "") or ""
                    num = f"{ri.number:02d}" if ri.number is not None else ""
                    short = (ri.short_name or ri.name or "").strip()
                    labels.append(f"{sec_code}-{num} {short}".strip())
            except Exception:
                pass
        obj.context = json.dumps(labels, ensure_ascii=False)

        obj.save()
        messages.success(request, "Блок сохранён.")
    else:
        messages.error(request, "Проверьте форму — есть ошибки.")
    return _redirect_after(request, default_tab="debugger")

@login_required
def block_update(request, pk: int):
    if request.method != "POST":
        return _redirect_after(request, default_tab="debugger")

    block = get_object_or_404(Block, pk=pk)

    try:
        form = BlockForm(request.POST, instance=block, model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm(request.POST, instance=block)

    if form.is_valid():
        obj = form.save(commit=False)

        # --- Контекст: мультивыбор -> JSON-массив "Код-№ Краткое" ---
        selected_ids = request.POST.getlist("context")
        labels: list[str] = []
        if selected_ids:
            try:
                reqs = (
                    RequestItem.objects
                    .filter(pk__in=selected_ids)
                    .select_related("table__section")
                )
                by_id = {str(r.pk): r for r in reqs}
                for sid in selected_ids:
                    ri = by_id.get(str(sid))
                    if not ri:
                        continue
                    sec_code = getattr(getattr(ri.table, "section", None), "code", "") or ""
                    num = f"{ri.number:02d}" if ri.number is not None else ""
                    short = (ri.short_name or ri.name or "").strip()
                    labels.append(f"{sec_code}-{num} {short}".strip())
            except Exception:
                pass
        obj.context = json.dumps(labels, ensure_ascii=False)

        # Модель/температура (как было)
        mdl = _posted_model(request, form)
        if hasattr(obj, "model"):
            obj.model = mdl
        temp = _posted_temperature(request, form)
        if hasattr(obj, "temperature"):
            obj.temperature = temp

        # Привязка к продукту/разделу: POST/GET
        prod, sect = _binding_from_request(request)
        if prod is not None:
            obj.product = prod
        if sect is not None:
            obj.section = sect

        obj.save()
        messages.success(request, "Изменения сохранены.")
    else:
        messages.error(request, "Проверьте форму — есть ошибки.")
    return _redirect_after(request, default_tab="debugger")


@require_POST
@login_required
def block_delete(request, pk):
    block = get_object_or_404(Block, pk=pk)
    name = block.name or block.code
    block.delete()
    messages.success(request, f"Блок «{name}» удалён.")
    return _redirect_after(request, default_tab="debugger")

@require_POST
@login_required
def block_set_model(request, pk):
    """
    Сохранение выбранной модели из выпадающего меню «Модель» на карточке блока.
    Просто перезаписываем Block.model в БД.
    """
    block = get_object_or_404(Block, pk=pk)
    model = (request.POST.get("model") or "").strip()
    block.model = model
    block.save(update_fields=["model"])
    messages.success(
        request,
        f"Модель для «{block.name or block.code}» установлена: {block.model or '—'}."
    )
    return _redirect_after(request, default_tab="debugger")


def _extract_context_labels(block) -> list[str]:
    """
    Возвращает список имён запросов для блока (то, что хранится в JSON в Block.context).
    """
    raw = (block.context or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            return [str(x).strip() for x in (arr or []) if str(x).strip()]
        except Exception:
            return [raw]
    return [raw]  # старые форматы (одна строка, либо id как строка)

def _is_folder_mime(mt: str) -> bool:
    return (mt or "").lower() == "application/vnd.google-apps.folder"

def _gdrive_list_children_safe(request, folder_id: str, res_key: str = "") -> list[dict]:
    try:
        items = gdrive_list_children(request, folder_id, res_key) or []
        return items
    except Exception:
        return []

def _find_project_folder_in_gdrive(request, base_folder_id: str, res_key: str, project_code6: str):
    """
    Среди дочерних папок base_folder ищем те, у которых нормализованный префикс (первые 6)
    совпадает с нормализованным кодом проекта (4444RU и т.п.).
    """
    children = _gdrive_list_children_safe(request, base_folder_id, res_key)
    if not children:
        raise ValueError("Выбран файл или пустая папка Google Drive. Выберите папку с проектами в «Подключения».")
    pc = _extract_project_code6(project_code6)  # повторная нормализация на всякий
    if not pc:
        raise ValueError("Не удалось определить номер проекта (формат 4444RU/5555KZ).")

    matched = []
    for ch in children:
        if not _is_folder_mime(ch.get("mimeType")):
            continue
        name = (ch.get("name") or "")
        code = _folder_code6_from_name(name)
        if code == pc:
            matched.append(ch)

    if not matched:
        raise ValueError("Проект не найден")
    if len(matched) > 1:
        raise ValueError("Найдено несколько папок с выбранным номером проекта")
    return matched[0]

def _find_child_folder_by_name(request, parent_id: str, res_key: str, name: str):
    """
    Ищем дочернюю папку с exact-совпадением имени (без регистра).
    Возвращаем dict или None.
    """
    if not name:
        return None
    target = (name or "").strip().lower()
    for ch in _gdrive_list_children_safe(request, parent_id, res_key):
        nm = (ch.get("name") or "").strip().lower()
        if _is_folder_mime(ch.get("mimeType")) and nm == target:
            return ch
    return None

def _collect_files_from_request_folders(
    request,
    root_folder_id: str,
    res_key: str,
    request_names: list[str],
    max_files=80,
    max_each_bytes=25 * 1024 * 1024,
    *,
    return_meta: bool = False,
    root_folder_name: str = "",
):
    """
    Возвращает:
      - если return_meta=False: [(name, data, mime)]
      - если return_meta=True:  ([(name, data, mime)], meta_list)
        где meta_list: [{"id","name","mime","web_link","gdrive_path"}]
    """
    names_set = {(n or "").strip().lower() for n in (request_names or []) if str(n).strip()}
    if not names_set:
        return ([], []) if return_meta else []

    def list_children(fid):  # локальная обёртка
        return _gdrive_list_children_safe(request, fid, res_key)

    # --- helpers -------------------------------------------------------------
    def _join_path(parts: list[str]) -> str:
        # унифицированный путь: всегда через '/'
        return "/".join([ (p or "").strip("/\\") for p in parts if p ])

    meta = []  # только если return_meta=True будем наполнять

    def _push_meta(fid: str, orig_name: str, mime_hint: str, stack: list[str]):
        if not return_meta:
            return
        gdrive_path = _join_path(stack + [orig_name])
        web_link = f"https://drive.google.com/file/d/{fid}/view?usp=drive_link"
        meta.append({
            "id": fid,
            "name": orig_name,
            "mime": (mime_hint or ""),
            "web_link": web_link,
            "gdrive_path": gdrive_path,   # ← ВСЕГДА через '/'
        })
    # ------------------------------------------------------------------------

    # 1) найти папки запросов (только прямые дети)
    req_folders = []
    for ch in list_children(root_folder_id):
        if not _is_folder_mime(ch.get("mimeType")):
            continue
        nm = (ch.get("name") or "").strip().lower()
        if nm in names_set:
            req_folders.append(ch)

    if not req_folders:
        return ([], []) if return_meta else []

    files_out: list[tuple[str, bytes, str]] = []

    def add_file(fid: str, name: str, mime_hint: str, stack: list[str]):
        try:
            mt = (mime_hint or "").lower()
            if mt == "application/pdf" or name.lower().endswith(".pdf") or mt.startswith("application/vnd.google-apps."):
                _mt, data = gdrive_download_file(request, fid, "application/pdf", res_key)
                if len(data) <= max_each_bytes:
                    files_out.append((name if name.lower().endswith(".pdf") else f"{name}.pdf", data, "application/pdf"))
                    _push_meta(fid, name if name.lower().endswith(".pdf") else f"{name}.pdf", "application/pdf", stack)
                return
            if mt.startswith("image/"):
                _mt, data = gdrive_download_file(request, fid, mt, res_key)
                if len(data) <= max_each_bytes:
                    files_out.append((name, data, mt))
                    _push_meta(fid, name, mt, stack)
                return
            if mt in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain", "text/markdown", "text/csv", "application/json",
            ) or name.lower().endswith((".docx", ".txt", ".md", ".csv", ".json")):
                prefer = mt or "application/octet-stream"
                _mt, data = gdrive_download_file(request, fid, prefer, res_key)
                if len(data) <= max_each_bytes:
                    files_out.append((name, data, prefer))
                    _push_meta(fid, name, prefer, stack)
                return
        except Exception:
            pass

    def walk(folder_id: str, stack: list[str]):
        if len(files_out) >= max_files:
            return
        for ch in list_children(folder_id):
            if _is_folder_mime(ch.get("mimeType")):
                walk(ch.get("id"), stack + [(ch.get("name") or ch.get("id"))])
                if len(files_out) >= max_files:
                    return
            else:
                add_file(
                    ch.get("id"),
                    ch.get("name") or ch.get("id"),
                    ch.get("mimeType") or "",
                    stack
                )
                if len(files_out) >= max_files:
                    return

    # стартовый стек: корень (опционально) + папка запроса
    root_stack = [root_folder_name] if root_folder_name else []
    for rf in req_folders:
        if len(files_out) >= max_files:
            break
        walk(rf.get("id"), root_stack + [(rf.get("name") or rf.get("id"))])

    if return_meta:
        return files_out, meta
    return files_out


def _group_for_email(email: str) -> str:
    e = (email or "").strip().lower().replace("@", ".")
    e = re.sub(r"[^0-9a-zA-Z_.-]+", "-", e)
    return f"user_{e}"[:90]

# Универсальная постановка addin.job в очередь с авто-адаптацией аргументов
def _enqueue_addin_job_compat(email: str, job: dict, doc_url: str, priority: int = 10):
    """
    Пытается вызвать macroops_app.service.enqueue_addin_job с подходящими именами аргументов.
    Передаёт ТОЛЬКО те ключи, которые есть у функции.
    """
    import inspect

    try:
        params = set(inspect.signature(enqueue_addin_job).parameters.keys())
    except Exception:
        params = set()

    kwargs = {}

    # получатель (если предусмотрен)
    for name in ("email", "user_email", "recipient", "to", "group", "group_name", "channel"):
        if name in params:
            kwargs[name] = email
            break

    # контейнер задания
    if "job" in params:
        kwargs["job"] = job
    elif "payload" in params:
        kwargs["payload"] = job
    elif "ops" in params:
        kwargs["ops"] = job.get("ops", [])
    else:
        kwargs["job"] = job  # дефолт

    # ссылка на документ
    for name in ("doc_url", "docUrl", "url", "doc", "document_url"):
        if name in params:
            kwargs[name] = doc_url
            break

    # приоритет
    for name in ("priority", "prio", "p"):
        if name in params:
            kwargs[name] = priority
            break

    return enqueue_addin_job(**kwargs)








@require_POST
@login_required
def block_run(request, pk):
    block = get_object_or_404(Block, pk=pk)

    trace_id = new_trace_id()

    _raw_tid = trace_id
    try:
        UUID(str(_raw_tid))  # валидно?
    except Exception:
        trace_id = uuid4()  # заменить на валидный UUID
        # при желании сохранить старый для отображения:
        request.META["X-Client-Trace"] = str(_raw_tid)

    request_id = uuid.uuid4()

    via = (request.POST.get("via") or request.GET.get("via") or "ws").lower()
    if via not in ("ws", "queue"):
        via = "ws"

    plog.info(
        request.user, phase="request", event="block_run.start",
        message=f"Start block_run via={via}",
        trace_id=trace_id, request_id=request_id, via=via,
        data={
            "block_id": pk,
            "post_keys": list(request.POST.keys()),
            "get_keys": list(request.GET.keys()),
        }
    )

    anchor_obj = _anchor_for_block(block)  # {"text": "< HRM-1"} | None

    # Диагностика запроса
    try:
        _path = request.path
        _qs   = request.META.get("QUERY_STRING","")
        _ct   = request.META.get("CONTENT_TYPE","")
        _raw  = request.body[:2048].decode("utf-8","ignore") if request.body else ""
        logger.warning("block_run path=%s qs=%s ctype=%s raw_prefix=%r", _path, _qs, _ct, _raw)
    except Exception:
        pass

    # 1) Код проекта с полной серверной диагностикой
    code6, dbg = _extract_project_code6_server(request)
    logger.info("block_run recv debug: %s", dbg)
    plog.info(request.user, phase="extract", event="project_code6",
              message=f"code6={code6 or ''}",
              trace_id=trace_id, request_id=request_id,
              project_code6=code6 or "", data={"dbg": dbg})


    if not code6:
        # Фолбэк из сессии (если когда-то уже запускали)
        sess_code = (request.session.get("last_project_code6") or "").strip().upper()
        if re.fullmatch(r"\d{4}[A-Z]{2}", sess_code or ""):
            code6 = sess_code
            logger.warning("PROJECT CODE FALLBACK from session: %s", {
                "code6": code6,
                "label": request.session.get("last_project_label") or "",
                "product_short": request.session.get("last_product_short") or "",
            })

    # 2) Проверка OneDrive выбора
    sel = OneDriveSelection.objects.filter(user=request.user).first()
    if not sel or not sel.item_id:
        plog.warn(request.user, phase="onedrive", event="selection.missing",
                  message="OneDrive not connected", trace_id=trace_id,
                  request_id=request_id, project_code6=code6 or "")
        messages.error(request, "Сначала выберите файл или папку …")
        return _redirect_after(request, default_tab="debugger")
    else:
        plog.info(request.user, phase="onedrive", event="selection.ok",
                  message="OneDrive selection ok",
                  trace_id=trace_id, request_id=request_id,
                  project_code6=code6 or "",
                  data={"item_id": sel.item_id, "item_name": sel.item_name})

    # 3) Модель
    model_id = (block.model or "").strip()
    if not model_id:
        messages.error(request, "Не выбрана модель для блока. Выберите её в форме блока или через кнопку «Модель».")
        return _redirect_after(request, default_tab="debugger")

    # 4) Собираем промпт (+ контекст)
    full_prompt = (block.prompt or "").strip()
    labels_for_prompt = _extract_context_labels(block)
    if labels_for_prompt:
        full_prompt = "{}\n\n{}".format("\n".join(labels_for_prompt), full_prompt)

    plog.debug(request.user, phase="prompt", event="compose",
        message="Compose prompt + context",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "",
        data={"context_labels": _extract_context_labels(block)})

    # Лог с ПОЛНЫМ текстом промпта
    plog.debug(
        request.user, phase="prompt", event="compose.raw",
        message=f"prompt_len={len(full_prompt)}",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "",
        data={
            "prompt": full_prompt,
            "context_labels": labels_for_prompt,
        }
    )

    # 5) Проверка Google Drive подключения (корневая папка проектов)

    gsel = request.session.get("gdrive_selection") or {}
    base_folder_id = gsel.get("id") or ""
    res_key = gsel.get("res_key") or ""
    if not base_folder_id or not gdrive_get_access_token(request):
        messages.error(request, "Google Drive не подключён. Выберите папку в «Подключения».")
        return _redirect_after(request, default_tab="debugger")

    if not base_folder_id or not gdrive_get_access_token(request):
        plog.error(request.user, phase="gdrive", event="not_connected",
                   message="Google Drive not connected",
                   trace_id=trace_id, request_id=request_id,
                   project_code6=code6 or "")
        messages.error(request, "Google Drive не подключён …")
        return _redirect_after(request, default_tab="debugger")

    # 6) Валидация кода проекта
    if not code6 or not re.fullmatch(r"\d{4}[A-Z]{2}", code6):
        logger.warning("PROJECT CODE MISSING/INVALID in block_run: %s", dbg)
        messages.error(request, "Не удалось определить номер проекта (формат 4444RU/5555KZ).")
        return _redirect_after(request, default_tab="debugger")

    # 7) Папка проекта в GDrive
    try:
        project_folder = _find_project_folder_in_gdrive(request, base_folder_id, res_key, code6)
    except ValueError as e:
        messages.error(request, str(e))
        return _redirect_after(request, default_tab="debugger")

    # 8) Папка актива (если указана)
    asset_name = (request.POST.get("asset_name") or request.GET.get("asset_name") or "").strip()
    search_root = project_folder
    if asset_name:
        found_asset = _find_child_folder_by_name(request, project_folder.get("id"), res_key, asset_name)
        if found_asset:
            search_root = found_asset

    plog.info(request.user, phase="gdrive", event="project_folder.ok",
              message="Project folder resolved",
              trace_id=trace_id, request_id=request_id,
              project_code6=code6 or "",
              data={"project_folder": project_folder.get("name"),
                    "asset": asset_name or ""})

    # 9) Вложения из папок запросов (по именам из Block.context)
    request_names = _extract_context_labels(block)

    # Подготовим «отображаемое имя корня» для путей:
    #   <project_folder.name>\[asset]\...  → совпадает с тем, что ожидаем видеть в ссылках
    root_display_name = (project_folder.get("name") or "")
    if asset_name and search_root is not project_folder:
        # если актив выбран и уже углубились в него — добавим сегмент актива
        root_display_name = "/".join([p for p in (root_display_name, (search_root.get("name") or asset_name)) if p])

    attachments, attachments_meta = _collect_files_from_request_folders(
        request, search_root.get("id"), res_key, request_names,
        max_files=120, max_each_bytes=25 * 1024 * 1024,
        return_meta=True,
        root_folder_name=root_display_name,
    )

    # НОРМАЛИЗАЦИЯ ТОЛЬКО ДЛЯ ЛОГОВ: всегда одинарный '/' в пути
    def _normalize_path_slashes(p: str) -> str:
        return (p or "").replace("\\", "/")

    sanitized_meta = []
    for it in (attachments_meta or []):
        gpath = _normalize_path_slashes(it.get("gdrive_path") or "")
        sanitized_meta.append({**it, "gdrive_path": gpath})

    plog.info(
        request.user, phase="gdrive", event="attachments.meta",
        message="Attachments metadata",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "",
        data={"count": len(sanitized_meta), "samples": sanitized_meta[:10]}
    )

    # --- Каталог источников для промпта ---------------------------------
    def _build_sources_catalog(meta: list[dict], max_items: int = 40) -> str:
        items = sorted(meta, key=lambda x: ((x.get("gdrive_path") or ""), (x.get("name") or "")))
        lines = []
        for i, it in enumerate(items[:max_items], start=1):
            name = it.get("name") or ""
            path = it.get("gdrive_path") or ""
            link = it.get("web_link") or ""
            lines.append(f"[S{i}] {name} <{path} {link}>")
        if not lines:
            return ""
        omitted = max(0, len(meta) - max_items)
        tail = (f"\n… (ещё {omitted} не показаны)" if omitted else "")
        header = "Каталог источников (справочно; не копируй этот блок в ответ):"
        return header + "\n" + "\n".join(lines) + tail

    if sanitized_meta:
        sources_catalog = _build_sources_catalog(sanitized_meta, max_items=40)
        footnote_rules = (
            "\n\nПравила указания источников:\n"
            "— Используй только сноски: сразу после абзаца/пункта/ячейки добавь операцию "
            "{\"op\":\"footnote.add\",\"text\":\"{Наименование} <{Путь} {Ссылка}>\"}.\n"
            "— Подставляй значения дословно из каталога (ничего не меняй).\n"
            "— Не вставляй источники внутрь текстов операций. Максимум одна сноска на операцию и только при фактическом использовании источника.\n"
            "— Каталог выше служебный, его не нужно копировать в ответ.\n"
        )
        # дополняем уже собранный full_prompt
        full_prompt = f"{full_prompt}\n\n{sources_catalog}{footnote_rules}"
    # --------------------------------------------------------------------

    # 10) Вызов LLM

    try:
        client = get_openai_client_for(request.user)
        if client is None:
            messages.error(request, "OpenAI не подключён или не настроен API ключ.")
            return _redirect_after(request, default_tab="debugger")

        temperature = getattr(block, "temperature", None)

        FILE_MODELS = {"gpt-4o", "o4-mini", "o4"}
        model_for_files = model_id

        plog.info(request.user, phase="llm", event="call.start",
                  message=f"model={model_for_files}",
                  trace_id=trace_id, request_id=request_id,
                  project_code6=code6 or "",
                  data={"temperature": getattr(block, "temperature", None),
                        "attachments": len(attachments)})

        if attachments and model_id not in FILE_MODELS:
            messages.warning(request, f"Модель «{model_id}» может не поддерживать документы. Включаю «gpt-4o».")
            model_for_files = "gpt-4o"

        if attachments and run_prompt_with_files:
            answer = (run_prompt_with_files(
                request.user, model_for_files, full_prompt, attachments, temperature=temperature
            ) or "").strip()
        else:
            answer = (run_prompt(
                request.user, model_id, full_prompt, temperature=temperature
            ) or "").strip()

        if not answer:
            raise RuntimeError("Пустой ответ модели.")
    except Exception as e:

        try:
            detail = {}
            # OpenAI SDK часто прячет статус и тело ответа так:
            if hasattr(e, "status_code"): detail["status_code"] = e.status_code
            if hasattr(e, "response") and hasattr(e.response, "text"):
                detail["response_text"] = e.response.text[:1000]
            plog.error(request.user, phase="llm", event="call.failed",
                       message=str(e), data=detail)
        except Exception:
            pass

        emsg = str(e).lower()
        if ("temperature" in emsg) and ("unsupported" in emsg or "does not support" in emsg):
            messages.error(request,
                           "Выбранная температура не поддерживается этой моделью. Укажите 1.0 или оставьте пусто.")
        else:
            messages.error(request, f"Ошибка при обращении к LLM: {e}")
        return _redirect_after(request, default_tab="debugger")

    plog.info(request.user, phase="llm", event="call.done",
              message=f"answer_len={len(answer)}",
              trace_id=trace_id, request_id=request_id,
              project_code6=code6 or "")

    plog.debug(
        request.user, phase="llm", event="answer.raw",
        message=f"model={(model_for_files or model_id)} answer_len={len(answer)}",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "",
        data={"answer": answer}
    )

    # определяем email перед DocOps-втекой
    target_email = (request.POST.get("email") or request.user.email or "").strip()
    if not target_email:
        messages.error(request, "У текущего пользователя не указан email — некуда «доставлять».")
        return _redirect_after(request, default_tab="debugger")

    # --- 10.1 Привязка из панели «Отладка» + надёжные фолбэки ---

    def _last(qd, name):  # берём последнее непустое из списка (и для POST, и для GET)
        try:
            vals = qd.getlist(name)
        except Exception:
            vals = []
        for v in reversed(vals):
            if v not in (None, "", []):
                return str(v)
        return ""

    asset_name = (_last(request.POST, "asset_name") or _last(request.GET, "asset_name") or "").strip()
    section_id = (_last(request.POST, "section_id") or _last(request.GET, "section_id") or "").strip()
    section_code_param = (
                _last(request.POST, "section_code") or _last(request.GET, "section_code") or "").strip().upper()

    # фолбэк из сессии
    if not asset_name:
        asset_name = (request.session.get("dbg_asset_name") or "").strip()
    if not section_id:
        section_id = (request.session.get("dbg_section_id") or "").strip()
    if not section_code_param:
        section_code_param = (request.session.get("dbg_section_code") or "").strip().upper()

    # приоритет: присланный section_code → из БД по section_id → из блока → ""
    section_code = section_code_param
    if not section_code and section_id:
        try:
            sec = TypicalSection.objects.filter(pk=section_id).only("code").first()
            if sec and getattr(sec, "code", ""):
                section_code = sec.code.strip().upper()
        except Exception:
            pass
    if not section_code and getattr(block, "section_id", None):
        try:
            section_code = (getattr(block.section, "code", "") or "").strip().upper()
        except Exception:
            pass

    # сохраняем в сессию для последующих запусков
    if asset_name:
        request.session["dbg_asset_name"] = asset_name
    if section_id:
        request.session["dbg_section_id"] = section_id
    if section_code:
        request.session["dbg_section_code"] = section_code

    company = asset_name  # именно строка из «Актив:»

    # section_code = код раздела (две буквы, например HR) по section_id
    section_code = ""
    if section_id:
        try:
            sec = TypicalSection.objects.filter(pk=section_id).only("code").first()
            if sec and getattr(sec, "code", ""):
                section_code = sec.code.strip()
        except Exception:
            section_code = ""

    # Лог — что именно привязали из панели
    plog.info(
        request.user, phase="extract", event="context.bound",
        message=f"binding from panel company='{company}' section='{section_code}'",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "",
        data={"asset_name": asset_name, "section_id": section_id, "section_code": section_code}
    )

    # 1) Ищем документ и получаем раздаваемую ссылку редактирования (share_url)
    try:
        info = resolve_doc_info(
            request.user, sel, code6,
            company=(company or None),
            section=(section_code or None),
        )
        share_url = ensure_share_link_for_doc(
            request.user, info["driveId"], info["itemId"],
            prefer="organization", grant_emails=None
        )

    except Exception as e1:
        # Фолбэк (ровно один .docx в папке) + лог
        plog.warn(
            request.user, phase="onedrive", event="resolve.failed",
            message=f"resolve_doc_info failed: {e1}",
            trace_id=trace_id, request_id=request_id,
            project_code6=code6 or "",
            data={"company": company, "section_code": section_code}
        )
        status, item_id = _one_docx_in_folder_or_error(request.user, sel.item_id)
        if status != "ok":
            messages.error(request, f"Не удалось найти документ в OneDrive: {e1}")
            return _redirect_after(request, default_tab="debugger")

        drive_id = getattr(sel, "drive_id", "") or ""
        if not drive_id:
            try:
                jd = od_list_children(request.user, sel.item_id)
                for it in jd.get("value", []):
                    if it.get("id") == item_id and it.get("parentReference", {}).get("driveId"):
                        drive_id = it["parentReference"]["driveId"];
                        break
            except Exception:
                drive_id = ""

        if not drive_id:
            messages.error(request, "Не удалось определить driveId для выбранного документа в OneDrive.")
            return _redirect_after(request, default_tab="debugger")

        share_url = ensure_share_link_for_doc(
            request.user, drive_id, item_id,
            prefer="organization", grant_emails=None
        )

    doc_url = share_url
    if not doc_url:
        messages.error(request, "Не удалось сформировать ссылку на документ в OneDrive.")
        return _redirect_after(request, default_tab="debugger")

    plog.info(
        request.user, phase="onedrive", event="share_url.ok",
        message="Share URL resolved",
        trace_id=trace_id, request_id=request_id,
        project_code6=code6 or "", doc_url=doc_url,
        company=company or "", section=section_code or ""
    )

    pipe = process_answer_through_pipeline(
        answer,
        user=request.user,
        trace_id=trace_id,
        request_id=request_id,
        project_code6=code6 or "",
    )

    plog.info(request.user, phase="pipeline", event="result",
              message="pipeline result",
              trace_id=trace_id, request_id=request_id,
              project_code6=code6 or "",
              data={"valid": pipe.get("valid"),
                    "normalized": pipe.get("normalized"),
                    "source": pipe.get("source"),
                    "ops_count": len(pipe.get("docops", {}).get("ops", []))})

    if not pipe.get("valid"):

        plog.warn(request.user, phase="pipeline", event="invalid",
                  message=str(pipe.get("error") or "invalid"),
                  trace_id=trace_id, request_id=request_id,
                  project_code6=code6 or "")

        # если совсем не смогли привести к валидному DocOps — аккуратный фолбэк
        if via == "ws":
            # отправим как плоский текст (минимальная деградация)
            sent = send_text_as_paragraphs(target_email, answer, styleBuiltIn="Normal")
            messages.warning(request,
                             f"DocOps/IR невалиден ({pipe.get('error')}). Через WS отправлен обычный текст ({sent} абз.).")
            return _redirect_after(request, default_tab="debugger")
        else:
            messages.error(request, f"DocOps/IR невалиден ({pipe.get('error')}). В очередь положить нечего.")
            return _redirect_after(request, default_tab="debugger")

    docops_prog = pipe["program"]  # {type:"DocOps", version:"v1", ops:[...]}

    # Подготовим anchor сразу — чтобы компилятор знал о нём и отлогировал has_anchor
    anchor_obj = _anchor_for_block(block)  # он у тебя уже есть выше; можно переиспользовать или пересчитать

    # Передадим компилятору trace/email — тогда появятся логи compile/*
    meta_for_compile = {
        "source": f"block_run/{pipe.get('source')}",
        "normalized": bool(pipe.get("normalized")),
        "blockId": block.id,
        "model": model_id,
        "trace_id": str(trace_id),
        "email": (request.POST.get("email") or request.user.email or "").strip(),
    }

    # Сборка addin.job через macroops
    job = docops_to_addin_job(docops_prog, meta=meta_for_compile, anchor=anchor_obj)

    # Гарантируем meta и trace_id в самой job (для очереди/агента)
    job.setdefault("meta", {})
    job["meta"].setdefault("trace_id", str(trace_id))

    # якорь "< CODE" — если вы уже внедряли хелпер _make_anchor_for_block, просто используйте:
    anchor_text = f"< {(block.code or '').strip()}" if getattr(block, "code", None) else None
    if anchor_text:
        job.setdefault("anchor", {"text": anchor_text})

        plog.info(request.user, phase="job", event="build.ok",
                  message="addin.job built",
                  trace_id=trace_id, request_id=request_id,
                  project_code6=code6 or "", anchor_text=anchor_text or "",
                  data={"ops": len(job.get("ops", []))})

    else:
        # оставим как есть; якорь опционален
        pass

    try:
        snap = snapshot_for_log(job, max_ops=12, max_chars_per_op=160)
        plog.info(
            request.user, phase="job", event="build.summary",
            message=f"addin.job summary ops={snap['ops_count']}",
            trace_id=trace_id, request_id=request_id, via=via,
            project_code6=code6 or "", doc_url=doc_url,
            anchor_text=(job.get("anchor") or {}).get("text", ""),
            data=snap,
        )
    except Exception as e:
        plog.warn(
            request.user, phase="job", event="build.summary.failed",
            message=str(e),
            trace_id=trace_id, request_id=request_id, via=via,
            project_code6=code6 or ""
        )

    # --- 3) Доставка: один вызов без дублирования ---
    delivered_ok = False
    try:
        # Заполняем полезную мету — чтобы в очереди и на клиенте было видно «кто/что/куда»
        job.setdefault("meta", {})
        job["meta"].setdefault("doc_url", doc_url)
        job["meta"].setdefault("trace_id", str(trace_id))
        job["meta"].setdefault("requestedBy", {
            "id": getattr(request.user, "id", None),
            "username": getattr(request.user, "username", "") or "",
            "email": getattr(request.user, "email", "") or "",
        })
        job["meta"].setdefault("job_id", str(request_id))

        if via == "ws":
            # Пытаемся отправить цельным addin.job по WS
            try:
                grp = group_for_email(target_email)
                cache.set(f"ws:last_trace:{grp}", str(trace_id), 600)
                cache.set(f"ws:last_job:{grp}", str(request_id), 600)
                sent_ops = push_addin_job_via_ws(target_email, job, doc_url=doc_url,
                                                 user=request.user, trace_id=trace_id)
            except Exception:
                # фолбэк: шлём напрямую через Channels один пакет addin.job
                layer = get_channel_layer()
                async_to_sync(layer.group_send)(
                    group_for_email(target_email),
                    {
                        "type": "addin.job",
                        "job": job,
                        "docUrl": doc_url,
                        "jobId": str(request_id),
                        "traceId": str(trace_id),
                    },
                )
                sent_ops = len(job.get("ops", []))

            messages.success(request, f"Отправлено по WS как job (опс: {sent_ops}).")
            delivered_ok = True

        else:
            try:
                q_snap = snapshot_for_log(job, max_ops=8, max_chars_per_op=140)
                plog.debug(
                    request.user, phase="queue", event="payload",
                    message="Queue payload snapshot",
                    trace_id=trace_id, request_id=request_id, via="queue",
                    project_code6=code6 or "", doc_url=doc_url,
                    anchor_text=(job.get("anchor") or {}).get("text", ""),
                    data=q_snap,
                )
            except Exception as e:
                plog.warn(
                    request.user, phase="queue", event="payload.snapshot.failed",
                    message=str(e),
                    trace_id=trace_id, request_id=request_id, via="queue",
                    project_code6=code6 or ""
                )
            # queue: совместим разные версии enqueue_* (payload/job/ops)
            res = _enqueue_addin_job_compat(
                email=target_email,
                job=job,
                doc_url=doc_url,
                priority=10,
            )
            messages.success(request, f"Положено в очередь: {res}")
            delivered_ok = True

    except Exception as e:
        messages.error(request, f"Ошибка доставки ({via}): {e}")
        plog.error(
            request.user, phase="deliver", event="failed",
            message=str(e),
            trace_id=trace_id, request_id=request_id,
            via=via, project_code6=code6 or "", doc_url=doc_url,
            anchor_text=anchor_text or "", data={"exc": str(e)}
        )

    if delivered_ok:
        plog.info(
            request.user, phase="deliver", event="ok",
            message="delivery finished",
            trace_id=trace_id, request_id=request_id, via=via,
            project_code6=code6 or "", doc_url=doc_url,
            anchor_text=anchor_text or ""
        )

    return _redirect_after(request, default_tab="debugger")
