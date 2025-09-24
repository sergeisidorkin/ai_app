import json, re, logging
from io import BytesIO
from docx import Document
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from googledrive_app.service import get_access_token as gdrive_get_access_token
from googledrive_app.service import list_children as gdrive_list_children
from googledrive_app.service import download_file as gdrive_download_file

from .forms import BlockForm
from .models import Block

from policy_app.models import Product, TypicalSection
from requests_app.models import RequestTable, RequestItem

from onedrive_app.models import OneDriveSelection, OneDriveAccount
from onedrive_app.graph import (
    download_item_bytes,
    upload_item_bytes,
    list_children as od_list_children,
    upload_new_file_in_folder,     # ← добавим функцию в graph.py (см. п.2)
)

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
        # Минимальный клиент из ENV; вернёт None, если ключей нет
        try:
            return OpenAI()
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
    try:
        # Попробуй сначала так (если у тебя есть такая модель):
        from projects_app.models import Project  # поправь на свою
        pr = Project.objects.filter(id=pid).first()
        if not pr:
            return ""
        # Выбери поле, которое используется в option {{ opt.label }}
        # Если там хранится "4444RU DD Пример проекта", то это что-то вроде pr.label или pr.name
        # Ниже пробуем несколько вариантов:
        for attr in ("label", "name", "title"):
            if hasattr(pr, attr) and getattr(pr, attr):
                return str(getattr(pr, attr))
        return str(pr)
    except Exception:
        # Если другой модуль:
        try:
            from debugger_app.utils import get_project_label  # вдруг есть такой хелпер
            return get_project_label(pid) or ""
        except Exception:
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

def _collect_files_from_request_folders(request, root_folder_id: str, res_key: str, request_names: list[str],
                                        max_files=80, max_each_bytes=25 * 1024 * 1024) -> list[tuple[str, bytes, str]]:
    """
    На первом шаге: находим папки в root, названия которых совпадают с request_names (без регистра).
    Затем для каждой найденной папки рекурсивно собираем все файлы.
    Возвращает [(name, data, mime)], готовые для run_prompt_with_files.
    """
    names_set = { (n or "").strip().lower() for n in (request_names or []) if str(n).strip() }
    if not names_set:
        return []

    def list_children(fid):  # локальная обёртка
        return _gdrive_list_children_safe(request, fid, res_key)

    # 1) найти папки запросов (только прямые дети)
    req_folders = []
    for ch in list_children(root_folder_id):
        if not _is_folder_mime(ch.get("mimeType")):
            continue
        nm = (ch.get("name") or "").strip().lower()
        if nm in names_set:
            req_folders.append(ch)

    if not req_folders:
        return []

    # 2) рекурсивно собрать файлы из каждой такой папки
    out: list[tuple[str, bytes, str]] = []

    def add_file(fid: str, name: str, mime_hint: str):
        # правила скачивания (как в старом коде)
        try:
            mt = (mime_hint or "").lower()
            # Google-native или PDF → экспорт в PDF
            if mt == "application/pdf" or name.lower().endswith(".pdf") or mt.startswith("application/vnd.google-apps."):
                _mt, data = gdrive_download_file(request, fid, "application/pdf", res_key)
                if len(data) <= max_each_bytes:
                    out.append((name if name.lower().endswith(".pdf") else f"{name}.pdf", data, "application/pdf"))
                return
            # изображения
            if mt.startswith("image/"):
                _mt, data = gdrive_download_file(request, fid, mt, res_key)
                if len(data) <= max_each_bytes:
                    out.append((name, data, mt))
                return
            # текст/документы
            if mt in (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain", "text/markdown", "text/csv", "application/json",
            ) or name.lower().endswith((".docx", ".txt", ".md", ".csv", ".json")):
                prefer = mt or "application/octet-stream"
                _mt, data = gdrive_download_file(request, fid, prefer, res_key)
                if len(data) <= max_each_bytes:
                    out.append((name, data, prefer))
                return
            # иное — пропускаем
        except Exception:
            pass

    def walk(folder_id: str):
        nonlocal out
        if len(out) >= max_files:
            return
        for ch in list_children(folder_id):
            if _is_folder_mime(ch.get("mimeType")):
                walk(ch.get("id"))
                if len(out) >= max_files:
                    return
            else:
                add_file(ch.get("id"), ch.get("name") or ch.get("id"), ch.get("mimeType") or "")
                if len(out) >= max_files:
                    return

    for rf in req_folders:
        if len(out) >= max_files:
            break
        walk(rf.get("id"))

    return out


@require_POST
@login_required
def block_run(request, pk):
    block = get_object_or_404(Block, pk=pk)

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
        messages.error(request, "Сначала выберите файл или папку в OneDrive в разделе «Подключения».")
        return _redirect_after(request, default_tab="debugger")

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

    # 5) Проверка Google Drive подключения (корневая папка проектов)
    gsel = request.session.get("gdrive_selection") or {}
    base_folder_id = gsel.get("id") or ""
    res_key = gsel.get("res_key") or ""
    if not base_folder_id or not gdrive_get_access_token(request):
        messages.error(request, "Google Drive не подключён. Выберите папку в «Подключения».")
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

    # 9) Вложения из папок запросов (по именам из Block.context)
    request_names = _extract_context_labels(block)
    attachments = _collect_files_from_request_folders(
        request, search_root.get("id"), res_key, request_names,
        max_files=120, max_each_bytes=25 * 1024 * 1024
    )

    # 10) Вызов LLM
    try:
        client = get_openai_client_for(request.user)
        if client is None:
            messages.error(request, "OpenAI не подключён или не настроен API ключ.")
            return _redirect_after(request, default_tab="debugger")

        temperature = getattr(block, "temperature", None)

        FILE_MODELS = {"gpt-4o", "o4-mini", "o4"}
        model_for_files = model_id
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
        emsg = str(e).lower()
        if ("temperature" in emsg) and ("unsupported" in emsg or "does not support" in emsg):
            messages.error(request, "Выбранная температура не поддерживается этой моделью. Укажите 1.0 или оставьте пусто.")
        else:
            messages.error(request, f"Ошибка при обращении к LLM: {e}")
        return _redirect_after(request, default_tab="debugger")

    # 11) Запись в OneDrive .docx
    try:
        if getattr(sel, "is_folder", False):
            status, payload = _one_docx_in_folder_or_error(request.user, sel.item_id)
            if status == "err":
                messages.error(request, payload)
                return _redirect_after(request, default_tab="debugger")
            target_item_id = payload
        else:
            name_lc = (sel.item_name or "").lower()
            if not name_lc.endswith(".docx"):
                messages.error(request, "Выбранный объект OneDrive — не .docx.")
                return _redirect_after(request, default_tab="debugger")
            target_item_id = sel.item_id

        src = download_item_bytes(request.user, target_item_id)
        doc = Document(BytesIO(src))

        marker = (block.code or "").strip()
        inserted = False
        if marker:
            for paragraph in _iter_paragraphs(doc):
                if marker in paragraph.text:
                    _insert_paragraph_after(paragraph, answer)
                    inserted = True
                    break
        if not inserted:
            doc.add_paragraph(answer)

        buf = BytesIO(); doc.save(buf); buf.seek(0)
        upload_item_bytes(request.user, target_item_id, buf.read())
    except Exception as e:
        messages.error(request, f"Не удалось записать в документ: {e}")
        return _redirect_after(request, default_tab="debugger")

    if marker and not inserted:
        messages.warning(request, f"Якорь «{marker}» не найден — текст добавлен в конец документа.")
    messages.success(request, f"Ответ модели «{model_id}» записан в документ. Вложений из Google Drive: {len(attachments)}.")
    return _redirect_after(request, default_tab="debugger")