from django.http import HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Max

from policy_app.models import Product, TypicalSection
from .models import RequestTable, RequestItem
from .forms import RequestForm
from django.urls import reverse
from django.db import transaction


def _hx(request):
    return request.headers.get("HX-Request") == "true"

def _resolve_product_section(request):
    product_short = (request.GET.get("product") or "").strip().upper()
    section_id = (request.GET.get("section") or "").strip()

    product = Product.objects.filter(short_name__iexact=product_short).first()
    if not product:
        return None, None

    section = None
    if section_id:
        section = TypicalSection.objects.filter(id=section_id, product=product).first()
    if not section:
        section = product.sections.order_by("position", "id").first()  # дефолт: 1-й раздел

    return product, section

def _get_bindings(request):
    prod_short = (request.GET.get("product") or "").strip().upper()
    section_id = request.GET.get("section")
    product = Product.objects.filter(short_name__iexact=prod_short).first()
    section = TypicalSection.objects.filter(id=section_id).first() if section_id else None
    return product, section


def _render_table_for(table):
    return render(
        None,
        "requests_app/requests_table.html",
        {
            "product": table.product,
            "section": table.section,
            "table": table.__class__.objects.filter(pk=table.pk).prefetch_related("items").first(),
        },
    )


def requests_partial(request):
    product, section = _get_bindings(request)
    table = None
    if product:
        table = RequestTable.objects.filter(product=product, section=section).prefetch_related("items").first()
    return render(request, "requests_app/requests_table.html", {"product": product, "section": section, "table": table})


@require_http_methods(["GET", "POST"])
def request_form_create(request):
    product, section = _get_bindings(request)
    if not product:
        return HttpResponseBadRequest("Не удалось определить продукт/раздел.")
    table, _ = RequestTable.objects.get_or_create(product=product, section=section)
    code_initial = getattr(section, "code", "")

    if request.method == "POST":
        form = RequestForm(request.POST)             # ← без disabled
        if form.is_valid():
            item = form.save(commit=False)
            item.table = table
            item.code = code_initial or item.code    # ← форсируем код из раздела
            last = RequestItem.objects.filter(table=table).aggregate(m=Max("position"))["m"] or 0
            item.position = last + 1
            item.save()

            table = RequestTable.objects.filter(pk=table.pk).prefetch_related("items").first()
            resp = render(request, "requests_app/requests_table.html",
                          {"product": product, "section": section, "table": table})
            resp["HX-Trigger"] = "requests:saved"
            return resp

        # Невалидно → вернуть форму в модалку
        resp = render(request, "requests_app/request_form_modal.html", {
            "title": "Добавить запрос",
            "submit_label": "Сохранить",
            "form_action": f"{reverse('request_form_create')}?product={product.short_name.upper()}&section={(section.id if section else '')}",
            "form": form, "product": product, "section": section,
        })
        resp["HX-Retarget"] = "#requests-modal .modal-content"
        resp.status_code = 422
        return resp

    # GET: показать форму с автозаполненным CODЕ и readonly
    form = RequestForm(initial={"code": code_initial})
    form.fields["code"].widget.attrs["readonly"] = "readonly"
    return render(request, "requests_app/request_form_modal.html", {
        "title": "Добавить запрос",
        "submit_label": "Сохранить",
        "form_action": f"{reverse('request_form_create')}?product={product.short_name.upper()}&section={(section.id if section else '')}",
        "form": form, "product": product, "section": section,
    })


@require_http_methods(["GET", "POST"])
def request_form_edit(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table__product", "table__section"), pk=pk)
    table = item.table
    product, section = table.product, table.section

    if request.method == "POST":
        form = RequestForm(request.POST, instance=item)   # ← без disabled
        if form.is_valid():
            obj = form.save(commit=False)
            obj.code = getattr(section, "code", obj.code) # ← фиксируем код
            obj.save()
            table = RequestTable.objects.filter(pk=table.pk).prefetch_related("items").first()
            resp = render(request, "requests_app/requests_table.html",
                          {"product": product, "section": section, "table": table})
            resp["HX-Trigger"] = "requests:saved"
            return resp

        resp = render(request, "requests_app/request_form_modal.html", {
            "title": "Изменить запрос",
            "submit_label": "Сохранить",
            "form_action": reverse('request_form_edit', args=[item.pk]),
            "form": form, "product": product, "section": section,
        })
        resp["HX-Retarget"] = "#requests-modal .modal-content"
        resp.status_code = 422
        return resp

    form = RequestForm(instance=item)
    form.fields["code"].widget.attrs["readonly"] = "readonly"
    return render(request, "requests_app/request_form_modal.html", {
        "title": "Изменить запрос",
        "submit_label": "Сохранить",
        "form_action": reverse('request_form_edit', args=[item.pk]),
        "form": form, "product": product, "section": section,
    })

@require_http_methods(["POST"])
def request_delete(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table__product", "table__section"), pk=pk)
    table = item.table
    item.delete()
    table = RequestTable.objects.filter(pk=table.pk).prefetch_related("items").first()
    return render(request, "requests_app/requests_table.html", {"product": table.product, "section": table.section, "table": table})


def _swap_positions(a: RequestItem, b: RequestItem):
    a.position, b.position = b.position, a.position
    a.save(update_fields=["position"])
    b.save(update_fields=["position"])


@require_http_methods(["POST"])
def request_move_up(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table"), pk=pk)
    prev = (
        RequestItem.objects.filter(table=item.table, position__lt=item.position)
        .order_by("-position")
        .first()
    )
    if prev:
        with transaction.atomic():
            _swap_positions(item, prev)
    table = RequestTable.objects.filter(pk=item.table.pk).prefetch_related("items").first()
    return render(request, "requests_app/requests_table.html", {"product": table.product, "section": table.section, "table": table})


@require_http_methods(["POST"])
def request_move_down(request, pk: int):
    item = get_object_or_404(RequestItem.objects.select_related("table"), pk=pk)
    nxt = (
        RequestItem.objects.filter(table=item.table, position__gt=item.position)
        .order_by("position")
        .first()
    )
    if nxt:
        with transaction.atomic():
            _swap_positions(item, nxt)
    table = RequestTable.objects.filter(pk=item.table.pk).prefetch_related("items").first()
    return render(request, "requests_app/requests_table.html", {"product": table.product, "section": table.section, "table": table})