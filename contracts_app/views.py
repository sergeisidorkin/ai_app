import logging
import os

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max, Sum, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from notifications_app.models import Notification, NotificationPerformerLink
from projects_app.models import Performer, ProjectRegistration
from .forms import ContractEditForm, ContractSigningForm, ContractSubjectForm, ContractTemplateForm, ContractVariableForm
from .models import ContractSubject, ContractTemplate, ContractVariable

logger = logging.getLogger(__name__)


def staff_required(user):
    return user.is_staff


CONTRACTS_PARTIAL_TEMPLATE = "contracts_app/contracts_partial.html"
CT_PARTIAL_TEMPLATE = "contracts_app/contract_templates_partial.html"
CT_FORM_TEMPLATE = "contracts_app/contract_template_form.html"
CT_HX_EVENT = "contract-templates-updated"


def _contracts_context(user=None):
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

    pending_notifications = list(
        Notification.objects
        .filter(
            notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION,
        )
        .pending_attention()
        .order_by("-sent_at", "-id")
    )
    pending_numbers = {
        n.pk: len(pending_notifications) - idx
        for idx, n in enumerate(pending_notifications)
    }

    batch_badge_map = {}
    if pending_notifications:
        for n in pending_notifications:
            perf_ids = set(
                NotificationPerformerLink.objects
                .filter(notification_id=n.pk)
                .values_list("performer_id", flat=True)
            )
            batch_ids = set(
                Performer.objects
                .filter(pk__in=perf_ids, contract_batch_id__isnull=False)
                .values_list("contract_batch_id", flat=True)
            )
            marker = pending_numbers[n.pk]
            for bid in batch_ids:
                if bid not in batch_badge_map:
                    batch_badge_map[bid] = marker

    is_expert = False
    is_lawyer = False
    if user and getattr(user, "is_authenticated", False):
        from policy_app.models import EXPERT_GROUP, LAWYER_GROUP
        is_expert = user.groups.filter(name=EXPERT_GROUP).exists()
        is_lawyer = user.groups.filter(name=LAWYER_GROUP).exists()

    lawyer_badge_map = {}
    if is_lawyer:
        lawyer_pending = list(
            Notification.objects
            .filter(notification_type=Notification.NotificationType.EMPLOYEE_SCAN_SENT)
            .pending_attention()
            .order_by("-sent_at", "-id")
        )
        lawyer_numbers = {n.pk: len(lawyer_pending) - idx for idx, n in enumerate(lawyer_pending)}
        for n in lawyer_pending:
            perf_ids = set(
                NotificationPerformerLink.objects
                .filter(notification_id=n.pk)
                .values_list("performer_id", flat=True)
            )
            bids = set(
                Performer.objects
                .filter(pk__in=perf_ids, contract_batch_id__isnull=False)
                .values_list("contract_batch_id", flat=True)
            )
            marker = lawyer_numbers[n.pk]
            for bid in bids:
                if bid not in lawyer_badge_map:
                    lawyer_badge_map[bid] = marker

    contract_project_ids = {p.registration_id for p in contracts}
    contract_projects = (
        ProjectRegistration.objects
        .filter(id__in=contract_project_ids)
        .order_by("-number", "-id")
    )

    return {
        "contracts": contracts,
        "contract_projects": contract_projects,
        "batch_badge_map": batch_badge_map,
        "lawyer_badge_map": lawyer_badge_map,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
    }


@login_required
@require_http_methods(["GET"])
def contracts_partial(request):
    return render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))


def _upload_scan_to_yandex_disk(user, performer, uploaded_file):
    """Upload scan to Yandex.Disk, publish it, and return the public URL."""
    if not performer.contract_project_disk_folder:
        return ""
    try:
        from yandexdisk_app.service import upload_file, publish_resource
        disk_path = f"{performer.contract_project_disk_folder}/{uploaded_file.name}"
        uploaded_file.seek(0)
        upload_file(user, disk_path, uploaded_file.read())
        public_url = publish_resource(user, disk_path)
        return public_url or ""
    except Exception:
        logger.debug("Yandex.Disk upload failed for scan %s", uploaded_file.name, exc_info=True)
        return ""


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_signing_edit(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related(
            "registration", "registration__type", "currency",
        ),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    if request.method == "POST":
        form = ContractSigningForm(request.POST, request.FILES, instance=performer)
        if form.is_valid():
            has_new_scan = "contract_employee_scan" in request.FILES
            if has_new_scan:
                scan_name = _compute_scan_name(performer)
                _rename_uploaded_file(request.FILES["contract_employee_scan"], scan_name)
                form.instance.contract_scan_document = scan_name
                form.instance.contract_upload_date = timezone.now()
            obj = form.save()
            if has_new_scan:
                scan_url = _upload_scan_to_yandex_disk(request.user, obj, request.FILES["contract_employee_scan"])
                if scan_url:
                    obj.contract_employee_scan_link = scan_url
                    obj.save(update_fields=["contract_employee_scan_link"])
            if obj.contract_batch_id:
                Performer.objects.filter(
                    contract_batch_id=obj.contract_batch_id,
                ).exclude(pk=obj.pk).update(
                    contract_employee_scan=obj.contract_employee_scan,
                    contract_employee_scan_link=obj.contract_employee_scan_link,
                    contract_scan_document=obj.contract_scan_document,
                    contract_upload_date=obj.contract_upload_date,
                    contract_send_date=obj.contract_send_date,
                    contract_signed_scan=obj.contract_signed_scan,
                )
            resp = render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))
            resp["HX-Trigger"] = "contracts-updated"
            return resp
    else:
        form = ContractSigningForm(instance=performer)

    resp = render(request, "contracts_app/signing_form.html", {
        "form": form,
        "performer": performer,
    })
    if request.method == "POST":
        resp["HX-Retarget"] = "#contracts-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
    return resp


def _compute_scan_name(performer):
    number = (performer.contract_number or "").replace("/", "-")
    executor_raw = " ".join(str(performer.executor or "").split())
    if executor_raw:
        parts = executor_raw.split(" ")
        last_name = parts[0]
        initials = "".join(p[0] for p in parts[1:3] if p)
        executor_short = f"{last_name} {initials}".strip()
    else:
        executor_short = "Unknown"
    return f"Договор {number}_{executor_short}".strip()


def _rename_uploaded_file(uploaded_file, new_basename):
    ext = os.path.splitext(uploaded_file.name)[1]
    uploaded_file.name = new_basename + ext


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_scan_upload(request, pk):
    performer = get_object_or_404(
        Performer,
        pk=pk,
        contract_batch_id__isnull=False,
    )
    uploaded_file = request.FILES.get("contract_employee_scan")
    if not uploaded_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)

    scan_name = _compute_scan_name(performer)
    _rename_uploaded_file(uploaded_file, scan_name)
    performer.contract_employee_scan = uploaded_file
    performer.contract_scan_document = scan_name
    performer.contract_upload_date = timezone.now()
    performer.save(update_fields=["contract_employee_scan", "contract_scan_document", "contract_upload_date"])

    scan_url = _upload_scan_to_yandex_disk(request.user, performer, uploaded_file)
    if scan_url:
        performer.contract_employee_scan_link = scan_url
        performer.save(update_fields=["contract_employee_scan_link"])

    if performer.contract_batch_id:
        Performer.objects.filter(
            contract_batch_id=performer.contract_batch_id,
        ).exclude(pk=performer.pk).update(
            contract_employee_scan=performer.contract_employee_scan,
            contract_employee_scan_link=performer.contract_employee_scan_link,
            contract_scan_document=performer.contract_scan_document,
            contract_upload_date=performer.contract_upload_date,
        )

    return JsonResponse({"ok": True, "scan_name": scan_name})


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
            resp = render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))
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


# ---------------------------------------------------------------------------
#  Field Parameters / Contract Subject ("Предмет договора")
# ---------------------------------------------------------------------------

FP_PARTIAL_TEMPLATE = "contracts_app/field_params_partial.html"
CS_FORM_TEMPLATE = "contracts_app/contract_subject_form.html"
FP_HX_EVENT = "field-params-updated"


def _fp_context():
    return {
        "subjects": ContractSubject.objects.select_related("product").all(),
    }


def _fp_next_position():
    mx = ContractSubject.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _fp_normalize_positions():
    for idx, obj in enumerate(ContractSubject.objects.all()):
        if obj.position != idx:
            ContractSubject.objects.filter(pk=obj.pk).update(position=idx)


def _fp_render_updated(request):
    response = render(request, FP_PARTIAL_TEMPLATE, _fp_context())
    response["HX-Trigger"] = FP_HX_EVENT
    return response


def _cs_render_form_with_errors(request, form, action, subject_obj=None):
    ctx = {"form": form, "action": action}
    if subject_obj is not None:
        ctx["subject_obj"] = subject_obj
    response = render(request, CS_FORM_TEMPLATE, ctx)
    response["HX-Retarget"] = "#field-params-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
@require_http_methods(["GET"])
def field_params_partial(request):
    return render(request, FP_PARTIAL_TEMPLATE, _fp_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def cs_form_create(request):
    if request.method == "GET":
        form = ContractSubjectForm()
        return render(request, CS_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ContractSubjectForm(request.POST)
    if not form.is_valid():
        return _cs_render_form_with_errors(request, form, "create")
    obj = form.save(commit=False)
    obj.position = _fp_next_position()
    obj.save()
    return _fp_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def cs_form_edit(request, pk):
    subject_obj = get_object_or_404(ContractSubject, pk=pk)
    if request.method == "GET":
        form = ContractSubjectForm(instance=subject_obj)
        return render(request, CS_FORM_TEMPLATE, {
            "form": form, "action": "edit", "subject_obj": subject_obj,
        })
    form = ContractSubjectForm(request.POST, instance=subject_obj)
    if not form.is_valid():
        return _cs_render_form_with_errors(request, form, "edit", subject_obj)
    form.save()
    return _fp_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def cs_delete(request, pk):
    get_object_or_404(ContractSubject, pk=pk).delete()
    _fp_normalize_positions()
    return _fp_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def cs_move_up(request, pk):
    obj = get_object_or_404(ContractSubject, pk=pk)
    prev = ContractSubject.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ContractSubject.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractSubject.objects.filter(pk=prev.pk).update(position=prev.position)
    return _fp_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def cs_move_down(request, pk):
    obj = get_object_or_404(ContractSubject, pk=pk)
    nxt = ContractSubject.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ContractSubject.objects.filter(pk=obj.pk).update(position=obj.position)
        ContractSubject.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _fp_render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def send_scan(request):
    from notifications_app.services import create_scan_notifications

    performer_ids = request.POST.getlist("performer_ids[]")
    performer_ids = [int(pid) for pid in performer_ids if pid.isdigit()]
    if not performer_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки."}, status=400)

    performers = list(
        Performer.objects
        .filter(pk__in=performer_ids, contract_batch_id__isnull=False)
        .select_related("registration", "registration__type", "currency", "employee", "typical_section")
    )
    if not performers:
        return JsonResponse({"ok": False, "error": "Исполнители не найдены."}, status=400)

    try:
        create_scan_notifications(performers=performers, sender=request.user)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    batch_ids = {p.contract_batch_id for p in performers if p.contract_batch_id}
    if batch_ids:
        batch_performer_ids = set(
            Performer.objects
            .filter(contract_batch_id__in=batch_ids)
            .values_list("pk", flat=True)
        )
        expert_notif_ids = set(
            NotificationPerformerLink.objects
            .filter(
                performer_id__in=batch_performer_ids,
                notification__notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION,
                notification__is_processed=False,
            )
            .values_list("notification_id", flat=True)
        )
        if expert_notif_ids:
            now = timezone.now()
            Notification.objects.filter(pk__in=expert_notif_ids).update(
                is_processed=True,
                action_at=now,
                updated_at=now,
            )

    return JsonResponse({"ok": True})
