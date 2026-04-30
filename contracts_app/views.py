import logging
import os
from urllib.parse import quote

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Max, Sum, Q
from django.db.models.functions import Trim
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.cloud_storage import (
    build_folder_url,
    CloudStorageNotReadyError,
    get_any_connected_service_user,
    get_nextcloud_root_path,
    get_primary_cloud_storage_label,
    is_nextcloud_primary,
    publish_resource as cloud_publish_resource,
    upload_file as cloud_upload_file,
)
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from nextcloud_app.models import NextcloudUserLink
from notifications_app.models import Notification, NotificationPerformerLink
from policy_app.models import LAWYER_GROUP
from projects_app.models import Performer, ProjectRegistration, ProjectRegistrationProduct
from users_app.forms import FREELANCER_LABEL
from .forms import (
    ContractEditForm,
    ContractProjectRegistrationForm,
    ContractSigningForm,
    ContractSubjectForm,
    ContractTemplateForm,
    ContractVariableForm,
)
from .models import ContractSubject, ContractTemplate, ContractVariable

logger = logging.getLogger(__name__)


def staff_required(user):
    return user.is_staff


CONTRACTS_PARTIAL_TEMPLATE = "contracts_app/contracts_partial.html"
CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE = "contracts_app/contracts_development_partial.html"
CONTRACTS_PROJECT_REG_FORM_TEMPLATE = "contracts_app/contracts_project_registration_form.html"
CT_PARTIAL_TEMPLATE = "contracts_app/contract_templates_partial.html"
CT_FORM_TEMPLATE = "contracts_app/contract_template_form.html"
CT_HX_EVENT = "contract-templates-updated"


def _contracts_context(user=None):
    active_participation_statuses = ["Не начат", "В работе"]
    registration_products_prefetch = models.Prefetch(
        "registration__product_links",
        queryset=(
            ProjectRegistrationProduct.objects
            .select_related("product")
            .order_by("rank", "id")
        ),
    )
    project_products_prefetch = models.Prefetch(
        "product_links",
        queryset=(
            ProjectRegistrationProduct.objects
            .select_related("product")
            .order_by("rank", "id")
        ),
    )
    contract_conclusion_performers = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__product",
            "employee",
            "employee__user",
            "currency",
        )
        .prefetch_related(registration_products_prefetch)
        .annotate(executor_trim=Trim("executor"))
        .filter(
            registration__status__in=active_participation_statuses,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            employee__employment=FREELANCER_LABEL,
        )
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    contract_conclusion_project_ids = (
        contract_conclusion_performers
        .values_list("registration_id", flat=True)
        .distinct()
    )
    contract_conclusion_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=contract_conclusion_project_ids)
        .order_by("-number", "-id")
    )
    contract_request_sent_initial = timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

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

    is_expert = False
    is_lawyer = False
    if user and getattr(user, "is_authenticated", False):
        from policy_app.models import EXPERT_GROUP, LAWYER_GROUP
        is_expert = user.groups.filter(name=EXPERT_GROUP).exists()
        is_lawyer = user.groups.filter(name=LAWYER_GROUP).exists()

    def _build_badge_map(notification_type):
        qs = (
            Notification.objects
            .filter(notification_type=notification_type, recipient=user)
            .pending_attention()
            .order_by("-sent_at", "-id")
        )
        pending_list = list(qs)
        if not pending_list:
            return {}
        numbers = {n.pk: len(pending_list) - idx for idx, n in enumerate(pending_list)}
        nids = [n.pk for n in pending_list]
        links = (
            NotificationPerformerLink.objects
            .filter(notification_id__in=nids)
            .values_list("notification_id", "performer_id")
        )
        nid_to_perfs = {}
        all_perf_ids = set()
        for nid, pid in links:
            nid_to_perfs.setdefault(nid, []).append(pid)
            all_perf_ids.add(pid)
        perf_batch = dict(
            Performer.objects
            .filter(pk__in=all_perf_ids, contract_batch_id__isnull=False)
            .values_list("pk", "contract_batch_id")
        )
        badge_map = {}
        for n in pending_list:
            marker = numbers[n.pk]
            for pid in nid_to_perfs.get(n.pk, []):
                bid = perf_batch.get(pid)
                if bid and bid not in badge_map:
                    badge_map[bid] = marker
        return badge_map

    batch_badge_map = _build_badge_map(Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION)
    lawyer_badge_map = (
        _build_badge_map(Notification.NotificationType.EMPLOYEE_SCAN_SENT) if is_lawyer else {}
    )

    contract_project_ids = {p.registration_id for p in contracts}
    contract_projects = (
        ProjectRegistration.objects
        .filter(id__in=contract_project_ids)
        .select_related("type")
        .order_by("-number", "-id")
    )

    contract_conclusion_performers = list(contract_conclusion_performers)
    _attach_contract_folder_urls([*contract_conclusion_performers, *contracts], user)

    return {
        "contracts": contracts,
        "contract_projects": contract_projects,
        "contract_conclusion_performers": contract_conclusion_performers,
        "contract_conclusion_projects": contract_conclusion_projects,
        "contract_request_sent_initial": contract_request_sent_initial,
        "batch_badge_map": batch_badge_map,
        "lawyer_badge_map": lawyer_badge_map,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
    }


def _normalize_contract_nextcloud_path(path: str) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    if raw_path == "/":
        return "/"
    return f"/{raw_path.strip('/')}"


def _contract_nextcloud_path_parts(path: str) -> list[str]:
    normalized = _normalize_contract_nextcloud_path(path)
    if normalized in {"", "/"}:
        return []
    return [part for part in normalized.strip("/").split("/") if part]


def _normalize_contract_viewer_target_path(path: str, *, root_path: str = "") -> str:
    normalized_path = _normalize_contract_nextcloud_path(path)
    if not normalized_path:
        return ""
    if not root_path or root_path == "/":
        return normalized_path
    if normalized_path == root_path:
        return "/"
    if normalized_path.startswith(f"{root_path}/"):
        stripped_path = _normalize_contract_nextcloud_path(normalized_path[len(root_path):])
        if stripped_path:
            return stripped_path
    return normalized_path


def _build_contract_shared_target_candidate(
    normalized_path: str,
    shared_path: str,
    target_path: str,
) -> tuple[int, int, int, int, str, str] | None:
    normalized_shared_path = _normalize_contract_nextcloud_path(shared_path)
    clean_target_path = str(target_path or "").strip()
    if not normalized_shared_path or not clean_target_path:
        return None

    shared_parts = _contract_nextcloud_path_parts(normalized_shared_path)
    if normalized_path == normalized_shared_path or normalized_path.startswith(f"{normalized_shared_path}/"):
        suffix = normalized_path[len(normalized_shared_path):].strip("/")
        if not suffix:
            return (2, len(shared_parts), 0, len(normalized_shared_path), normalized_shared_path, clean_target_path)
        return (
            2,
            len(shared_parts),
            0,
            len(normalized_shared_path),
            normalized_shared_path,
            f"{clean_target_path.rstrip('/')}/{suffix}",
        )

    path_parts = _contract_nextcloud_path_parts(normalized_path)
    if not path_parts or not shared_parts or len(shared_parts) > len(path_parts):
        return None

    for start_index in range(len(path_parts) - len(shared_parts) + 1):
        if path_parts[start_index:start_index + len(shared_parts)] != shared_parts:
            continue
        suffix_parts = path_parts[start_index + len(shared_parts):]
        if not suffix_parts:
            return (
                1,
                len(shared_parts),
                -start_index,
                len(normalized_shared_path),
                normalized_shared_path,
                clean_target_path,
            )
        return (
            1,
            len(shared_parts),
            -start_index,
            len(normalized_shared_path),
            normalized_shared_path,
            f"{clean_target_path.rstrip('/')}/{'/'.join(suffix_parts)}",
        )
    return None


def _resolve_contract_shared_target_path(path: str, share_map: dict[str, object], *, root_path: str = "") -> str:
    normalized_path = _normalize_contract_nextcloud_path(path)
    if not normalized_path:
        return ""

    candidates = []
    for shared_path, share in share_map.items():
        target_path = _normalize_contract_viewer_target_path(
            getattr(share, "target_path", "") or "",
            root_path=root_path,
        )
        candidate = _build_contract_shared_target_candidate(normalized_path, shared_path, target_path)
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[:5])[-1]


def _resolve_contract_target_path_via_user_share_lookup(
    client,
    owner_user_id: str,
    path: str,
    share_with_user_id: str,
    *,
    root_path: str = "",
) -> str:
    normalized_path = _normalize_contract_nextcloud_path(path)
    if not normalized_path or normalized_path == "/":
        return ""

    current_path = normalized_path
    while current_path and current_path != "/":
        share = client.get_user_share(owner_user_id, current_path, share_with_user_id)
        if share is not None:
            target_path = _normalize_contract_viewer_target_path(
                getattr(share, "target_path", "") or "",
                root_path=root_path,
            )
            if target_path:
                candidate = _build_contract_shared_target_candidate(normalized_path, current_path, target_path)
                if candidate is not None:
                    return candidate[-1]
        current_path = current_path.rsplit("/", 1)[0] or "/"
    return ""


def _contract_nextcloud_parent_path(path: str) -> str:
    normalized_path = _normalize_contract_nextcloud_path(path)
    if not normalized_path or normalized_path == "/":
        return ""
    parent = normalized_path.rsplit("/", 1)[0]
    return parent or "/"


def _resolve_contract_nextcloud_file_id(client, owner_user_id: str, path: str, *, resource_cache=None) -> str:
    normalized_path = _normalize_contract_nextcloud_path(path)
    parent_path = _contract_nextcloud_parent_path(normalized_path)
    if not normalized_path or not parent_path:
        return ""
    if resource_cache is None:
        resource_cache = {}
    if parent_path not in resource_cache:
        items = client.list_resources(owner_user_id, parent_path, limit=500)
        resource_cache[parent_path] = {
            _normalize_contract_nextcloud_path(item.get("path") or ""): str(item.get("file_id") or "").strip()
            for item in items
        }
    return str(resource_cache.get(parent_path, {}).get(normalized_path) or "")


def _build_contract_child_url(client, parent_path: str, child_name: str) -> str:
    normalized_parent = _normalize_contract_nextcloud_path(parent_path)
    clean_child_name = str(child_name or "").strip().strip("/")
    if not normalized_parent or not clean_child_name:
        return ""
    if normalized_parent == "/":
        return client.build_files_url(f"/{clean_child_name}")
    return client.build_files_url(f"{normalized_parent.rstrip('/')}/{clean_child_name}")


def _build_contract_file_redirect_url(client, file_id: str) -> str:
    clean_file_id = str(file_id or "").strip()
    base_url = str(getattr(client, "base_url", "") or "").strip().rstrip("/")
    if not clean_file_id or not base_url:
        return ""
    return f"{base_url}/f/{quote(clean_file_id, safe='')}"


def _attach_contract_folder_urls(contracts, user=None):
    folder_cache = {}
    for performer in contracts:
        path = getattr(performer, "contract_project_disk_folder", "") or ""
        public_url = (getattr(performer, "contract_project_folder_link", "") or "").strip()
        performer.contract_project_folder_url = public_url or build_folder_url(path)
        performer.contract_project_docx_file_url = (
            getattr(performer, "contract_project_link", "") or ""
        ).strip()
        if path:
            folder_cache.setdefault(path, performer.contract_project_folder_url)

    if not contracts or not is_nextcloud_primary():
        return
    if user is None or not getattr(user, "is_authenticated", False):
        return

    client = NextcloudApiClient()
    if not client.is_configured:
        return
    is_lawyer = user.groups.filter(name=LAWYER_GROUP).exists()

    link = NextcloudUserLink.objects.filter(user=user).first()
    if not link or not link.nextcloud_user_id or link.nextcloud_user_id == client.username:
        return

    try:
        share_map = client.list_user_shares(client.username, link.nextcloud_user_id)
    except NextcloudApiError as exc:
        logger.warning("Could not resolve Nextcloud share targets for contracts table: %s", exc)
        return

    normalized_root_path = _normalize_contract_nextcloud_path(get_nextcloud_root_path())
    resolved_cache = dict(folder_cache)
    resolved_target_cache = {}
    for path in list(resolved_cache.keys()):
        target_path = _resolve_contract_shared_target_path(path, share_map, root_path=normalized_root_path)
        if not target_path:
            try:
                target_path = _resolve_contract_target_path_via_user_share_lookup(
                    client,
                    client.username,
                    path,
                    link.nextcloud_user_id,
                    root_path=normalized_root_path,
                )
            except NextcloudApiError as exc:
                logger.warning("Could not resolve Nextcloud share target for contract path %s: %s", path, exc)
        if target_path:
            resolved_target_cache[path] = target_path
            resolved_cache[path] = client.build_files_url(target_path)

    resource_cache = {}

    for performer in contracts:
        path = getattr(performer, "contract_project_disk_folder", "") or ""
        public_url = (getattr(performer, "contract_project_folder_link", "") or "").strip()
        target_path = resolved_target_cache.get(path, "")
        stored_folder_file_id = str(getattr(performer, "contract_project_folder_file_id", "") or "").strip()
        if path and not public_url:
            performer.contract_project_folder_url = resolved_cache.get(path, performer.contract_project_folder_url)
        if is_lawyer and path and not stored_folder_file_id:
            try:
                stored_folder_file_id = _resolve_contract_nextcloud_file_id(
                    client,
                    client.username,
                    path,
                    resource_cache=resource_cache,
                )
            except NextcloudApiError as exc:
                logger.warning("Could not resolve Nextcloud contract folder file id for performer %s: %s", performer.pk, exc)
                stored_folder_file_id = ""
            if stored_folder_file_id:
                performer.contract_project_folder_file_id = stored_folder_file_id
                Performer.objects.filter(pk=performer.pk).update(
                    contract_project_folder_file_id=stored_folder_file_id
                )
        if is_lawyer and stored_folder_file_id:
            performer.contract_project_folder_url = _build_contract_file_redirect_url(client, stored_folder_file_id)
        if is_lawyer and path and not target_path:
            try:
                share = client.ensure_user_share(
                    client.username,
                    path,
                    link.nextcloud_user_id,
                    permissions=NextcloudApiClient.EDITOR_PERMISSIONS,
                )
            except NextcloudApiError as exc:
                logger.warning("Could not ensure Nextcloud contract folder share for performer %s: %s", performer.pk, exc)
            else:
                target_path = _normalize_contract_viewer_target_path(
                    getattr(share, "target_path", "") or "",
                    root_path=normalized_root_path,
                )
                if target_path:
                    resolved_target_cache[path] = target_path
                    resolved_cache[path] = client.build_files_url(target_path)
        if is_lawyer:
            contract_file = getattr(performer, "contract_file", "") or ""
            editor_url = ""
            if contract_file:
                contract_file_path = f"{path.rstrip('/')}/{contract_file}" if path else ""
                file_id = str(getattr(performer, "contract_project_file_id", "") or "").strip()
                if not file_id:
                    try:
                        file_id = _resolve_contract_nextcloud_file_id(
                            client,
                            client.username,
                            contract_file_path,
                            resource_cache=resource_cache,
                        )
                    except NextcloudApiError as exc:
                        logger.warning("Could not resolve Nextcloud contract DOCX file id for performer %s: %s", performer.pk, exc)
                        file_id = ""
                    if file_id:
                        performer.contract_project_file_id = file_id
                        Performer.objects.filter(pk=performer.pk).update(contract_project_file_id=file_id)
                if file_id and target_path:
                    editor_url = client.build_files_open_url(file_id, target_path)
                if not editor_url and file_id:
                    editor_url = _build_contract_file_redirect_url(client, file_id)
                if not editor_url:
                    editor_url = _build_contract_child_url(client, target_path, contract_file)
            if editor_url:
                performer.contract_project_docx_file_url = editor_url


def _contracts_development_context():
    registrations = (
        ProjectRegistration.objects
        .select_related("country", "group_member", "type")
        .all()
    )
    return {"registrations": registrations}


def _render_contracts_development_updated(request):
    resp = render(request, CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE, _contracts_development_context())
    resp["HX-Trigger"] = "contracts-updated"
    return resp


def _render_contracts_project_registration_form(request, form, *, action, registration=None):
    return render(
        request,
        CONTRACTS_PROJECT_REG_FORM_TEMPLATE,
        {"form": form, "action": action, "registration": registration},
    )


def _normalize_contract_development_positions():
    items = ProjectRegistration.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ProjectRegistration.objects.filter(pk=item.pk).update(position=idx)


@login_required
@require_http_methods(["GET"])
def contracts_partial(request):
    return render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))


@login_required
@require_http_methods(["GET"])
def contracts_development_partial(request):
    return render(request, CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE, _contracts_development_context())


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contracts_project_registration_create(request):
    if request.method == "GET":
        return _render_contracts_project_registration_form(
            request, ContractProjectRegistrationForm(), action="create",
        )

    form = ContractProjectRegistrationForm(request.POST)
    if not form.is_valid():
        resp = _render_contracts_project_registration_form(request, form, action="create")
        resp["HX-Retarget"] = "#contracts-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    from projects_app.views import _next_position, _sync_selection_kwargs, _sync_to_legal_entity_record

    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ProjectRegistration)
    obj.save()
    _sync_to_legal_entity_record(
        obj.customer,
        obj.country,
        obj.identifier,
        obj.registration_number,
        obj.registration_date,
        request.user,
        business_entity_source="[Проекты / Заказчик]",
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contracts_project_registration_edit(request, pk):
    registration = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        return _render_contracts_project_registration_form(
            request,
            ContractProjectRegistrationForm(instance=registration),
            action="edit",
            registration=registration,
        )

    form = ContractProjectRegistrationForm(request.POST, instance=registration)
    if not form.is_valid():
        resp = _render_contracts_project_registration_form(
            request, form, action="edit", registration=registration,
        )
        resp["HX-Retarget"] = "#contracts-modal .modal-content"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    from projects_app.views import _sync_selection_kwargs, _sync_to_legal_entity_record

    obj = form.save()
    _sync_to_legal_entity_record(
        obj.customer,
        obj.country,
        obj.identifier,
        obj.registration_number,
        obj.registration_date,
        request.user,
        business_entity_source="[Проекты / Заказчик]",
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def contracts_project_registration_delete(request, pk):
    registration = get_object_or_404(ProjectRegistration, pk=pk)
    registration.delete()
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def contracts_project_registration_move_up(request, pk):
    _normalize_contract_development_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        ProjectRegistration.objects.filter(pk=current.id).update(position=previous.position)
        ProjectRegistration.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_contract_development_positions()
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def contracts_project_registration_move_down(request, pk):
    _normalize_contract_development_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, nxt = items[idx], items[idx + 1]
        ProjectRegistration.objects.filter(pk=current.id).update(position=nxt.position)
        ProjectRegistration.objects.filter(pk=nxt.id).update(position=current.position)
        _normalize_contract_development_positions()
    return _render_contracts_development_updated(request)


def _get_cloud_upload_user(user):
    """Return a user context suitable for cloud uploads."""
    if is_nextcloud_primary():
        return user
    return get_any_connected_service_user()


def _upload_scan_to_cloud_bytes(user, performer, filename, file_bytes):
    """Upload scan bytes to the selected cloud storage and return the public URL."""
    if not performer.contract_project_disk_folder:
        logger.warning("Cloud upload skipped: no cloud folder for performer %s", performer.pk)
        return ""
    try:
        cloud_user = _get_cloud_upload_user(user)
    except CloudStorageNotReadyError:
        logger.warning("Cloud upload skipped: selected backend is not migrated for contract scans")
        return ""
    if not cloud_user:
        logger.warning("Cloud upload skipped: no connected cloud account found")
        return ""
    try:
        disk_path = f"{performer.contract_project_disk_folder}/{filename}"
        ok = cloud_upload_file(cloud_user, disk_path, file_bytes)
        if not ok:
            logger.error("Cloud upload_file returned False for %s", disk_path)
            return ""
        public_url = cloud_publish_resource(cloud_user, disk_path)
        return public_url or ""
    except CloudStorageNotReadyError:
        logger.warning("Cloud upload skipped: selected backend is not migrated for contract scans")
        return ""
    except Exception:
        logger.exception("Cloud upload failed for scan %s", filename)
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
        from django.core.files.storage import default_storage

        has_new_scan = "contract_employee_scan" in request.FILES
        old_scan_path = performer.contract_employee_scan.name if performer.contract_employee_scan else ""
        clear_scan = bool(request.POST.get("contract_employee_scan-clear")) and not has_new_scan

        has_new_signed = "contract_signed_scan_file" in request.FILES
        old_signed_path = performer.contract_signed_scan_file.name if performer.contract_signed_scan_file else ""
        clear_signed = bool(request.POST.get("contract_signed_scan_file-clear")) and not has_new_signed

        if has_new_scan:
            scan_name = _compute_scan_name(performer)
            _rename_uploaded_file(request.FILES["contract_employee_scan"], scan_name)
        else:
            scan_name = ""

        if has_new_signed:
            signed_name = _compute_signed_scan_name(performer)
            _rename_uploaded_file(request.FILES["contract_signed_scan_file"], signed_name)
        else:
            signed_name = ""

        form = ContractSigningForm(request.POST, request.FILES, instance=performer)
        if form.is_valid():
            scan_file_data = None
            if has_new_scan:
                f = request.FILES["contract_employee_scan"]
                f.seek(0)
                scan_file_data = f.read()

            signed_file_data = None
            if has_new_signed:
                f = request.FILES["contract_signed_scan_file"]
                f.seek(0)
                signed_file_data = f.read()

            scan_url = ""
            if has_new_scan and scan_file_data is not None:
                scan_url = _upload_scan_to_cloud_bytes(
                    request.user, performer, request.FILES["contract_employee_scan"].name, scan_file_data,
                )
                if not scan_url:
                    form.add_error("contract_employee_scan", "Не удалось загрузить файл в облачное хранилище.")

            signed_url = ""
            if has_new_signed and signed_file_data is not None:
                signed_url = _upload_scan_to_cloud_bytes(
                    request.user, performer, request.FILES["contract_signed_scan_file"].name, signed_file_data,
                )
                if not signed_url:
                    form.add_error("contract_signed_scan_file", "Не удалось загрузить файл в облачное хранилище.")

            if form.errors:
                resp = render(request, "contracts_app/signing_form.html", {
                    "form": form,
                    "performer": performer,
                })
                resp["HX-Retarget"] = "#contracts-modal .modal-content"
                resp["HX-Reswap"] = "innerHTML"
                return resp

            obj = performer
            update_fields = []
            sibling_updates = {}
            paths_to_delete = []

            if has_new_scan:
                obj.contract_scan_document = scan_name
                obj.contract_upload_date = timezone.now()
                obj.contract_employee_scan_link = scan_url
                obj.contract_employee_scan = ""
                update_fields.extend([
                    "contract_scan_document",
                    "contract_upload_date",
                    "contract_employee_scan_link",
                    "contract_employee_scan",
                ])
                sibling_updates.update({
                    "contract_employee_scan_link": obj.contract_employee_scan_link,
                    "contract_scan_document": obj.contract_scan_document,
                    "contract_upload_date": obj.contract_upload_date,
                    "contract_send_date": obj.contract_send_date,
                    "contract_employee_scan": "",
                })
                if old_scan_path:
                    paths_to_delete.append(old_scan_path)
            elif clear_scan:
                obj.contract_scan_document = ""
                obj.contract_upload_date = None
                obj.contract_employee_scan_link = ""
                obj.contract_employee_scan = ""
                update_fields.extend([
                    "contract_scan_document",
                    "contract_upload_date",
                    "contract_employee_scan_link",
                    "contract_employee_scan",
                ])
                sibling_updates.update({
                    "contract_employee_scan_link": obj.contract_employee_scan_link,
                    "contract_scan_document": obj.contract_scan_document,
                    "contract_upload_date": obj.contract_upload_date,
                    "contract_send_date": obj.contract_send_date,
                    "contract_employee_scan": "",
                })
                if old_scan_path:
                    paths_to_delete.append(old_scan_path)

            if has_new_signed:
                obj.contract_signed_scan = signed_name
                obj.contract_signed_scan_upload_date = timezone.now()
                obj.contract_signed_scan_link = signed_url
                obj.contract_signed_scan_file = ""
                update_fields.extend([
                    "contract_signed_scan",
                    "contract_signed_scan_upload_date",
                    "contract_signed_scan_link",
                    "contract_signed_scan_file",
                ])
                sibling_updates.update({
                    "contract_signed_scan": obj.contract_signed_scan,
                    "contract_signed_scan_link": obj.contract_signed_scan_link,
                    "contract_signed_scan_upload_date": obj.contract_signed_scan_upload_date,
                    "contract_signed_scan_file": "",
                })
                if old_signed_path:
                    paths_to_delete.append(old_signed_path)
            elif clear_signed:
                obj.contract_signed_scan = ""
                obj.contract_signed_scan_upload_date = None
                obj.contract_signed_scan_link = ""
                obj.contract_signed_scan_file = ""
                update_fields.extend([
                    "contract_signed_scan",
                    "contract_signed_scan_upload_date",
                    "contract_signed_scan_link",
                    "contract_signed_scan_file",
                ])
                sibling_updates.update({
                    "contract_signed_scan": obj.contract_signed_scan,
                    "contract_signed_scan_link": obj.contract_signed_scan_link,
                    "contract_signed_scan_upload_date": obj.contract_signed_scan_upload_date,
                    "contract_signed_scan_file": "",
                })
                if old_signed_path:
                    paths_to_delete.append(old_signed_path)

            if update_fields:
                obj.save(update_fields=update_fields)

            if obj.contract_batch_id and sibling_updates:
                Performer.objects.filter(
                    contract_batch_id=obj.contract_batch_id,
                ).exclude(pk=obj.pk).update(
                    **sibling_updates,
                )
            for path in paths_to_delete:
                try:
                    default_storage.delete(path)
                except Exception:
                    pass
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


def _compute_scan_name_base(performer, suffix):
    project_number = ""
    if performer.registration:
        project_number = str(performer.registration.number or "")
    executor_raw = " ".join(str(performer.executor or "").split())
    if executor_raw:
        parts = executor_raw.split(" ")
        last_name = parts[0]
        initials = "".join(p[0] for p in parts[1:3] if p)
        executor_short = f"{last_name} {initials}".strip()
    else:
        executor_short = "Unknown"
    addendum_suffix = ""
    if performer.contract_is_addendum:
        addendum_suffix = f"_ДС{performer.contract_addendum_number or ''}"
    return f"Договор {project_number}_{executor_short}{addendum_suffix}_{suffix}".strip()


def _compute_scan_name(performer):
    return _compute_scan_name_base(performer, "1п")


def _compute_signed_scan_name(performer):
    return _compute_scan_name_base(performer, "2п")


def _rename_uploaded_file(uploaded_file, new_basename):
    ext = os.path.splitext(uploaded_file.name)[1]
    uploaded_file.name = new_basename + ext


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_scan_upload(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related("registration"),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    uploaded_file = request.FILES.get("contract_employee_scan")
    if not uploaded_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)

    scan_name = _compute_scan_name(performer)
    _rename_uploaded_file(uploaded_file, scan_name)
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    scan_url = _upload_scan_to_cloud_bytes(request.user, performer, uploaded_file.name, file_bytes)
    if not scan_url:
        return JsonResponse({"ok": False, "error": "Не удалось загрузить файл в облачное хранилище."}, status=400)

    performer.contract_employee_scan = ""
    performer.contract_scan_document = scan_name
    performer.contract_upload_date = timezone.now()
    performer.contract_employee_scan_link = scan_url
    performer.save(
        update_fields=[
            "contract_employee_scan",
            "contract_scan_document",
            "contract_upload_date",
            "contract_employee_scan_link",
        ]
    )

    if performer.contract_batch_id:
        Performer.objects.filter(
            contract_batch_id=performer.contract_batch_id,
        ).exclude(pk=performer.pk).update(
            contract_employee_scan="",
            contract_employee_scan_link=performer.contract_employee_scan_link,
            contract_scan_document=performer.contract_scan_document,
            contract_upload_date=performer.contract_upload_date,
        )

    return JsonResponse(
        {
            "ok": True,
            "scan_name": scan_name,
            "storage_label": get_primary_cloud_storage_label(),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_signed_scan_upload(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related("registration"),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    uploaded_file = request.FILES.get("contract_signed_scan_file")
    if not uploaded_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)

    scan_name = _compute_signed_scan_name(performer)
    _rename_uploaded_file(uploaded_file, scan_name)
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    scan_url = _upload_scan_to_cloud_bytes(
        request.user, performer, uploaded_file.name, file_bytes,
    )
    if not scan_url:
        return JsonResponse({"ok": False, "error": "Не удалось загрузить файл в облачное хранилище."}, status=400)

    performer.contract_signed_scan_file = ""
    performer.contract_signed_scan = scan_name
    performer.contract_signed_scan_upload_date = timezone.now()
    performer.contract_signed_scan_link = scan_url
    performer.save(update_fields=[
        "contract_signed_scan_file",
        "contract_signed_scan",
        "contract_signed_scan_upload_date",
        "contract_signed_scan_link",
    ])

    if performer.contract_batch_id:
        Performer.objects.filter(
            contract_batch_id=performer.contract_batch_id,
        ).exclude(pk=performer.pk).update(
            contract_signed_scan_file="",
            contract_signed_scan_link=performer.contract_signed_scan_link,
            contract_signed_scan=performer.contract_signed_scan,
            contract_signed_scan_upload_date=performer.contract_signed_scan_upload_date,
        )

    return JsonResponse(
        {
            "ok": True,
            "scan_name": scan_name,
            "storage_label": get_primary_cloud_storage_label(),
        }
    )


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
                    contract_date=obj.contract_date,
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
    templates = list(
        ContractTemplate.objects
        .select_related("product", "group_member")
        .prefetch_related("group_members", "products")
        .all()
    )
    order_map = _group_member_order_map()
    for t in templates:
        groups = list(t.group_members.all())
        if groups:
            t.group_display = ", ".join(_group_member_short(group, order_map.get(group.pk, 0)) for group in groups)
        elif t.group_member_id:
            t.group_display = _group_member_short(t.group_member, order_map.get(t.group_member_id, 0))
        else:
            t.group_display = "Все"
        products = list(t.products.all())
        if products:
            t.product_display = ", ".join((product.short_name or str(product)).strip() for product in products)
        elif t.product_id:
            t.product_display = t.product.short_name or str(t.product)
        else:
            t.product_display = "Все"
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

    representative_performers = list(
        Performer.objects
        .filter(pk__in=performer_ids, contract_batch_id__isnull=False)
    )
    if not representative_performers:
        return JsonResponse({"ok": False, "error": "Исполнители не найдены."}, status=400)

    batch_ids = {p.contract_batch_id for p in representative_performers}
    performers = list(
        Performer.objects
        .filter(contract_batch_id__in=batch_ids)
        .select_related("registration", "registration__type", "currency", "employee", "typical_section")
    )

    try:
        create_scan_notifications(performers=performers, sender=request.user)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    now = timezone.now()
    Performer.objects.filter(
        contract_batch_id__in=batch_ids,
        contract_send_date__isnull=True,
    ).update(contract_send_date=now)

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
            Notification.objects.filter(pk__in=expert_notif_ids).update(
                is_processed=True,
                action_at=now,
                updated_at=now,
            )

    return JsonResponse({"ok": True})
