import os

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max, Sum, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from projects_app.models import Performer, ProjectRegistration
from .forms import ContractEditForm, ContractTemplateForm, ContractVariableForm
from .models import ContractTemplate, ContractVariable


def staff_required(user):
    return user.is_staff


CONTRACTS_PARTIAL_TEMPLATE = "contracts_app/contracts_partial.html"
CT_PARTIAL_TEMPLATE = "contracts_app/contract_templates_partial.html"
CT_FORM_TEMPLATE = "contracts_app/contract_template_form.html"
CT_HX_EVENT = "contract-templates-updated"


def _contracts_context():
    all_performers = (
        Performer.objects
        .select_related(
            "registration", "registration__type", "typical_section",
            "employee", "employee__user", "currency",
        )
        .filter(contract_batch_id__isnull=False)
        .order_by("contract_batch_id", "position", "id")
    )

    seen_batches = set()
    contracts = []
    for p in all_performers:
        if p.contract_batch_id not in seen_batches:
            seen_batches.add(p.contract_batch_id)
            contracts.append(p)

    price_map = {}
    for row in (
        Performer.objects
        .filter(contract_batch_id__isnull=False, agreed_amount__isnull=False)
        .values("contract_batch_id")
        .annotate(total_agreed=Sum("agreed_amount"))
    ):
        price_map[row["contract_batch_id"]] = row["total_agreed"]

    for p in contracts:
        p.total_price = price_map.get(p.contract_batch_id)

    contract_project_ids = {p.registration_id for p in contracts}
    contract_projects = (
        ProjectRegistration.objects
        .filter(id__in=contract_project_ids)
        .order_by("-number", "-id")
    )

    return {
        "contracts": contracts,
        "contract_projects": contract_projects,
    }


@login_required
@require_http_methods(["GET"])
def contracts_partial(request):
    return render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_form_edit(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related(
            "registration", "registration__type", "currency",
        ),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    if request.method == "POST":
        form = ContractEditForm(request.POST, instance=performer)
        if form.is_valid():
            obj = form.save()
            if obj.contract_batch_id:
                Performer.objects.filter(
                    contract_batch_id=obj.contract_batch_id,
                ).exclude(pk=obj.pk).update(
                    contract_number=obj.contract_number,
                    contract_file=obj.contract_file,
                )
            resp = render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context())
            resp["HX-Trigger"] = "contracts-updated"
            return resp
    else:
        form = ContractEditForm(instance=performer)

    batch_filter = (
        Q(contract_batch_id=performer.contract_batch_id)
        if performer.contract_batch_id
        else Q(registration_id=performer.registration_id, executor=performer.executor, contract_batch_id__isnull=False)
    )
    total_price = (
        Performer.objects
        .filter(batch_filter, agreed_amount__isnull=False)
        .aggregate(total=Sum("agreed_amount"))
        .get("total")
    )
    performer.total_price = total_price

    return render(request, "contracts_app/contract_form.html", {
        "form": form,
        "performer": performer,
    })


# ---------------------------------------------------------------------------
#  Contract Templates ("Образцы шаблонов")
# ---------------------------------------------------------------------------

CTV_FORM_TEMPLATE = "contracts_app/contract_variable_form.html"


def _ct_context():
    from .forms import _group_member_order_map, _group_member_short
    templates = list(ContractTemplate.objects.select_related("product", "group_member").all())
    order_map = _group_member_order_map()
    for t in templates:
        if t.group_member_id:
            t.group_display = _group_member_short(t.group_member, order_map.get(t.group_member_id, 0))
        else:
            t.group_display = ""
    return {
        "templates": templates,
        "ct_variables": ContractVariable.objects.all(),
    }


def _ct_next_position():
    mx = ContractTemplate.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _ct_normalize_positions():
    for idx, obj in enumerate(ContractTemplate.objects.all()):
        if obj.position != idx:
            ContractTemplate.objects.filter(pk=obj.pk).update(position=idx)


def _ct_render_updated(request):
    response = render(request, CT_PARTIAL_TEMPLATE, _ct_context())
    response["HX-Trigger"] = CT_HX_EVENT
    return response


def _ct_form_context(form, action, template_obj=None):
    ctx = {"form": form, "action": action}
    if template_obj is not None:
        ctx["template_obj"] = template_obj
    return ctx


def _ct_render_form_with_errors(request, template, context):
    response = render(request, template, context)
    response["HX-Retarget"] = "#contract-templates-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
@require_http_methods(["GET"])
def contract_templates_partial(request):
    return render(request, CT_PARTIAL_TEMPLATE, _ct_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ct_form_create(request):
    if request.method == "GET":
        form = ContractTemplateForm()
        return render(request, CT_FORM_TEMPLATE, _ct_form_context(form, "create"))
    form = ContractTemplateForm(request.POST, request.FILES)
    if not form.is_valid():
        return _ct_render_form_with_errors(request, CT_FORM_TEMPLATE, _ct_form_context(form, "create"))
    form.instance.position = _ct_next_position()
    form.save()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ct_form_edit(request, pk):
    template_obj = get_object_or_404(ContractTemplate, pk=pk)
    if request.method == "GET":
        form = ContractTemplateForm(instance=template_obj)
        return render(request, CT_FORM_TEMPLATE, _ct_form_context(form, "edit", template_obj))
    form = ContractTemplateForm(request.POST, request.FILES, instance=template_obj)
    if not form.is_valid():
        return _ct_render_form_with_errors(request, CT_FORM_TEMPLATE, _ct_form_context(form, "edit", template_obj))
    form.save()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ct_delete(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    if obj.file:
        obj.file.delete(save=False)
    obj.delete()
    _ct_normalize_positions()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ct_move_up(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    prev = ContractTemplate.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ContractTemplate.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractTemplate.objects.filter(pk=prev.pk).update(position=prev.position)
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ct_move_down(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    nxt = ContractTemplate.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ContractTemplate.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractTemplate.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _ct_render_updated(request)


@login_required
@require_http_methods(["GET"])
def ct_download(request, pk):
    obj = get_object_or_404(ContractTemplate, pk=pk)
    if not obj.file:
        raise Http404("Файл не найден")
    file_path = obj.file.path
    if not os.path.isfile(file_path):
        raise Http404("Файл не найден на диске")
    from urllib.parse import quote
    basename = os.path.basename(file_path)
    response = FileResponse(
        open(file_path, "rb"),
        content_type="application/octet-stream",
    )
    response["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(basename)}"
    )
    return response


# ---------------------------------------------------------------------------
#  Contract Variables ("Доступные переменные")
# ---------------------------------------------------------------------------

def _ctv_form_ctx(**extra):
    from core.column_registry import get_registry_json
    ctx = {"registry_json": get_registry_json()}
    ctx.update(extra)
    return ctx


def _ctv_next_position():
    mx = ContractVariable.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _ctv_normalize_positions():
    for idx, obj in enumerate(ContractVariable.objects.all()):
        if obj.position != idx:
            ContractVariable.objects.filter(pk=obj.pk).update(position=idx)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ctv_form_create(request):
    if request.method == "GET":
        form = ContractVariableForm()
        return render(request, CTV_FORM_TEMPLATE, _ctv_form_ctx(form=form, action="create"))
    form = ContractVariableForm(request.POST)
    if not form.is_valid():
        resp = render(request, CTV_FORM_TEMPLATE, _ctv_form_ctx(form=form, action="create"))
        resp["HX-Retarget"] = "#contract-templates-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    obj = form.save(commit=False)
    obj.position = _ctv_next_position()
    obj.save()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ctv_form_edit(request, pk):
    obj = get_object_or_404(ContractVariable, pk=pk)
    if request.method == "GET":
        form = ContractVariableForm(instance=obj)
        return render(request, CTV_FORM_TEMPLATE, _ctv_form_ctx(
            form=form, action="edit", variable=obj,
        ))
    form = ContractVariableForm(request.POST, instance=obj)
    if not form.is_valid():
        resp = render(request, CTV_FORM_TEMPLATE, _ctv_form_ctx(
            form=form, action="edit", variable=obj,
        ))
        resp["HX-Retarget"] = "#contract-templates-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp
    form.save()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ctv_delete(request, pk):
    get_object_or_404(ContractVariable, pk=pk).delete()
    _ctv_normalize_positions()
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ctv_move_up(request, pk):
    obj = get_object_or_404(ContractVariable, pk=pk)
    prev = ContractVariable.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ContractVariable.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractVariable.objects.filter(pk=prev.pk).update(position=prev.position)
    return _ct_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ctv_move_down(request, pk):
    obj = get_object_or_404(ContractVariable, pk=pk)
    nxt = ContractVariable.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ContractVariable.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractVariable.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _ct_render_updated(request)
