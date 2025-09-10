from io import BytesIO
from docx import Document
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph

from .forms import BlockForm
from .models import Block

from policy_app.models import Product, TypicalSection

from onedrive_app.models import OneDriveSelection, OneDriveAccount
from onedrive_app.graph import download_item_bytes, upload_item_bytes

# Опционально: импортируем OpenAIAccount, если приложение/модель есть
try:
    from openai_app.models import OpenAIAccount
except Exception:
    OpenAIAccount = None  # чтобы не было NameError

try:
    from openai_app.service import (
        get_client as get_openai_client_for,
        get_available_models,
        run_prompt,
    )
except Exception:
    def get_openai_client_for(user): return None
    def get_available_models(user): return []
    def run_prompt(user, model, prompt): return ""


def _llm_choices_for(user):
    # Всегда пробуем получить список (service сам решит — ENV или БД)
    try:
        models = get_available_models(user) or []
    except Exception:
        models = []
    return [(m, m) for m in models]


def _redirect_to_templates():
    """Редирект на главную с активной вкладкой «Шаблоны»."""
    return redirect(reverse("home") + "#templates")

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
    Отображение списка блоков c фильтрами:
    ?product=<SHORT_NAME in UPPER>  (необязателен)
    ?section=<SECTION_ID>           (необязателен)
    """
    blocks = Block.objects.all()

    # Пытаемся передать choices в форму (если BlockForm это поддерживает)
    try:
        form = BlockForm(model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm()

    llm_models = [v for v, _ in _llm_choices_for(request.user)]
    qs = Block.objects.all().select_related("product", "section").order_by("-id")

    product_short = (request.GET.get("product") or "").strip().upper()
    if product_short:
        qs = qs.filter(product__short_name__iexact=product_short)

    section_id = request.GET.get("section")
    if section_id:
        qs = qs.filter(section_id=section_id)

    selection = OneDriveSelection.objects.filter(user=request.user).first()
    onedrive_connected = OneDriveAccount.objects.filter(user=request.user).exists()
    openai = OpenAIAccount.objects.filter(user=request.user).first() if OpenAIAccount else None

    return render(
        request,
        "blocks_app/dashboard_partial.html",
        {
            "blocks": qs,
            "form": form,
            "llm_models": llm_models,
            "selection": selection,
            "onedrive_connected": onedrive_connected,
            "openai": openai,
        },
    )

@login_required
def block_create(request):
    if request.method != "POST":
        return _redirect_to_templates()

    # пробуем с choices; если форма не поддерживает аргумент — откатываемся
    try:
        form = BlockForm(request.POST, model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm(request.POST)

    if form.is_valid():
        obj = form.save(commit=False)

        # ЯВНО сохраняем model, даже если поле не входит в форму
        mdl = _posted_model(request, form)
        if hasattr(obj, "model"):
            obj.model = mdl

        temp = _posted_temperature(request, form)
        if hasattr(obj, "temperature"):
            obj.temperature = temp

        # Привязка к продукту и разделу (из скрытых полей)
        try:
            from policy_app.models import Product, TypicalSection
        except Exception:
            Product = TypicalSection = None

        product_id = (request.POST.get("product_id") or "").strip()
        section_id = (request.POST.get("section_id") or "").strip()

        if Product and product_id:
            obj.product = Product.objects.filter(id=product_id).first() or None
        if TypicalSection and section_id:
            obj.section = TypicalSection.objects.filter(id=section_id).first() or None

        obj.save()
        messages.success(request, "Блок сохранён.")
    else:
        messages.error(request, "Проверьте форму — есть ошибки.")
    return _redirect_to_templates()

@login_required
def block_update(request, pk: int):
    if request.method != "POST":
        return _redirect_to_templates()

    block = get_object_or_404(Block, pk=pk)

    try:
        form = BlockForm(request.POST, instance=block, model_choices=_llm_choices_for(request.user))
    except TypeError:
        form = BlockForm(request.POST, instance=block)

    if form.is_valid():
        obj = form.save(commit=False)

        # ЯВНО сохраняем model, даже если поле не входит в форму
        mdl = _posted_model(request, form)
        if hasattr(obj, "model"):
            obj.model = mdl

        temp = _posted_temperature(request, form)
        if hasattr(obj, "temperature"):
            obj.temperature = temp

        obj.save()
        messages.success(request, "Изменения сохранены.")
    else:
        messages.error(request, "Проверьте форму — есть ошибки.")
    return _redirect_to_templates()


@require_POST
@login_required
def block_delete(request, pk):
    block = get_object_or_404(Block, pk=pk)
    name = block.name or block.code
    block.delete()
    messages.success(request, f"Блок «{name}» удалён.")
    return _redirect_to_templates()


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
    return _redirect_to_templates()


@require_POST
@login_required
def block_run(request, pk):
    """
    Отправка промпта в выбранную модель и вставка ответа в .docx.
    Ищем маркер block.code во всех абзацах (включая таблицы) и
    вставляем новый абзац СРАЗУ ПОСЛЕ абзаца с маркером.
    Если маркер не найден — дописываем в конец.
    """
    block = get_object_or_404(Block, pk=pk)

    # 1) Проверяем выбранный документ
    sel = OneDriveSelection.objects.filter(user=request.user).first()
    if not sel or not sel.item_id:
        messages.error(request, "Сначала выберите файл в разделе «Подключения».")
        return _redirect_to_templates()

    # 2) Проверяем выбранную модель
    model_id = (block.model or "").strip()
    if not model_id:
        messages.error(
            request,
            "Не выбрана модель для блока. Выберите её в форме блока или через кнопку «Модель»."
        )
        return _redirect_to_templates()

    # 3) Готовим промпт (учитываем контекст)
    full_prompt = (block.prompt or "").strip()
    if block.context:
        full_prompt = f"{block.context.strip()}\n\n{full_prompt}"

    # 4) Запускаем LLM
    try:
        client = get_openai_client_for(request.user)
        if client is None:
            raise RuntimeError("OpenAI не подключён.")
        answer = (run_prompt(
            request.user,
            model_id,
            full_prompt,
            temperature=getattr(block, "temperature", None),
        ) or "").strip()
        if not answer:
            raise RuntimeError("Пустой ответ модели.")
    except Exception as e:
        emsg = str(e).lower()
        if ("temperature" in emsg) and ("unsupported" in emsg or "does not support" in emsg):
            messages.error(
                request,
                "Выбранная температура не поддерживается этой моделью. "
                "Оставьте поле пустым или укажите 1.0 и повторите."
            )
        else:
            messages.error(request, f"Ошибка при обращении к LLM: {e}")
        return _redirect_to_templates()

    # 5) Вставляем ответ в .docx по маркеру или в конец
    try:
        src = download_item_bytes(request.user, sel.item_id)
        doc = Document(BytesIO(src))

        marker = (block.code or "").strip()
        inserted = False

        if marker:
            # проходим ВСЕ абзацы (тело + таблицы)
            for paragraph in _iter_paragraphs(doc):
                if marker in paragraph.text:
                    _insert_paragraph_after(paragraph, answer)
                    inserted = True
                    break

        if not inserted:
            # если маркер не найден — добавляем в конец документа
            doc.add_paragraph(answer)

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        upload_item_bytes(request.user, sel.item_id, buf.read())

    except Exception as e:
        messages.error(request, f"Не удалось записать в документ: {e}")
        return _redirect_to_templates()

    messages.success(request, f"Ответ модели «{model_id}» записан в документ.")
    return _redirect_to_templates()