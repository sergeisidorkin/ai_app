import calendar
import json
import logging
import os
import sys
from datetime import date as dt_date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from classifiers_app.models import LegalEntityRecord
from core.cloud_storage import (
    build_folder_url,
    get_nextcloud_root_path,
    get_primary_cloud_storage_label,
    is_nextcloud_primary,
)
from core.proposal_registry_columns import (
    get_proposal_dispatch_ui_columns,
    get_proposal_payment_schedule_ui_columns,
    get_proposal_registry_ui_columns,
)
from core.section_labels import get_app_section_label
from experts_app.models import ExpertProfile, ExpertProfileSpecialty
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError, NextcloudNetworkError
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.workspace import build_proposal_workspace_path, create_proposal_workspace
from policy_app.models import (
    Product,
    ServiceGoalReport,
    SpecialtyTariff,
    SYSTEM_DSC_SECTION_CODE,
    SYSTEM_DSC_SECTION_DEFAULTS,
    ServiceBlockClassifierSpecialty,
    Tariff,
    TypicalSection,
    TypicalServiceComposition,
    TypicalServiceTerm,
    build_consulting_catalog_meta,
)
from projects_app.models import ProjectRegistration, ProjectRegistrationProduct, _sync_project_registration_primary_product
from smtp_app.models import ExternalSMTPAccount
from users_app.contact_sync import (
    annotate_staff_locked_contacts,
    contact_fields_are_staff_locked,
    staff_employee_for_dispatch_contact,
)
from users_app.models import Employee

from .cbr import get_cbr_eur_rate_for_today, get_cbr_eur_rate_text
from .forms import (
    DispatchRecipientFormRow,
    ProposalDispatchForm,
    ProposalRegistrationForm,
    ProposalTemplateForm,
    ProposalVariableForm,
    _proposal_group_member_order_map,
    _proposal_group_member_short,
    allowed_manual_proposal_statuses,
    can_edit_locked_proposal_status,
    proposal_variable_registry_json,
)
from .document_generation import (
    DOCX_CONTENT_TYPE,
    LOCAL_PROPOSAL_PATH_PREFIX,
    LocalProposalFolderError,
    build_proposal_docx_source_url,
    convert_docx_bytes_to_pdf_locally,
    generate_and_store_proposal_pdf,
    get_generated_docx_path,
    get_generated_pdf_path,
    get_proposal_docx_source_token_payload,
    is_local_proposal_path,
    is_onlyoffice_conversion_configured,
    load_existing_proposal_docx_bytes,
    local_proposal_folder_enabled,
    local_proposal_folder_placeholder,
    resolve_proposal_generation_source,
    store_existing_proposal_docx_bytes,
    store_generated_documents,
    store_generated_documents_locally,
    store_generated_pdf_document,
)
from .models import (
    ProposalDispatchRecipient,
    ProposalRegistration,
    ProposalTemplate,
    ProposalVariable,
    ProposalVersionError,
    mirror_primary_dispatch_recipient,
)
from .services import (
    PROPOSAL_DELIVERY_CHANNEL_STATUS_ONLY,
    normalize_proposal_delivery_channels,
    send_proposal_dispatch_emails,
)
from .variable_resolver import resolve_variables
from .xlsx_export import build_commercial_xlsx

PROPOSALS_PARTIAL_TEMPLATE = "proposals_app/proposals_partial.html"
PROPOSAL_FORM_TEMPLATE = "proposals_app/proposal_form_page.html"
PROPOSAL_DISPATCH_FORM_TEMPLATE = "proposals_app/proposal_dispatch_form.html"
PROPOSAL_TEMPLATE_FORM_TEMPLATE = "proposals_app/proposal_template_form.html"
PROPOSAL_VARIABLE_FORM_TEMPLATE = "proposals_app/proposal_variable_form.html"
PROPOSAL_VARIABLES_SECTION_TEMPLATE = "proposals_app/proposal_variables_section.html"

HX_TRIGGER_HEADER = "HX-Trigger"
HX_PROPOSALS_UPDATED_EVENT = "proposals-updated"
PROPOSAL_NEXTCLOUD_TARGETS_SESSION_KEY = "proposal_nextcloud_target_paths"
logger = logging.getLogger(__name__)
PROPOSAL_FACSIMILE_PLACEHOLDER = "[[facsimile]]"
PROPOSAL_FACSIMILE_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"}
PROPOSAL_CONTRACT_DETAILS_SECTION_PATH = (
    f"{get_app_section_label('experts')} -> Реквизиты для договора"
)

# CI can import this module through either `proposals_app.views` or
# `ai_app.proposals_app.views`. Keep both names bound to the same module object
# so patch() targets stay stable.
sys.modules.setdefault("proposals_app.views", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.views", sys.modules[__name__])


def _get_proposal_signer_expert_profile(user_id: int | None) -> ExpertProfile:
    try:
        clean_user_id = int(user_id or 0)
    except (TypeError, ValueError):
        clean_user_id = 0
    if clean_user_id <= 0:
        raise RuntimeError("Не удалось определить пользователя, подписывающего ТКП.")
    try:
        return ExpertProfile.objects.select_related(
            "employee",
            "employee__user",
        ).prefetch_related(
            "contract_details_records__citizenship_record",
        ).get(employee__user_id=clean_user_id)
    except ExpertProfile.DoesNotExist as exc:
        raise RuntimeError(
            "Для текущего пользователя не заполнена строка "
            f"в разделе «{PROPOSAL_CONTRACT_DETAILS_SECTION_PATH}»."
        ) from exc


def _get_proposal_signer_contract_details(user_id: int | None):
    profile = _get_proposal_signer_expert_profile(user_id)
    contract_details = profile.default_contract_details(require_facsimile=True)
    if contract_details is None:
        raise RuntimeError(
            "Для текущего пользователя не заполнена строка "
            f"в разделе «{PROPOSAL_CONTRACT_DETAILS_SECTION_PATH}»."
        )
    return contract_details


def _load_proposal_signer_facsimile_bytes(user_id: int | None) -> bytes:
    contract_details = _get_proposal_signer_contract_details(user_id)
    facsimile = getattr(contract_details, "facsimile_file", None)
    facsimile_name = str(getattr(facsimile, "name", "") or "").strip()
    if not facsimile_name:
        raise RuntimeError(
            "Для текущего пользователя не заполнено поле «Факсимиле» "
            f"в разделе «{PROPOSAL_CONTRACT_DETAILS_SECTION_PATH}»."
        )

    file_extension = os.path.splitext(facsimile_name)[1].lower()
    if file_extension and file_extension not in PROPOSAL_FACSIMILE_ALLOWED_EXTENSIONS:
        raise RuntimeError("Факсимиле должно быть изображением в формате PNG, JPG, GIF, BMP или TIFF.")

    try:
        facsimile.open("rb")
        try:
            facsimile_bytes = facsimile.read()
        finally:
            facsimile.close()
    except Exception as exc:
        raise RuntimeError("Не удалось прочитать файл факсимиле текущего пользователя.") from exc

    if not facsimile_bytes:
        raise RuntimeError("Файл факсимиле текущего пользователя пустой.")
    return facsimile_bytes


def _normalize_nextcloud_path(path: str) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    if raw_path == "/":
        return "/"
    return f"/{raw_path.strip('/')}"


def _nextcloud_path_parts(path: str) -> list[str]:
    normalized = _normalize_nextcloud_path(path)
    if normalized in {"", "/"}:
        return []
    return [part for part in normalized.strip("/").split("/") if part]


def _build_shared_target_candidate(
    normalized_path: str,
    shared_path: str,
    target_path: str,
) -> tuple[int, int, int, int, str, str] | None:
    normalized_shared_path = _normalize_nextcloud_path(shared_path)
    clean_target_path = str(target_path or "").strip()
    if not normalized_shared_path or not clean_target_path:
        return None

    shared_parts = _nextcloud_path_parts(normalized_shared_path)
    if normalized_path == normalized_shared_path or normalized_path.startswith(f"{normalized_shared_path}/"):
        suffix = normalized_path[len(normalized_shared_path) :].strip("/")
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

    path_parts = _nextcloud_path_parts(normalized_path)
    if not path_parts or not shared_parts or len(shared_parts) > len(path_parts):
        return None

    for start_index in range(len(path_parts) - len(shared_parts) + 1):
        if path_parts[start_index : start_index + len(shared_parts)] != shared_parts:
            continue
        suffix_parts = path_parts[start_index + len(shared_parts) :]
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


def _get_normalized_nextcloud_root_path() -> str:
    return _normalize_nextcloud_path(get_nextcloud_root_path())


def _resolve_shared_target_path(path: str, share_map: dict[str, object], *, root_path: str = "") -> str:
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path:
        return ""

    candidates = []
    for shared_path, share in share_map.items():
        target_path = _normalize_viewer_target_path(
            getattr(share, "target_path", "") or "",
            root_path=root_path,
        )
        candidate = _build_shared_target_candidate(normalized_path, shared_path, target_path)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return ""

    _, _, _, _, _, resolved_target_path = max(candidates, key=lambda item: item[:5])
    return resolved_target_path


def _resolve_target_path_via_user_share_lookup(
    client,
    owner_user_id: str,
    path: str,
    share_with_user_id: str,
    *,
    root_path: str = "",
    share_lookup_cache: dict[str, object] | None = None,
):
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path or normalized_path == "/":
        return "", None

    current_path = normalized_path
    last_share = None
    if share_lookup_cache is None:
        share_lookup_cache = {}
    while current_path and current_path != "/":
        if current_path not in share_lookup_cache:
            try:
                share_lookup_cache[current_path] = client.get_user_share(
                    owner_user_id,
                    current_path,
                    share_with_user_id,
                )
            except NextcloudApiError as exc:
                logger.warning(
                    "Could not resolve Nextcloud share for proposal path %s "
                    "(lookup path %s, viewer %s); leaving its link unavailable: %s",
                    normalized_path,
                    current_path,
                    share_with_user_id,
                    exc,
                )
                share_lookup_cache[current_path] = None
                return "", last_share
        share = share_lookup_cache[current_path]
        if share is not None:
            last_share = share
            target_path = _normalize_viewer_target_path(
                getattr(share, "target_path", "") or "",
                root_path=root_path,
            )
            if target_path:
                candidate = _build_shared_target_candidate(normalized_path, current_path, target_path)
                if candidate is not None:
                    return candidate[-1], share
        current_path = current_path.rsplit("/", 1)[0] or "/"

    return "", last_share


def _normalize_viewer_target_path(path: str, *, root_path: str = "") -> str:
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path:
        return ""
    if not root_path or root_path == "/":
        return normalized_path
    if normalized_path == root_path:
        return "/"
    if normalized_path.startswith(f"{root_path}/"):
        stripped_path = _normalize_nextcloud_path(normalized_path[len(root_path) :])
        if stripped_path:
            return stripped_path
    return normalized_path


def _get_cached_proposal_target_paths(request=None, *, root_path: str = "") -> dict[str, str]:
    if request is None or not hasattr(request, "session"):
        return {}
    raw_value = request.session.get(PROPOSAL_NEXTCLOUD_TARGETS_SESSION_KEY)
    if not isinstance(raw_value, dict):
        return {}
    cached = {}
    for path, target_path in raw_value.items():
        normalized_path = _normalize_nextcloud_path(path)
        normalized_target_path = _normalize_viewer_target_path(target_path, root_path=root_path)
        if normalized_path and normalized_target_path:
            cached[normalized_path] = normalized_target_path
    return cached


def _cache_proposal_target_path(request, proposal_path: str, target_path: str, *, root_path: str = "") -> None:
    normalized_path = _normalize_nextcloud_path(proposal_path)
    normalized_target_path = _normalize_viewer_target_path(target_path, root_path=root_path)
    if (
        request is None
        or not hasattr(request, "session")
        or not normalized_path
        or not normalized_target_path
    ):
        return
    cached = _get_cached_proposal_target_paths(request, root_path=root_path)
    cached[normalized_path] = normalized_target_path
    request.session[PROPOSAL_NEXTCLOUD_TARGETS_SESSION_KEY] = cached
    request.session.modified = True


def _serialize_nextcloud_share(share) -> dict[str, object]:
    if share is None:
        return {}
    return {
        "share_id": str(getattr(share, "share_id", "") or ""),
        "path": _normalize_nextcloud_path(getattr(share, "path", "") or ""),
        "target_path": str(getattr(share, "target_path", "") or ""),
        "permissions": int(getattr(share, "permissions", 0) or 0),
        "share_with": str(getattr(share, "share_with", "") or ""),
    }


def _proposal_link_debug_enabled(request=None) -> bool:
    if request is None:
        return False
    raw_value = str(request.GET.get("debug_nextcloud_links") or "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _log_nextcloud_resolution_debug(
    *,
    path: str,
    share_map: dict[str, object],
    direct_share=None,
    resolved_target_path: str = "",
    lookup_share=None,
    final_target_path: str = "",
    final_url: str = "",
    user=None,
    nextcloud_user_id: str = "",
    reason: str = "",
    force: bool = False,
) -> None:
    if not (force or not final_target_path):
        return

    normalized_path = _normalize_nextcloud_path(path)
    related_shares = []
    for shared_path, share in sorted(share_map.items()):
        normalized_shared_path = _normalize_nextcloud_path(shared_path)
        if not normalized_shared_path:
            continue
        if normalized_path == normalized_shared_path or normalized_path.startswith(f"{normalized_shared_path}/"):
            related_shares.append(_serialize_nextcloud_share(share))

    payload = {
        "reason": reason,
        "user_id": getattr(user, "pk", None),
        "nextcloud_user_id": nextcloud_user_id,
        "path": normalized_path,
        "resolved_target_path": resolved_target_path,
        "direct_share": _serialize_nextcloud_share(direct_share),
        "lookup_share": _serialize_nextcloud_share(lookup_share),
        "related_shares": related_shares,
        "final_target_path": final_target_path,
        "final_url": final_url,
    }
    logger.warning("Nextcloud proposal folder resolution debug: %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))


def staff_required(user):
    return user.is_authenticated and user.is_staff


def _next_position(model) -> int:
    last = model.objects.aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def _sync_to_legal_entity_record(
    short_name,
    country,
    identifier,
    registration_number,
    registration_date,
    user=None,
    selected_identifier_record_id=None,
    selected_from_autocomplete=False,
    business_entity_source="",
    registration_region="",
):
    from classifiers_app.views import sync_autocomplete_registry_entry

    return sync_autocomplete_registry_entry(
        short_name=short_name,
        country=country,
        identifier_type=identifier,
        registration_number=registration_number,
        registration_date=registration_date,
        registration_region=registration_region,
        user=user,
        selected_identifier_record_id=selected_identifier_record_id,
        selected_from_autocomplete=selected_from_autocomplete,
        business_entity_source=business_entity_source,
    )


def _reuse_identifier_kwargs(identifier_record):
    if identifier_record is None:
        return {
            "selected_identifier_record_id": None,
            "selected_from_autocomplete": False,
        }
    return {
        "selected_identifier_record_id": identifier_record.pk,
        "selected_from_autocomplete": True,
    }


def _remember_proposal_party_links(proposal, request):
    customer_identifier = _sync_to_legal_entity_record(
        proposal.customer,
        proposal.country,
        proposal.identifier,
        proposal.registration_number,
        proposal.registration_date,
        registration_region=proposal.registration_region,
        user=request.user,
        business_entity_source="[ТКП / Заказчик]",
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    if proposal.asset_owner_matches_customer:
        owner_identifier = customer_identifier
    else:
        owner_identifier = _sync_to_legal_entity_record(
            proposal.asset_owner,
            proposal.asset_owner_country,
            proposal.asset_owner_identifier,
            proposal.asset_owner_registration_number,
            proposal.asset_owner_registration_date,
            registration_region=proposal.asset_owner_region,
            user=request.user,
            business_entity_source="[ТКП / Владелец активов]",
            **_sync_selection_kwargs(request, "asset_owner_autocomplete"),
        )
    proposal.customer_identifier_record = customer_identifier
    proposal.asset_owner_identifier_record = owner_identifier
    proposal.save(update_fields=["customer_identifier_record", "asset_owner_identifier_record"])


def _proposal_related_row_has_identity(item):
    return bool((item.get("short_name") or "").strip())


def _same_registry_identity(left, right):
    left_name = (left.get("short_name") or "").strip()
    right_name = (right.get("short_name") or "").strip()
    if not left_name or left_name != right_name:
        return False
    left_number = (left.get("registration_number") or "").strip()
    right_number = (right.get("registration_number") or "").strip()
    if left_number and right_number and left_number != right_number:
        return False
    return True


def _row_reuses_linked_identifier(item):
    """Строка, заполненная из другой уже связанной строки, не открывает новую цепочку справочника."""
    if not _proposal_related_row_has_identity(item):
        return False
    if item.get("selected_from_autocomplete") or item.get("selected_identifier_record_id"):
        return False
    if item.get("user_edited"):
        return False
    return bool(item.get("copied_from_owner") or item.get("copied_from_asset"))


def _attach_related_registry_links(rows, user, business_entity_source, reuse_identifier_for=None):
    for index, item in enumerate(rows or []):
        reused = reuse_identifier_for(item, index) if reuse_identifier_for else None
        if reused is not None and _row_reuses_linked_identifier(item):
            item["identifier_record"] = reused
            continue
        if not _should_sync_proposal_related_row(item):
            item["identifier_record"] = None
            continue
        selected_identifier_record_id = item.get("selected_identifier_record_id")
        selected_from_autocomplete = bool(item.get("selected_from_autocomplete"))
        if selected_identifier_record_id and not selected_from_autocomplete:
            selected_from_autocomplete = True
        item["identifier_record"] = _sync_to_legal_entity_record(
            item["short_name"],
            item["country"],
            item["identifier"],
            item["registration_number"],
            item["registration_date"],
            user,
            selected_identifier_record_id=selected_identifier_record_id,
            selected_from_autocomplete=selected_from_autocomplete,
            business_entity_source=business_entity_source,
        )


def _link_proposal_service_volume(proposal, form, user):
    assets = getattr(form, "cleaned_assets", [])
    legal_entities = getattr(form, "cleaned_legal_entities", [])
    owner_identifier = proposal.asset_owner_identifier_record

    def reuse_owner(item, index):
        if item.get("copied_from_owner"):
            return owner_identifier
        return None

    def reuse_asset(item, index):
        if not item.get("copied_from_asset"):
            return None
        if 0 <= index < len(assets) and _same_registry_identity(assets[index], item):
            linked = assets[index].get("identifier_record")
            if linked is not None:
                return linked
        for asset in assets:
            if not _same_registry_identity(asset, item):
                continue
            linked = asset.get("identifier_record")
            if linked is not None:
                return linked
        return None

    _attach_related_registry_links(
        assets,
        user,
        "[ТКП / Объем услуг: активы]",
        reuse_identifier_for=reuse_owner,
    )
    _attach_related_registry_links(
        legal_entities,
        user,
        "[ТКП / Объем услуг: юрлица]",
        reuse_identifier_for=reuse_asset,
    )


def _autocomplete_link_state(form, prefix, stored_id):
    if getattr(form, "is_bound", False):
        raw_id = str(form.data.get(f"{prefix}_identifier_record_id") or "").strip()
        raw_flag = str(form.data.get(f"{prefix}_selected_from_autocomplete") or "").strip().lower()
        selected = raw_flag in {"1", "true", "yes", "on"} and bool(raw_id)
        return raw_id, "1" if selected else "0"
    stored = "" if stored_id in (None, "") else str(stored_id)
    return stored, "1" if stored else "0"


def _sync_dispatch_contact_to_person_registry(*, last_name, first_name="", middle_name=""):
    normalized_last_name = str(last_name or "").strip()
    normalized_first_name = str(first_name or "").strip()
    normalized_middle_name = str(middle_name or "").strip()
    if not normalized_last_name:
        return

    from contacts_app.models import PersonRecord, PhoneRecord, PositionRecord

    def refresh_related_position_sources():
        queryset = (
            PositionRecord.objects
            .filter(person__last_name=normalized_last_name)
            .select_related("person")
            .order_by("position", "id")
        )
        for position_record in queryset:
            new_source = position_record.resolve_source()
            if position_record.source != new_source:
                PositionRecord.objects.filter(pk=position_record.pk).update(source=new_source)

    person = (
        PersonRecord.objects.filter(
            last_name=normalized_last_name,
            first_name=normalized_first_name,
            middle_name=normalized_middle_name,
        )
        .order_by("position", "id")
        .first()
    )
    if person is None:
        next_position = (PersonRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        person = PersonRecord.objects.create(
            last_name=normalized_last_name,
            first_name=normalized_first_name,
            middle_name=normalized_middle_name,
            position=next_position,
        )
        next_phone_position = (PhoneRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        PhoneRecord.objects.create(
            person=person,
            country=None,
            code="",
            phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
            region="",
            phone_number="",
            extension="",
            valid_from=dt_date.today(),
            valid_to=None,
            record_date=dt_date.today(),
            record_author="",
            source="",
            position=next_phone_position,
        )
        refresh_related_position_sources()
        return

    updates = []
    if person.first_name != normalized_first_name:
        person.first_name = normalized_first_name
        updates.append("first_name")
    if person.middle_name != normalized_middle_name:
        person.middle_name = normalized_middle_name
        updates.append("middle_name")
    if updates:
        person.save(update_fields=updates)
    refresh_related_position_sources()


def _sync_selection_kwargs(request, prefix):
    selected_flag = str(request.POST.get(f"{prefix}_selected_from_autocomplete") or "").strip().lower()
    return {
        "selected_identifier_record_id": (request.POST.get(f"{prefix}_identifier_record_id") or "").strip(),
        "selected_from_autocomplete": selected_flag in {"1", "true", "yes", "on"},
    }


def _should_sync_proposal_related_row(item):
    return bool(
        (item.get("short_name") or "").strip()
        and (
            item.get("selected_from_autocomplete")
            or item.get("user_edited")
        )
    )


def _build_proposal_docx_disk_path(proposal) -> str:
    workspace_path = _normalize_nextcloud_path(getattr(proposal, "proposal_workspace_disk_path", "") or "")
    filename = str(getattr(proposal, "docx_file_name", "") or "").strip()
    if not workspace_path or not filename:
        return ""
    return f"{workspace_path.rstrip('/')}/{filename}"


def _stored_proposal_file_link(proposal, attr_name: str) -> str:
    return str(getattr(proposal, attr_name, "") or "").strip()


def _stored_docx_link(proposal) -> str:
    return _stored_proposal_file_link(proposal, "docx_file_link")


def _stored_pdf_link(proposal) -> str:
    return _stored_proposal_file_link(proposal, "pdf_file_link")


def _build_nextcloud_child_url(client, parent_path: str, child_name: str) -> str:
    normalized_parent = _normalize_nextcloud_path(parent_path)
    clean_child_name = str(child_name or "").strip().strip("/")
    if not normalized_parent or not clean_child_name:
        return ""
    if normalized_parent == "/":
        return client.build_files_url(f"/{clean_child_name}")
    return client.build_files_url(f"{normalized_parent.rstrip('/')}/{clean_child_name}")


def _nextcloud_parent_path(path: str) -> str:
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path or normalized_path == "/":
        return ""
    parent = normalized_path.rsplit("/", 1)[0]
    return parent or "/"


def _is_nextcloud_cloud_path(path: str) -> bool:
    """Return True when ``path`` points at a Nextcloud resource (not MEDIA/URL)."""
    clean_path = str(path or "").strip()
    if not clean_path:
        return False
    if clean_path.startswith(("http://", "https://")):
        return False
    if clean_path.startswith(LOCAL_PROPOSAL_PATH_PREFIX):
        return False
    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()
    if media_url and clean_path.startswith(media_url):
        return False
    return True


def _refresh_proposal_nextcloud_file_ids(proposals) -> list:
    """Resolve and persist Nextcloud file ids for proposal resources.

    Ensures ``docx_file_id`` / ``pdf_file_id`` / ``proposal_workspace_file_id``
    columns reflect the latest state in Nextcloud so that viewer-side editor
    URLs and the workspace folder link stay valid after the session cache
    expires. Paths not stored in Nextcloud (empty, HTTP(S), MEDIA) are silently
    ignored.
    """
    updated_proposals = []
    if not proposals or not is_nextcloud_primary():
        return updated_proposals
    client = NextcloudApiClient()
    if not client.is_configured:
        return updated_proposals
    owner_user_id = client.username
    resource_cache: dict[str, dict[str, str]] = {}
    for proposal in proposals:
        changed_fields: list[str] = []
        workspace_path = str(getattr(proposal, "proposal_workspace_disk_path", "") or "").strip()
        if workspace_path and not getattr(proposal, "proposal_workspace_file_id", "").strip():
            try:
                file_id = _resolve_nextcloud_file_id(
                    client,
                    owner_user_id,
                    workspace_path,
                    resource_cache=resource_cache,
                )
            except NextcloudApiError as exc:
                logger.warning(
                    "Could not resolve Nextcloud workspace file id for proposal %s: %s",
                    getattr(proposal, "pk", ""),
                    exc,
                )
                file_id = ""
            if file_id:
                proposal.proposal_workspace_file_id = file_id
                changed_fields.append("proposal_workspace_file_id")
        docx_path = _stored_docx_link(proposal)
        if _is_nextcloud_cloud_path(docx_path):
            try:
                file_id = _resolve_nextcloud_file_id(
                    client,
                    owner_user_id,
                    docx_path,
                    resource_cache=resource_cache,
                )
            except NextcloudApiError as exc:
                logger.warning(
                    "Could not resolve Nextcloud DOCX file id for proposal %s: %s",
                    getattr(proposal, "pk", ""),
                    exc,
                )
                file_id = ""
            if file_id and getattr(proposal, "docx_file_id", "") != file_id:
                proposal.docx_file_id = file_id
                changed_fields.append("docx_file_id")
        pdf_path = _stored_pdf_link(proposal)
        if _is_nextcloud_cloud_path(pdf_path):
            try:
                file_id = _resolve_nextcloud_file_id(
                    client,
                    owner_user_id,
                    pdf_path,
                    resource_cache=resource_cache,
                )
            except NextcloudApiError as exc:
                logger.warning(
                    "Could not resolve Nextcloud PDF file id for proposal %s: %s",
                    getattr(proposal, "pk", ""),
                    exc,
                )
                file_id = ""
            if file_id and getattr(proposal, "pdf_file_id", "") != file_id:
                proposal.pdf_file_id = file_id
                changed_fields.append("pdf_file_id")
        if changed_fields:
            ProposalRegistration.objects.filter(pk=proposal.pk).update(
                **{name: getattr(proposal, name) for name in changed_fields}
            )
            updated_proposals.append(proposal)
    return updated_proposals


def _resolve_nextcloud_file_id(client, owner_user_id: str, path: str, *, resource_cache=None) -> str:
    normalized_path = _normalize_nextcloud_path(path)
    parent_path = _nextcloud_parent_path(normalized_path)
    if not normalized_path or not parent_path:
        return ""
    if resource_cache is None:
        resource_cache = {}
    if parent_path not in resource_cache:
        items = client.list_resources(owner_user_id, parent_path, limit=500)
        resource_cache[parent_path] = {
            _normalize_nextcloud_path(item.get("path") or ""): str(item.get("file_id") or "").strip()
            for item in items
        }
    return str(resource_cache.get(parent_path, {}).get(normalized_path) or "")


def _build_nextcloud_editor_url(client, file_id: str, dir_path: str) -> str:
    normalized_dir = _normalize_nextcloud_path(dir_path)
    if not file_id or not normalized_dir:
        return ""
    return client.build_files_open_url(file_id, normalized_dir)


def _build_nextcloud_file_redirect_url(client, file_id: str) -> str:
    """Return Nextcloud's canonical ``/f/<fileid>`` URL.

    This URL works for every user who has access to the file regardless of how
    the parent folder is mounted, so it is our safest fallback when the viewer
    mount path is not known.
    """
    clean_file_id = str(file_id or "").strip()
    base_url = str(getattr(client, "base_url", "") or "").strip().rstrip("/")
    if not clean_file_id or not base_url:
        return ""
    return f"{base_url}/f/{quote(clean_file_id, safe='')}"


def _stored_proposal_file_id(proposal, attr_name: str) -> str:
    return str(getattr(proposal, attr_name, "") or "").strip()


def _resolve_proposal_file_open_url(
    proposal,
    *,
    file_name_attr: str,
    file_link_attr: str,
    file_id_attr: str,
    client=None,
    viewer_has_nextcloud_link: bool = False,
    resolved_workspace_target_path: str = "",
    owner_file_id: str = "",
) -> str:
    raw_link = _stored_proposal_file_link(proposal, file_link_attr)
    file_name = str(getattr(proposal, file_name_attr, "") or "").strip()
    stored_file_id = _stored_proposal_file_id(proposal, file_id_attr)
    if not raw_link and not file_name:
        return ""
    if is_local_proposal_path(raw_link):
        download_name = (
            "proposal_generated_pdf_download"
            if file_link_attr == "pdf_file_link"
            else "proposal_generated_docx_download"
        )
        return reverse(download_name, args=[proposal.pk])
    if raw_link.startswith(("http://", "https://")):
        return raw_link
    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()
    if media_url and raw_link.startswith(media_url):
        return raw_link
    if client is None:
        return build_folder_url(raw_link)

    # Prefer the DB-persisted Nextcloud file id so the link stays valid even
    # when the session cache expires or the share API momentarily fails.
    effective_file_id = stored_file_id or owner_file_id

    if viewer_has_nextcloud_link:
        stored_target_path = _normalize_viewer_target_path(
            str(getattr(proposal, "proposal_workspace_target_path", "") or "").strip(),
        )
        target_dir = resolved_workspace_target_path or stored_target_path
        if effective_file_id and target_dir:
            return _build_nextcloud_editor_url(client, effective_file_id, target_dir)
        if effective_file_id:
            # No viewer-side mount known, fall back to Nextcloud's file-id
            # redirect URL that works regardless of mountpoint.
            return _build_nextcloud_file_redirect_url(client, effective_file_id)
        if target_dir and file_name:
            return _build_nextcloud_child_url(client, target_dir, file_name)
        stored_public = (getattr(proposal, "proposal_workspace_public_url", "") or "").strip()
        return stored_public

    # Owner/service-account viewer: the raw owner path is valid, so we can keep
    # using it to build an editor URL.
    if effective_file_id:
        parent_path = _nextcloud_parent_path(raw_link)
        if parent_path:
            return _build_nextcloud_editor_url(client, effective_file_id, parent_path)
    return build_folder_url(raw_link)


def _resolve_proposal_docx_open_url(
    proposal,
    *,
    client=None,
    viewer_has_nextcloud_link: bool = False,
    resolved_workspace_target_path: str = "",
    owner_file_id: str = "",
) -> str:
    return _resolve_proposal_file_open_url(
        proposal,
        file_name_attr="docx_file_name",
        file_link_attr="docx_file_link",
        file_id_attr="docx_file_id",
        client=client,
        viewer_has_nextcloud_link=viewer_has_nextcloud_link,
        resolved_workspace_target_path=resolved_workspace_target_path,
        owner_file_id=owner_file_id,
    )


def _resolve_proposal_pdf_open_url(
    proposal,
    *,
    client=None,
    viewer_has_nextcloud_link: bool = False,
    resolved_workspace_target_path: str = "",
    owner_file_id: str = "",
) -> str:
    return _resolve_proposal_file_open_url(
        proposal,
        file_name_attr="pdf_file_name",
        file_link_attr="pdf_file_link",
        file_id_attr="pdf_file_id",
        client=client,
        viewer_has_nextcloud_link=viewer_has_nextcloud_link,
        resolved_workspace_target_path=resolved_workspace_target_path,
        owner_file_id=owner_file_id,
    )


def _attach_proposal_folder_urls(proposals, user=None, request=None, *, debug_nextcloud_links=False):
    folder_cache = {}
    share_resolution_paths = set()
    viewer_has_nextcloud_link = False
    resolved_target_cache = {}
    resource_cache = {}

    def _stored_public(proposal):
        return (getattr(proposal, "proposal_workspace_public_url", "") or "").strip()

    def _assign_fallback_urls_without_share_resolution():
        for proposal in proposals:
            path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
            if path:
                folder_cache.setdefault(path, build_folder_url(path))
                proposal.proposal_workspace_folder_url = _stored_public(proposal) or folder_cache.get(path, "")
            proposal.proposal_docx_file_url = _resolve_proposal_docx_open_url(proposal)
            proposal.proposal_pdf_file_url = _resolve_proposal_pdf_open_url(proposal)

    for proposal in proposals:
        path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
        proposal.proposal_workspace_folder_url = _stored_public(proposal)
        proposal.proposal_docx_file_url = ""
        proposal.proposal_pdf_file_url = ""
        if path:
            folder_cache.setdefault(path, build_folder_url(path))
            share_resolution_paths.add(path)

    if not proposals or not is_nextcloud_primary():
        _assign_fallback_urls_without_share_resolution()
        return

    client = NextcloudApiClient()
    if not client.is_configured:
        _assign_fallback_urls_without_share_resolution()
        return

    live_share_lookup = bool(
        getattr(settings, "NEXTCLOUD_LIVE_SHARE_LOOKUP_ON_READ", True)
    )
    if live_share_lookup and NextcloudApiClient.network_cooldown_active():
        # The host failed at transport level moments ago: every live lookup
        # would burn connect-timeout + retry per proposal. Render from the
        # persisted file ids / public links instead (same fallback as a
        # failed lookup) and let the next request after the cooldown retry.
        logger.info(
            "Nextcloud network cooldown is active; rendering the proposals "
            "registry from saved links without live share resolution",
        )
        live_share_lookup = False
    normalized_root_path = _get_normalized_nextcloud_root_path()
    resolved_cache = {}
    cached_target_paths = _get_cached_proposal_target_paths(request, root_path=normalized_root_path)
    share_lookup_cache = {}
    if share_resolution_paths and user is not None and getattr(user, "is_authenticated", False):
        link = NextcloudUserLink.objects.filter(user=user).first()
        if (
            link
            and link.nextcloud_user_id
            and link.nextcloud_user_id != client.username
        ):
            viewer_has_nextcloud_link = True
            share_map = {}
            if live_share_lookup:
                try:
                    share_map = client.list_user_shares(
                        client.username,
                        link.nextcloud_user_id,
                    )
                except NextcloudApiError as exc:
                    logger.warning(
                        "Could not load Nextcloud share map for proposals table; "
                        "rendering the registry without live share resolution: %s",
                        exc,
                    )
                    live_share_lookup = False
                client.prime_user_share_cache(
                    client.username,
                    link.nextcloud_user_id,
                    share_map,
                )

            stored_target_paths = {
                (getattr(proposal, "proposal_workspace_disk_path", "") or "").strip(): _normalize_viewer_target_path(
                    (getattr(proposal, "proposal_workspace_target_path", "") or "").strip(),
                )
                for proposal in proposals
                if (getattr(proposal, "proposal_workspace_disk_path", "") or "").strip()
            }
            for path in share_resolution_paths:
                target_path = _resolve_shared_target_path(path, share_map, root_path=normalized_root_path)
                direct_share = share_map.get(path)
                direct_target_path = _normalize_viewer_target_path(
                    getattr(direct_share, "target_path", "") or "",
                    root_path=normalized_root_path,
                )
                lookup_share = None
                if not target_path and direct_target_path:
                    target_path = direct_target_path
                if not target_path:
                    # Canonical viewer mountpoint captured at workspace creation
                    # (persisted in ``proposal_workspace_target_path``) is our
                    # most reliable fallback when the live share API is silent.
                    target_path = stored_target_paths.get(path, "")
                if not target_path:
                    target_path = cached_target_paths.get(path, "")
                if not target_path and live_share_lookup and NextcloudApiClient.network_cooldown_active():
                    # A lookup earlier in this render already hit a transport
                    # error; do not pay the timeout again for every path.
                    live_share_lookup = False
                if not target_path and live_share_lookup:
                    target_path, lookup_share = _resolve_target_path_via_user_share_lookup(
                        client,
                        client.username,
                        path,
                        link.nextcloud_user_id,
                        root_path=normalized_root_path,
                        share_lookup_cache=share_lookup_cache,
                    )
                if target_path:
                    resolved_target_cache[path] = target_path
                    resolved_cache[path] = client.build_files_url(target_path)
                    _cache_proposal_target_path(
                        request,
                        path,
                        target_path,
                        root_path=normalized_root_path,
                    )
                _log_nextcloud_resolution_debug(
                    path=path,
                    share_map=share_map,
                    direct_share=direct_share,
                    resolved_target_path=_resolve_shared_target_path(
                        path,
                        share_map,
                        root_path=normalized_root_path,
                    ),
                    lookup_share=lookup_share,
                    final_target_path=target_path,
                    final_url=resolved_cache.get(path, ""),
                    user=user,
                    nextcloud_user_id=link.nextcloud_user_id,
                    reason="share-resolution",
                    force=debug_nextcloud_links,
                )

    def _maybe_resolve_owner_file_id(proposal, *, stored_attr: str, cloud_path: str) -> str:
        nonlocal live_share_lookup
        # Avoid an extra PROPFIND when the file id is already persisted in DB.
        stored_file_id = _stored_proposal_file_id(proposal, stored_attr)
        if stored_file_id:
            return stored_file_id
        if not live_share_lookup or not _is_nextcloud_cloud_path(cloud_path):
            return ""
        try:
            return _resolve_nextcloud_file_id(
                client,
                client.username,
                cloud_path,
                resource_cache=resource_cache,
            )
        except NextcloudNetworkError as exc:
            # Host unreachable: the remaining proposals would hit the same
            # timeout one by one. Fall back to saved links for all of them.
            logger.warning(
                "Nextcloud unreachable while resolving file id for proposal %s path %s; "
                "skipping live lookups for the rest of this render: %s",
                getattr(proposal, "pk", ""),
                cloud_path,
                exc,
            )
            live_share_lookup = False
            return ""
        except NextcloudApiError as exc:
            logger.warning(
                "Could not resolve Nextcloud file id for proposal %s path %s: %s",
                getattr(proposal, "pk", ""),
                cloud_path,
                exc,
            )
            return ""

    for proposal in proposals:
        path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
        if path:
            if viewer_has_nextcloud_link:
                # Folder link uses only canonical, verifiable sources. If the
                # viewer mountpoint is unknown we show a saved public link or
                # nothing — never a guessed owner-path URL that leads to
                # "folder not found".
                stored_workspace_file_id = _stored_proposal_file_id(
                    proposal, "proposal_workspace_file_id"
                )
                # Prefer Nextcloud's ``/f/<fileid>`` redirect URL over a
                # ``?dir=`` URL: the file-id URL follows whatever mountpoint
                # the viewer actually has, so it keeps working even when the
                # share API reports a viewer target that is shadowed by a
                # broader parent share already mounted in the viewer's tree.
                file_id_url = (
                    _build_nextcloud_file_redirect_url(client, stored_workspace_file_id)
                    if stored_workspace_file_id
                    else ""
                )
                proposal.proposal_workspace_folder_url = (
                    file_id_url
                    or resolved_cache.get(path)
                    or _stored_public(proposal)
                )
                owner_file_id = _maybe_resolve_owner_file_id(
                    proposal,
                    stored_attr="docx_file_id",
                    cloud_path=_stored_docx_link(proposal),
                )
                owner_pdf_file_id = _maybe_resolve_owner_file_id(
                    proposal,
                    stored_attr="pdf_file_id",
                    cloud_path=_stored_pdf_link(proposal),
                )
                proposal.proposal_docx_file_url = _resolve_proposal_docx_open_url(
                    proposal,
                    client=client,
                    viewer_has_nextcloud_link=True,
                    resolved_workspace_target_path=resolved_target_cache.get(path, ""),
                    owner_file_id=owner_file_id,
                )
                proposal.proposal_pdf_file_url = _resolve_proposal_pdf_open_url(
                    proposal,
                    client=client,
                    viewer_has_nextcloud_link=True,
                    resolved_workspace_target_path=resolved_target_cache.get(path, ""),
                    owner_file_id=owner_pdf_file_id,
                )
                if not resolved_cache.get(path):
                    _log_nextcloud_resolution_debug(
                        path=path,
                        share_map=share_map if "share_map" in locals() else {},
                        final_url=proposal.proposal_workspace_folder_url,
                        user=user,
                        nextcloud_user_id=(link.nextcloud_user_id if "link" in locals() and link else ""),
                        reason="viewer-fallback-to-non-editor-url",
                        force=debug_nextcloud_links,
                    )
            else:
                proposal.proposal_workspace_folder_url = (
                    resolved_cache.get(path)
                    or _stored_public(proposal)
                    or folder_cache.get(path, "")
                )
                owner_file_id = _maybe_resolve_owner_file_id(
                    proposal,
                    stored_attr="docx_file_id",
                    cloud_path=_stored_docx_link(proposal),
                )
                owner_pdf_file_id = _maybe_resolve_owner_file_id(
                    proposal,
                    stored_attr="pdf_file_id",
                    cloud_path=_stored_pdf_link(proposal),
                )
                proposal.proposal_docx_file_url = _resolve_proposal_docx_open_url(
                    proposal,
                    client=client,
                    owner_file_id=owner_file_id,
                )
                proposal.proposal_pdf_file_url = _resolve_proposal_pdf_open_url(
                    proposal,
                    client=client,
                    owner_file_id=owner_pdf_file_id,
                )
        else:
            proposal.proposal_docx_file_url = _resolve_proposal_docx_open_url(proposal, client=client)
            proposal.proposal_pdf_file_url = _resolve_proposal_pdf_open_url(proposal, client=client)


def _proposal_schedule_decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip().replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _proposal_schedule_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _proposal_schedule_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, dt_date):
        return value
    raw = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _proposal_schedule_month_end_day(year, month):
    return calendar.monthrange(year, month)[1]


def _add_proposal_schedule_months(value, months):
    months = _proposal_schedule_decimal(months)
    if not value or months is None:
        return value
    safe_months = max(months, Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(((safe_months - whole_months) * Decimal("30")) + Decimal("0.5"))
    month_index = (value.month - 1) + whole_months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _proposal_schedule_month_end_day(year, month))
    return dt_date(year, month, day) + timedelta(days=fractional_days)


def _subtract_proposal_schedule_months(value, months):
    months = _proposal_schedule_decimal(months)
    if not value or months is None:
        return value
    safe_months = max(months, Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(((safe_months - whole_months) * Decimal("30")) + Decimal("0.5"))
    base = value - timedelta(days=fractional_days)
    month_index = (base.month - 1) - whole_months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, _proposal_schedule_month_end_day(year, month))
    return dt_date(year, month, day)


def _add_proposal_schedule_weeks(value, weeks):
    weeks = _proposal_schedule_decimal(weeks)
    if not value or weeks is None:
        return value
    safe_weeks = max(weeks, Decimal("0"))
    return value + timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _subtract_proposal_schedule_weeks(value, weeks):
    weeks = _proposal_schedule_decimal(weeks)
    if not value or weeks is None:
        return value
    safe_weeks = max(weeks, Decimal("0"))
    return value - timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _proposal_schedule_preliminary_term_unit(value):
    raw = str(value or "").strip()
    if raw in {"months", "days", "weeks"}:
        return raw
    return "months"


def _proposal_schedule_final_term_unit(value):
    raw = str(value or "").strip()
    if raw in {"days", "weeks", "months"}:
        return raw
    return "weeks"


def _add_proposal_schedule_days(value, days):
    days = _proposal_schedule_decimal(days)
    if not value or days is None:
        return value
    return value + timedelta(days=int(max(days, Decimal("0")) + Decimal("0.5")))


def _subtract_proposal_schedule_days(value, days):
    days = _proposal_schedule_decimal(days)
    if not value or days is None:
        return value
    return value - timedelta(days=int(max(days, Decimal("0")) + Decimal("0.5")))


def _add_proposal_schedule_term(value, amount, unit):
    if unit == "days":
        return _add_proposal_schedule_days(value, amount)
    if unit == "weeks":
        return _add_proposal_schedule_weeks(value, amount)
    return _add_proposal_schedule_months(value, amount)


def _subtract_proposal_schedule_term(value, amount, unit):
    if unit == "days":
        return _subtract_proposal_schedule_days(value, amount)
    if unit == "weeks":
        return _subtract_proposal_schedule_weeks(value, amount)
    return _subtract_proposal_schedule_months(value, amount)


def _format_proposal_schedule_term(value, unit):
    amount = _proposal_schedule_decimal(value)
    if amount is None:
        return ""
    if unit == "days":
        display = str(int(max(amount, Decimal("0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    else:
        rounded = amount.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        display = f"{rounded:.1f}".replace(".", ",").rstrip("0").rstrip(",")
    labels = {"days": "дн.", "weeks": "нед.", "months": "мес."}
    return f"{display} {labels.get(unit, 'мес.')}"


def _proposal_stage_flag(payload, key, default):
    from projects_app.stage_terms import enabled_flag

    if not isinstance(payload, dict) or key not in payload:
        return default
    return enabled_flag(payload.get(key), default)


def _proposal_schedule_term_unit(value, default):
    raw = str(value or "").strip()
    if raw in {"days", "weeks", "months"}:
        return raw
    return default


def _proposal_stage_delay_days(payload):
    from projects_app.stage_terms import term_to_days

    if not isinstance(payload, dict):
        return 0
    unit = _proposal_schedule_term_unit(payload.get("next_stage_delay_unit"), "days")
    days = term_to_days(payload.get("next_stage_delay_days") or 0, unit)
    return int(days.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _proposal_schedule_base_start_date(today=None):
    current = (today or timezone.localdate()) + timedelta(days=14)
    previous_monday = current - timedelta(days=current.weekday())
    next_monday = previous_monday + timedelta(days=7)
    if abs((current - previous_monday).days) <= abs((next_monday - current).days):
        return previous_monday
    return next_monday


def _proposal_stage_payloads(proposal):
    return [
        payload
        for payload in (getattr(proposal, "stage_payloads_json", None) or [])
        if isinstance(payload, dict)
    ]


def _proposal_stage_value(payload, key, proposal, attr):
    value = payload.get(key) if isinstance(payload, dict) else None
    if value not in (None, ""):
        return value
    return getattr(proposal, attr, None)


def _proposal_stage_payload_for_product(stage_payloads, product, index):
    product_id = str(getattr(product, "pk", "") or "")
    if 0 <= index < len(stage_payloads):
        indexed_payload = stage_payloads[index]
        if not product_id or str(indexed_payload.get("product_id") or "") == product_id:
            return indexed_payload
    if product_id:
        for payload in stage_payloads:
            if str(payload.get("product_id") or "") == product_id:
                return payload
    if index < len(stage_payloads):
        return stage_payloads[index]
    return {}


def _build_proposal_payment_schedule_rows(proposals):
    rows = []
    for proposal in proposals:
        products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
        if not products and getattr(proposal, "type_id", None):
            products = [proposal.type]
        stage_payloads = _proposal_stage_payloads(proposal)
        if not products and stage_payloads:
            products = [None for _ in stage_payloads]

        rolling_start_date = _proposal_schedule_base_start_date()
        product_count = len(products)
        for index, product in enumerate(products, start=1):
            payload = _proposal_stage_payload_for_product(stage_payloads, product, index - 1)
            source_enabled = _proposal_stage_flag(payload, "source_data_term_enabled", False)
            source_date_enabled = _proposal_stage_flag(payload, "source_data_date_enabled", False)
            preliminary_term_enabled = _proposal_stage_flag(payload, "service_term_months_enabled", True)
            preliminary_date_enabled = _proposal_stage_flag(payload, "preliminary_report_date_enabled", True)
            final_date_enabled = _proposal_stage_flag(payload, "final_report_date_enabled", True)
            source_term = (
                _proposal_schedule_decimal(payload.get("source_data_term") if isinstance(payload, dict) else None)
                if source_enabled
                else None
            )
            source_unit = _proposal_schedule_term_unit(
                payload.get("source_data_term_unit") if isinstance(payload, dict) else None,
                "weeks",
            )
            source_date = (
                _proposal_schedule_date(payload.get("source_data_date") if isinstance(payload, dict) else None)
                if source_enabled and source_date_enabled
                else None
            )
            service_term_months = (
                _proposal_schedule_decimal(
                    _proposal_stage_value(payload, "service_term_months", proposal, "service_term_months")
                )
                if preliminary_term_enabled
                else None
            )
            preliminary_report_term_unit = _proposal_schedule_preliminary_term_unit(
                _proposal_stage_value(payload, "preliminary_report_term_unit", proposal, "preliminary_report_term_unit")
            )
            final_report_term_weeks = _proposal_schedule_decimal(
                _proposal_stage_value(payload, "final_report_term_weeks", proposal, "final_report_term_weeks")
            )
            final_report_term_unit = _proposal_schedule_final_term_unit(
                _proposal_stage_value(payload, "final_report_term_unit", proposal, "final_report_term_unit")
            )
            preliminary_report_date = (
                _proposal_schedule_date(
                    _proposal_stage_value(payload, "preliminary_report_date", proposal, "preliminary_report_date")
                )
                if preliminary_date_enabled
                else None
            )
            final_report_date = (
                _proposal_schedule_date(
                    _proposal_stage_value(payload, "final_report_date", proposal, "final_report_date")
                )
                if final_date_enabled
                else None
            )
            next_stage_delay_days = _proposal_stage_delay_days(payload)

            if source_date and source_term is not None:
                start_date = _subtract_proposal_schedule_term(source_date, source_term, source_unit)
            elif preliminary_report_date and service_term_months is not None:
                start_date = _subtract_proposal_schedule_term(
                    preliminary_report_date,
                    service_term_months,
                    preliminary_report_term_unit,
                )
                if source_term is not None:
                    start_date = _subtract_proposal_schedule_term(start_date, source_term, source_unit)
            else:
                start_date = rolling_start_date
            chain_date = start_date
            if source_term is not None:
                if not source_date:
                    source_date = _add_proposal_schedule_term(chain_date, source_term, source_unit)
                if source_date:
                    chain_date = source_date
            if not preliminary_report_date and service_term_months is not None:
                preliminary_report_date = _add_proposal_schedule_term(
                    chain_date,
                    service_term_months,
                    preliminary_report_term_unit,
                )
            if not final_report_date and preliminary_report_date and final_report_term_weeks is not None:
                final_report_date = _add_proposal_schedule_term(
                    preliminary_report_date,
                    final_report_term_weeks,
                    final_report_term_unit,
                )
            stage_end_date = final_report_date or preliminary_report_date or source_date or start_date
            rolling_start_date = (
                stage_end_date + timedelta(days=next_stage_delay_days)
                if stage_end_date
                else stage_end_date
            )

            rows.append(
                {
                    "proposal_id": proposal.pk,
                    "kind": proposal.kind,
                    "kind_label": proposal.get_kind_display(),
                    "status": proposal.status,
                    "status_label": proposal.get_status_display(),
                    "is_first_for_proposal": index == 1,
                    "is_continuation": index > 1,
                    "has_next_for_proposal": index < product_count,
                    "number": proposal.formatted_number,
                    "sub_number": proposal.sub_number,
                    "group": proposal.group_display,
                    "tkp_id": proposal.short_uid,
                    "type": (getattr(product, "short_name", "") or str(product or "")).strip(),
                    "name": proposal.name,
                    "version": proposal.version_display,
                    "version_group": getattr(proposal, "version_group", "") or "",
                    "is_version_head": bool(getattr(proposal, "is_version_head", False)),
                    "is_version_continuation": bool(getattr(proposal, "is_version_continuation", False)),
                    "has_version_history": bool(getattr(proposal, "has_version_history", False)),
                    "stage": f"Этап {index}",
                    "evaluation_date": (
                        _proposal_schedule_date(
                            _proposal_stage_value(payload, "evaluation_date", proposal, "evaluation_date")
                        )
                        if _proposal_stage_flag(payload, "evaluation_date_enabled", True)
                        else None
                    ),
                    "start_date": start_date,
                    "service_term_months": service_term_months,
                    "preliminary_term_display": _format_proposal_schedule_term(
                        service_term_months,
                        preliminary_report_term_unit,
                    ),
                    "preliminary_report_date": preliminary_report_date,
                    "final_report_term_weeks": final_report_term_weeks,
                    "final_term_display": _format_proposal_schedule_term(
                        final_report_term_weeks,
                        final_report_term_unit,
                    ),
                    "final_report_date": final_report_date,
                    "next_stage_delay_days": next_stage_delay_days,
                    "advance_percent": _proposal_schedule_decimal(
                        _proposal_stage_value(payload, "advance_percent", proposal, "advance_percent")
                    ),
                    "advance_term_days": _proposal_schedule_int(
                        _proposal_stage_value(payload, "advance_term_days", proposal, "advance_term_days")
                    ),
                    "preliminary_report_percent": _proposal_schedule_decimal(
                        _proposal_stage_value(
                            payload,
                            "preliminary_report_percent",
                            proposal,
                            "preliminary_report_percent",
                        )
                    ),
                    "preliminary_report_term_days": _proposal_schedule_int(
                        _proposal_stage_value(
                            payload,
                            "preliminary_report_term_days",
                            proposal,
                            "preliminary_report_term_days",
                        )
                    ),
                    "final_report_percent": _proposal_schedule_decimal(
                        _proposal_stage_value(payload, "final_report_percent", proposal, "final_report_percent")
                    ),
                    "final_report_term_days": _proposal_schedule_int(
                        _proposal_stage_value(payload, "final_report_term_days", proposal, "final_report_term_days")
                    ),
                }
            )
    return rows


def _annotate_preliminary_sent_status_markers(proposals):
    """Отправленное предварительное ТКП помечается как завершённое по цвету, если у того же ТКП ID есть итоговое."""
    grouped = {}
    for proposal in proposals:
        grouped.setdefault(_proposal_version_group_key(proposal), []).append(proposal)
    final = ProposalRegistration.ProposalDocumentKind.FINAL
    preliminary = ProposalRegistration.ProposalDocumentKind.PRELIMINARY
    sent = ProposalRegistration.ProposalStatus.SENT
    for members in grouped.values():
        has_final = any(member.document_kind == final for member in members)
        for member in members:
            member.sent_status_marker_done = bool(
                has_final
                and member.document_kind == preliminary
                and member.status == sent
            )
    return proposals


def _proposal_version_group_key(proposal):
    uid = str(getattr(proposal, "short_uid", "") or "").strip()
    if uid:
        return uid
    return f"id:{proposal.pk}"


def _order_proposals_for_display(proposals):
    items = list(proposals)
    groups = {}
    for item in items:
        groups.setdefault(_proposal_version_group_key(item), []).append(item)

    def anchor(members):
        first = min(members, key=lambda proposal: (int(proposal.version or 1), proposal.pk or 0))
        return (int(first.position or 0), first.pk or 0)

    ordered = []
    for key in sorted(groups, key=lambda group_key: anchor(groups[group_key])):
        members = sorted(
            groups[key],
            key=lambda proposal: (-int(proposal.version or 1), -(proposal.pk or 0)),
        )
        for index, proposal in enumerate(members):
            proposal.is_version_head = index == 0
            proposal.is_version_continuation = index > 0
            proposal.has_version_history = len(members) > 1
            proposal.version_group = key
        ordered.extend(members)
    return ordered


def _normalize_proposal_version_order(ordered_ids, by_id):
    grouped = {}
    group_order = []
    for proposal_id in ordered_ids:
        item = by_id[proposal_id]
        key = _proposal_version_group_key(item)
        if key not in grouped:
            grouped[key] = []
            group_order.append(key)
        grouped[key].append(item)
    normalized = []
    for key in group_order:
        members = sorted(
            grouped[key],
            key=lambda proposal: (-int(proposal.version or 1), -(proposal.pk or 0)),
        )
        normalized.extend(member.pk for member in members)
    return normalized


def _display_proposal_groups(items):
    groups = []
    for proposal in _order_proposals_for_display(items):
        key = proposal.version_group
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(proposal.pk)
    return groups


def _scoped_proposal_display_ids(items, years):
    """Порядок, который видит таблица: тот же годовой охват, что у реестра, включая версии одного ТКП ID."""
    groups = _display_proposal_groups(items)
    full_ids = [proposal_id for _, member_ids in groups for proposal_id in member_ids]
    if not years:
        return groups, full_ids
    scoped_pks = set(
        _apply_proposal_year_scope(
            ProposalRegistration.objects.filter(pk__in=full_ids),
            years,
        ).values_list("pk", flat=True)
    )
    return groups, [proposal_id for proposal_id in full_ids if proposal_id in scoped_pks]


def _merge_scoped_proposal_order(full_groups, ordered_scoped_ids, by_id):
    """Перестановка видимых строк встаёт в их места, скрытые строки и версии одного ТКП ID остаются целыми."""
    scoped_groups = []
    seen = set()
    for proposal_id in ordered_scoped_ids:
        key = _proposal_version_group_key(by_id[proposal_id])
        if key not in seen:
            seen.add(key)
            scoped_groups.append([])
        scoped_groups[-1].append(proposal_id)
    pending = iter(scoped_groups)
    merged = []
    for key, member_ids in full_groups:
        if key in seen:
            merged.extend(next(pending))
        else:
            merged.extend(member_ids)
    return merged


def _persist_proposal_positions(ordered_ids):
    for index, proposal_id in enumerate(ordered_ids, start=1):
        ProposalRegistration.objects.filter(pk=proposal_id).update(position=index)


def _move_proposal_group(pk, direction):
    items = list(ProposalRegistration.objects.select_related("group_member").order_by("position", "id"))
    display = _order_proposals_for_display(items)
    groups = []
    index_by_pk = {}
    for proposal in display:
        key = proposal.version_group
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(proposal.pk)
        index_by_pk[proposal.pk] = len(groups) - 1
    index = index_by_pk.get(pk)
    if index is None:
        return
    swap_with = index - 1 if direction == "up" else index + 1
    if swap_with < 0 or swap_with >= len(groups):
        return
    groups[index], groups[swap_with] = groups[swap_with], groups[index]
    _persist_proposal_positions(proposal_id for _, proposal_ids in groups for proposal_id in proposal_ids)


def _proposal_identity_key(proposal):
    return (
        str(proposal.sub_number if proposal.sub_number is not None else ""),
        str(getattr(proposal, "group_display", "") or ""),
        str(getattr(proposal, "short_uid", "") or ""),
        str(getattr(proposal, "type_short_display", "") or ""),
        str(getattr(proposal, "name", "") or ""),
    )


def _payment_identity_key(row):
    sub_number = row.get("sub_number")
    return (
        str(sub_number if sub_number is not None else ""),
        str(row.get("group") or ""),
        str(row.get("tkp_id") or ""),
        str(row.get("type") or ""),
        str(row.get("name") or ""),
    )


def _annotate_identity_groups(items, key_fn):
    items = list(items)
    start = 0
    while start < len(items):
        key = key_fn(items[start])
        end = start + 1
        while end < len(items) and key_fn(items[end]) == key:
            end += 1
        group_size = end - start
        for offset, item in enumerate(items[start:end]):
            values = {
                "show_identity_fields": offset == 0,
                "identity_has_next": offset < group_size - 1,
                "is_identity_continuation": offset > 0,
            }
            if isinstance(item, dict):
                item.update(values)
            else:
                for name, value in values.items():
                    setattr(item, name, value)
        start = end
    return items


def _annotate_payment_number_groups(rows):
    items = list(rows)
    start = 0
    while start < len(items):
        current_number = items[start].get("number")
        end = start + 1
        while end < len(items) and items[end].get("number") == current_number:
            end += 1
        group_size = end - start
        for offset, row in enumerate(items[start:end]):
            row["is_first_for_number"] = offset == 0
            row["is_number_continuation"] = offset > 0
            row["has_next_for_number"] = offset < group_size - 1
        start = end
    return _annotate_payment_request_version_toggles(items)


def _annotate_payment_request_version_toggles(rows):
    items = list(rows)
    start = 0
    while start < len(items):
        number = items[start].get("number")
        end = start + 1
        while end < len(items) and items[end].get("number") == number:
            end += 1
        group = items[start:end]

        def tkp_id(row):
            return str(row.get("version_group") or row.get("tkp_id") or "")

        combine, toggle_ids = _request_version_toggle_state(
            group,
            tkp_id,
            has_own_toggle=lambda row: bool(
                row.get("is_first_for_proposal")
                and row.get("is_version_head")
                and row.get("has_version_history")
            ),
        )
        controlled = " ".join(toggle_ids) if combine else ""
        for index, row in enumerate(group):
            own_toggle = bool(
                row.get("is_first_for_proposal")
                and row.get("is_version_head")
                and row.get("has_version_history")
            )
            if combine and index == 0:
                row["show_version_toggle"] = True
                row["version_toggle_group"] = toggle_ids[0]
                row["version_toggle_controlled_ids"] = controlled
                row["version_toggle_suppressed"] = False
                row["version_toggle_master_only"] = not own_toggle
            elif combine and own_toggle:
                row["show_version_toggle"] = True
                row["version_toggle_group"] = tkp_id(row)
                row["version_toggle_controlled_ids"] = ""
                row["version_toggle_suppressed"] = True
                row["version_toggle_master_only"] = False
            else:
                row["show_version_toggle"] = own_toggle
                row["version_toggle_group"] = tkp_id(row) if own_toggle else ""
                row["version_toggle_controlled_ids"] = ""
                row["version_toggle_suppressed"] = False
                row["version_toggle_master_only"] = False
        start = end
    return items


def _payment_row_class(row):
    classes = []
    if row.get("has_next_for_proposal"):
        classes.append("proposal-payment-stage-has-next")
    if row.get("is_continuation"):
        classes.append("proposal-payment-stage-continuation")
    if row.get("has_next_for_number"):
        classes.append("proposal-payment-number-has-next")
    if row.get("is_number_continuation"):
        classes.append("proposal-payment-number-continuation")
    if row.get("identity_has_next"):
        classes.append("proposal-payment-identity-has-next")
    if row.get("is_identity_continuation"):
        classes.append("proposal-payment-identity-continuation")
    return " ".join(classes)


def _annotate_proposal_number_groups(proposals):
    items = list(proposals)
    start = 0
    while start < len(items):
        current_number = items[start].number
        end = start + 1
        while end < len(items) and items[end].number == current_number:
            end += 1
        group_size = end - start
        for offset, proposal in enumerate(items[start:end], start=1):
            proposal.is_first_for_number = offset == 1
            proposal.is_number_continuation = offset > 1
            proposal.has_next_for_number = offset < group_size
        start = end
    return _annotate_request_version_toggles(items)


def _request_version_toggle_state(rows, tkp_id, *, has_own_toggle):
    seen_tkp = []
    toggle_ids = []
    for row in rows:
        tkp = tkp_id(row)
        if tkp and tkp not in seen_tkp:
            seen_tkp.append(tkp)
        if has_own_toggle(row) and tkp and tkp not in toggle_ids:
            toggle_ids.append(tkp)
    return len(seen_tkp) > 1 and bool(toggle_ids), toggle_ids


def _annotate_request_version_toggles(proposals):
    """Одна стрелка на «Запрос», если внутри него несколько разных ТКП ID."""
    items = list(proposals)
    start = 0
    while start < len(items):
        number = items[start].number
        end = start + 1
        while end < len(items) and items[end].number == number:
            end += 1
        group = items[start:end]
        combine, toggle_ids = _request_version_toggle_state(
            group,
            _proposal_version_group_key,
            has_own_toggle=lambda proposal: bool(
                proposal.is_version_head and proposal.has_version_history
            ),
        )
        controlled = " ".join(toggle_ids) if combine else ""
        for index, proposal in enumerate(group):
            own_toggle = bool(proposal.is_version_head and proposal.has_version_history)
            if combine and index == 0:
                proposal.show_version_toggle = True
                proposal.version_toggle_group = toggle_ids[0]
                proposal.version_toggle_controlled_ids = controlled
                proposal.version_toggle_suppressed = False
                proposal.version_toggle_master_only = not own_toggle
            elif combine and own_toggle:
                proposal.show_version_toggle = True
                proposal.version_toggle_group = _proposal_version_group_key(proposal)
                proposal.version_toggle_controlled_ids = ""
                proposal.version_toggle_suppressed = True
                proposal.version_toggle_master_only = False
            else:
                proposal.show_version_toggle = own_toggle
                proposal.version_toggle_group = _proposal_version_group_key(proposal) if own_toggle else ""
                proposal.version_toggle_controlled_ids = ""
                proposal.version_toggle_suppressed = False
                proposal.version_toggle_master_only = False
        start = end
    return items


PROPOSAL_YEAR_NONE = "none"


def _proposal_request_values(request, key):
    if request is None:
        return []
    values = list(request.GET.getlist(key))
    if request.method == "POST":
        values.extend(request.POST.getlist(key))
    parts = []
    for value in values:
        parts.extend(part.strip() for part in str(value).split(",") if part.strip())
    return parts


def _selected_proposal_years(request):
    years = []
    for value in _proposal_request_values(request, "proposals_year"):
        if value == "__all__":
            continue
        if value == PROPOSAL_YEAR_NONE:
            year = None
        elif value.isdigit():
            year = int(value)
        else:
            continue
        if year not in years:
            years.append(year)
    return years


def _proposal_year_query_values(years):
    return [PROPOSAL_YEAR_NONE if year is None else str(year) for year in years]


def _proposal_year_options():
    """Все годы реестра, независимо от текущего фильтра: список в шапке не должен схлопываться."""
    years = set()
    has_none = False
    for year in ProposalRegistration.objects.values_list("year", flat=True).distinct():
        if year is None:
            has_none = True
        else:
            years.add(year)
    options = [{"value": str(year), "label": str(year)} for year in sorted(years, reverse=True)]
    if has_none:
        options.append({"value": PROPOSAL_YEAR_NONE, "label": "Без года"})
    return options


def _apply_proposal_year_scope(queryset, years):
    """Год сужает выборку на сервере. Версии одного ТКП ID остаются вместе, если подошла любая."""
    if not years:
        return queryset
    numeric = [year for year in years if year is not None]
    include_none = None in years
    year_q = Q()
    if numeric:
        year_q |= Q(year__in=numeric)
    if include_none:
        year_q |= Q(year__isnull=True)
    matched = ProposalRegistration.objects.filter(year_q)
    sibling_uids = matched.exclude(short_uid="").values("short_uid")
    return queryset.filter(Q(pk__in=matched.values("pk")) | Q(short_uid__in=sibling_uids))


def _proposals_context(
    request=None,
    user=None,
    *,
    debug_nextcloud_links=False,
    strict_nextcloud=True,
):
    if request is not None and user is None:
        user = request.user
    selected_years = _selected_proposal_years(request)
    proposals = ProposalRegistration.objects.select_related(
        "group_member",
        "country",
        "asset_owner_country",
        "type",
        "currency",
    ).prefetch_related(
        "product_links__product",
        Prefetch(
            "dispatch_recipients",
            queryset=ProposalDispatchRecipient.objects.order_by("position", "id"),
        ),
    )
    proposals = _apply_proposal_year_scope(proposals, selected_years)
    proposals = _annotate_preliminary_sent_status_markers(
        _annotate_identity_groups(
            _annotate_proposal_number_groups(_order_proposals_for_display(proposals)),
            _proposal_identity_key,
        )
    )
    proposal_payment_schedule_rows = _annotate_payment_number_groups(
        _annotate_identity_groups(
            _build_proposal_payment_schedule_rows(proposals),
            _payment_identity_key,
        )
    )
    for row in proposal_payment_schedule_rows:
        row["row_class"] = _payment_row_class(row)
    try:
        _attach_proposal_folder_urls(
            proposals,
            user=user,
            request=request,
            debug_nextcloud_links=debug_nextcloud_links,
        )
    except NextcloudApiError as exc:
        if strict_nextcloud:
            raise
        logger.warning(
            "Nextcloud unavailable while rendering a completed proposal mutation; "
            "using saved folder links: %s",
            exc,
        )
    proposal_templates = list(
        ProposalTemplate.objects
        .select_related("group_member", "product")
        .prefetch_related("group_members", "products")
        .all()
    )
    proposal_variables = ProposalVariable.objects.all()
    order_map = _proposal_group_member_order_map()
    for template in proposal_templates:
        groups = list(template.group_members.all())
        if not groups and template.group_member_id:
            groups = [template.group_member]
        template.group_display = (
            ", ".join(_proposal_group_member_short(group, order_map.get(group.pk, 0)) for group in groups)
            if groups
            else "Все"
        )
        products = list(template.products.all())
        if not products and template.product_id:
            products = [template.product]
        template.products_display = (
            ", ".join(product.short_name or str(product) for product in products)
            if products
            else "Все"
        )
    has_active_smtp_connection = False
    if user:
        has_active_smtp_connection = ExternalSMTPAccount.objects.filter(
            user=user,
            is_active=True,
            use_for_notifications=True,
        ).exists()
    proposal_registry_ui_columns = get_proposal_registry_ui_columns()
    proposal_payment_schedule_ui_columns = get_proposal_payment_schedule_ui_columns()
    proposal_dispatch_ui_columns = get_proposal_dispatch_ui_columns()
    proposal_order_ids = [proposal.pk for proposal in proposals]
    return {
        "proposals": proposals,
        "proposal_payment_schedule_rows": proposal_payment_schedule_rows,
        "proposal_templates": proposal_templates,
        "proposal_variables": proposal_variables,
        "proposal_registry_ui_columns": proposal_registry_ui_columns,
        "proposal_payment_schedule_ui_columns": proposal_payment_schedule_ui_columns,
        "proposal_dispatch_ui_columns": proposal_dispatch_ui_columns,
        "proposal_order_signature": _proposal_order_signature(proposal_order_ids),
        "proposal_registry_empty_colspan": len(proposal_registry_ui_columns) + 3,
        "proposal_payment_schedule_empty_colspan": len(proposal_payment_schedule_ui_columns) + 2,
        "proposal_dispatch_empty_colspan": len(proposal_dispatch_ui_columns) + 2,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "proposal_request_sent_initial": timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
        "has_active_smtp_connection": has_active_smtp_connection,
        "allow_local_proposal_folder": local_proposal_folder_enabled(),
        "local_proposal_folder_placeholder": local_proposal_folder_placeholder(),
        "proposal_year_options": _proposal_year_options(),
        "proposal_registry_years": _proposal_year_query_values(selected_years),
    }


def _render_proposals_updated(request):
    response = render(
        request,
        PROPOSALS_PARTIAL_TEMPLATE,
        _proposals_context(
            request=request,
            debug_nextcloud_links=_proposal_link_debug_enabled(request),
            strict_nextcloud=False,
        ),
    )
    response[HX_TRIGGER_HEADER] = HX_PROPOSALS_UPDATED_EVENT
    return response


SKIP_RENDER_HEADER = "X-Skip-Render"


def _skip_render_requested(request) -> bool:
    """Client performs a batch mutation and will fetch the final markup itself.

    The panel JS sends ``X-Skip-Render: 1`` on every request of a batch except
    the last one, so intermediate deletions do not pay for a full registry
    render (and its Nextcloud link resolution) whose result is discarded.
    """
    return str(request.headers.get(SKIP_RENDER_HEADER, "") or "").strip() == "1"


def _render_proposals_updated_or_empty(request):
    if _skip_render_requested(request):
        return HttpResponse(status=204)
    return _render_proposals_updated(request)


def _render_proposal_variables_updated(request, *, close_modal=False):
    # The variables section depends only on ``proposal_variables``: skip the
    # registry query and Nextcloud link resolution of the full pane context.
    if _skip_render_requested(request):
        return HttpResponse(status=204)
    response = render(
        request,
        PROPOSAL_VARIABLES_SECTION_TEMPLATE,
        {"proposal_variables": ProposalVariable.objects.all()},
    )
    if close_modal:
        response[HX_TRIGGER_HEADER] = HX_PROPOSALS_UPDATED_EVENT
    return response


def _maybe_create_nextcloud_proposal_workspace(request, proposal) -> None:
    if not is_nextcloud_primary():
        return
    try:
        workspace_result = create_proposal_workspace(
            request.user,
            proposal,
            return_share_target=True,
        )
    except NextcloudApiError:
        # The registry row should still be saved even if the cloud sync fails.
        return
    if isinstance(workspace_result, tuple):
        workspace_path, share_target_path = workspace_result
    else:
        workspace_path, share_target_path = workspace_result, ""
    normalized_root_path = _get_normalized_nextcloud_root_path()
    normalized_target_path = _normalize_viewer_target_path(
        share_target_path,
        root_path=normalized_root_path,
    )
    workspace_file_id = _resolve_workspace_folder_file_id(workspace_path)
    proposal.proposal_workspace_disk_path = workspace_path
    # Persist the viewer-side mountpoint returned by Nextcloud so the icon link
    # stays valid after the session cache expires or another user opens the table.
    proposal.proposal_workspace_target_path = normalized_target_path
    # For Nextcloud we want the table icon to resolve to a user share with editor
    # permissions, not to a public readonly link.
    proposal.proposal_workspace_public_url = ""
    # Capture the folder id so the table can fall back to Nextcloud's
    # ``/f/<id>`` redirect URL, which works for every viewer regardless of how
    # the folder is mounted into their file tree.
    proposal.proposal_workspace_file_id = workspace_file_id
    proposal.save(
        update_fields=[
            "proposal_workspace_disk_path",
            "proposal_workspace_target_path",
            "proposal_workspace_public_url",
            "proposal_workspace_file_id",
        ]
    )
    _cache_proposal_target_path(
        request,
        workspace_path,
        share_target_path,
        root_path=normalized_root_path,
    )


def _resolve_workspace_folder_file_id(workspace_path: str) -> str:
    """Resolve Nextcloud folder id for a proposal workspace path.

    Failures are swallowed so that workspace creation itself never breaks when
    the follow-up PROPFIND cannot locate the folder yet (e.g., eventual
    consistency right after share creation).
    """
    normalized_workspace_path = _normalize_nextcloud_path(workspace_path)
    if not normalized_workspace_path:
        return ""
    client = NextcloudApiClient()
    if not client.is_configured:
        return ""
    try:
        return _resolve_nextcloud_file_id(
            client,
            client.username,
            normalized_workspace_path,
        )
    except NextcloudApiError as exc:
        logger.warning(
            "Could not resolve Nextcloud workspace file id for path %s: %s",
            normalized_workspace_path,
            exc,
        )
        return ""


def _proposal_product_catalog():
    from policy_app.product_groups import catalog_group_payload, product_catalog_queryset

    products = list(product_catalog_queryset())
    catalog_meta = build_consulting_catalog_meta()
    consulting_types = []
    service_categories = []
    seen_consulting_types = set()
    seen_service_categories = set()
    for item in catalog_meta["consulting_types"]:
        label = item["label"]
        if label and label not in seen_consulting_types:
            seen_consulting_types.add(label)
            consulting_types.append(label)
    for item in catalog_meta["service_categories"]:
        label = item["label"]
        if label and label not in seen_service_categories:
            seen_service_categories.add(label)
            service_categories.append(label)
    return {
        "consulting_types": consulting_types,
        "service_categories": service_categories,
        "products": [
            {
                "id": product.pk,
                "label": " ".join(
                    part
                    for part in ((product.short_name or "").strip(), (product.display_name or "").strip())
                    if part
                ),
                "short_label": (product.short_name or "").strip(),
                "consulting_type": (product.consulting_type_display or "").strip(),
                "service_category": (product.service_category_display or "").strip(),
                "service_subtype": (product.service_subtype_display or "").strip(),
                **catalog_group_payload(product),
            }
            for product in products
        ],
    }


def _proposal_product_autofill_data(product_ids=None, group_member=None):
    def _section_specialty_names(section):
        names = []
        seen = set()
        for link in section.ranked_specialties.all():
            specialty_name = str(getattr(getattr(link, "specialty", None), "specialty", "") or "").strip()
            if specialty_name and specialty_name not in seen:
                seen.add(specialty_name)
                names.append(specialty_name)
        return names

    def _employee_short_name(employee):
        if not employee:
            return ""
        user = getattr(employee, "user", None)
        parts = [
            (getattr(user, "first_name", "") or "").strip(),
            (getattr(user, "last_name", "") or "").strip(),
        ]
        return " ".join(part for part in parts if part)

    def _grade_sort_key(profile):
        grade = getattr(profile, "grade", None)
        return (
            int(getattr(grade, "qualification", 0) or 0),
            int(getattr(grade, "qualification_levels", 0) or 0),
        )

    def _system_dsc_section_entry(product_id, section_tariff_map):
        dsc_name = SYSTEM_DSC_SECTION_DEFAULTS["name_ru"]
        section_tariff_days = int(
            (section_tariff_map.get(product_id, {}).get(SYSTEM_DSC_SECTION_CODE))
            or (section_tariff_map.get(product_id, {}).get(dsc_name))
            or 0
        )
        return {
            "name": dsc_name,
            "code": SYSTEM_DSC_SECTION_CODE,
            "select_key": SYSTEM_DSC_SECTION_CODE,
            "display_name": f"{SYSTEM_DSC_SECTION_CODE} - {dsc_name}",
            "is_system": True,
            "is_system_dsc": True,
            "accounting_type": SYSTEM_DSC_SECTION_DEFAULTS["accounting_type"],
            "executor": "",
            "exclude_from_tkp_autofill": bool(SYSTEM_DSC_SECTION_DEFAULTS["exclude_from_tkp_autofill"]),
            "default_specialist": "",
            "default_professional_status": "",
            "default_base_rate_share": 0,
            "specialty_tariff_rate_eur": "",
            "service_days_tkp": section_tariff_days,
            "specialty_is_director": True,
            "specialist_options": [],
        }

    def _section_select_key(section_name, section_code):
        code = (section_code or "").strip()
        return code or (section_name or "").strip()

    def _section_display_name(section_name, section_code):
        name = (section_name or "").strip()
        code = (section_code or "").strip()
        return f"{code} {name}" if code and name else name

    product_filter = None
    if product_ids is not None:
        product_filter = {
            int(product_id)
            for product_id in product_ids
            if str(product_id or "").strip().isdigit() and int(product_id) > 0
        }

    specialty_candidates = {}
    specialty_defaults = {}
    expert_profiles = (
        ExpertProfile.objects
        .filter(employee__user__is_staff=True)
        .select_related("employee__user", "grade")
        .prefetch_related(
            Prefetch(
                "ranked_specialties",
                queryset=(
                    ExpertProfileSpecialty.objects
                    .select_related("specialty")
                    .order_by("rank", "id")
                ),
            )
        )
    )
    for profile in expert_profiles:
        specialist_name = _employee_short_name(profile.employee)
        if not specialist_name:
            continue
        candidate_status = str(profile.professional_status_short or "").strip()
        for link in profile.ranked_specialties.all():
            specialty_name = str(getattr(link.specialty, "specialty", "") or "").strip()
            if not specialty_name:
                continue
            specialty_candidates.setdefault(specialty_name, []).append(
                {
                    "name": specialist_name,
                    "professional_status": candidate_status,
                    "base_rate_share": int(getattr(getattr(profile, "grade", None), "base_rate_share", 0) or 0),
                    "rank": int(link.rank or 0),
                    "grade_sort_key": _grade_sort_key(profile),
                }
            )

    for specialty_name, candidates in specialty_candidates.items():
        if not candidates:
            continue
        min_rank = min(candidate["rank"] for candidate in candidates)
        best_grade_key = max(
            (
                candidate["grade_sort_key"]
                for candidate in candidates
                if candidate["rank"] == min_rank
            ),
            default=(0, 0),
        )
        specialty_defaults[specialty_name] = next(
            (
                {
                    "name": candidate["name"],
                    "professional_status": candidate["professional_status"],
                    "base_rate_share": int(candidate.get("base_rate_share", 0) or 0),
                }
                for candidate in candidates
                if candidate["rank"] == min_rank and candidate["grade_sort_key"] == best_grade_key
            ),
            {"name": "", "professional_status": "", "base_rate_share": 0},
        )
        seen_names = set()
        ordered_candidates = []
        for candidate in sorted(
            candidates,
            key=lambda item: (
                item["rank"],
                -item["grade_sort_key"][0],
                -item["grade_sort_key"][1],
                item["name"],
            ),
        ):
            if candidate["name"] in seen_names:
                continue
            seen_names.add(candidate["name"])
            ordered_candidates.append(
                {
                    "name": candidate["name"],
                    "professional_status": candidate["professional_status"],
                    "base_rate_share": int(candidate.get("base_rate_share", 0) or 0),
                }
            )
        specialty_candidates[specialty_name] = ordered_candidates

    products_qs = Product.objects.order_by("position", "id")
    if product_filter is not None:
        products_qs = products_qs.filter(pk__in=product_filter)
    product_ids = [str(product_id) for product_id in products_qs.values_list("id", flat=True)]

    sections_qs = (
        TypicalSection.objects
        .select_related(
            "product",
            "service_block",
            "service_block__expertise_dir",
            "service_block__expertise_direction",
        )
        .prefetch_related(
            Prefetch(
                "service_block__ranked_specialties",
                queryset=(
                    ServiceBlockClassifierSpecialty.objects
                    .select_related("specialty")
                    .order_by("rank", "id")
                ),
            )
        )
        .order_by("product_id", "position", "id")
    )
    service_goal_reports_qs = ServiceGoalReport.objects.select_related("product").order_by("product_id", "position", "id")
    typical_service_compositions_qs = (
        TypicalServiceComposition.objects.select_related("product", "section").order_by("product_id", "position", "id")
    )
    typical_service_terms_qs = TypicalServiceTerm.objects.select_related("product").order_by("product_id", "position", "id")
    if product_filter is not None:
        sections_qs = sections_qs.filter(product_id__in=product_filter)
        service_goal_reports_qs = service_goal_reports_qs.filter(product_id__in=product_filter)
        typical_service_compositions_qs = typical_service_compositions_qs.filter(product_id__in=product_filter)
        typical_service_terms_qs = typical_service_terms_qs.filter(product_id__in=product_filter)
    sections = list(sections_qs)
    service_goal_reports = list(service_goal_reports_qs)
    typical_service_compositions = list(typical_service_compositions_qs)
    typical_service_terms = list(typical_service_terms_qs)
    specialty_tariffs = list(
        SpecialtyTariff.objects
        .prefetch_related("specialties")
        .order_by("position", "id")
    )
    section_tariffs_qs = (
        Tariff.objects
        .select_related("product", "section")
        .order_by("product_id", "position", "id")
    )
    if product_filter is not None:
        section_tariffs_qs = section_tariffs_qs.filter(product_id__in=product_filter)
    section_tariffs = list(section_tariffs_qs)
    from group_app.expertise_management import ExpertiseAssignmentIndex

    assignment_index = ExpertiseAssignmentIndex(
        section.expertise_dir_id for section in sections if section.expertise_dir_id
    )
    direction_heads = {}
    for section in sections:
        if not section.expertise_dir_id:
            continue
        head = assignment_index.operation_head(section.expertise_dir_id, group_member)
        if head is not None:
            direction_heads[section.pk] = head
    head_profiles = {}
    head_employee_ids = [employee.pk for employee in direction_heads.values()]
    if head_employee_ids:
        for profile in (
            ExpertProfile.objects
            .select_related("employee__user")
            .filter(employee_id__in=head_employee_ids)
        ):
            head_profiles[profile.employee_id] = profile

    sections_map = {}
    specialty_tariff_map = {}
    for tariff in specialty_tariffs:
        if tariff.daily_rate_tkp_eur in (None, ""):
            continue
        for specialty in tariff.specialties.all():
            specialty_name = str(getattr(specialty, "specialty", "") or "").strip()
            if specialty_name and specialty_name not in specialty_tariff_map:
                specialty_tariff_map[specialty_name] = str(tariff.daily_rate_tkp_eur)
    section_tariff_map = {}
    for tariff in section_tariffs:
        product_id = str(tariff.product_id or "")
        if not product_id:
            continue
        bucket = section_tariff_map.setdefault(product_id, {})
        section_code = (getattr(tariff.section, "code", "") or "").strip()
        section_name = (getattr(tariff.section, "name_ru", "") or "").strip()
        if section_code and section_code not in bucket:
            bucket[section_code] = int(tariff.service_days_tkp or 0)
        if section_name and section_name not in bucket:
            bucket[section_name] = int(tariff.service_days_tkp or 0)
    for product_id in product_ids:
        sections_map[product_id] = [_system_dsc_section_entry(product_id, section_tariff_map)]
    for section in sections:
        product_id = str(section.product_id or "")
        if not product_id or not section.name_ru:
            continue
        if section.is_system_dsc or (section.code or "").strip().upper() == SYSTEM_DSC_SECTION_CODE:
            continue
        bucket = sections_map.setdefault(product_id, [])
        section_code = (section.code or "").strip()
        section_seen = any(
            ((item.get("code") or "").strip() == section_code)
            if section_code
            else item.get("name") == section.name_ru
            for item in bucket
        )
        if not section_seen:
            section_specialty_names = _section_specialty_names(section)
            specialty_name = section_specialty_names[0] if section_specialty_names else ""
            executor_display = "\n".join(section_specialty_names)
            specialist_options = list(specialty_candidates.get(specialty_name, []))
            default_candidate = specialty_defaults.get(
                specialty_name, {"name": "", "professional_status": "", "base_rate_share": 0}
            )
            default_specialist = default_candidate["name"]
            default_professional_status = default_candidate["professional_status"]
            default_base_rate_share = int(default_candidate.get("base_rate_share", 0) or 0)
            if section.expertise_dir_id:
                head = direction_heads.get(section.pk)
                head_profile = head_profiles.get(getattr(head, "pk", None))
                head_name = _employee_short_name(head)
                if head_name:
                    default_specialist = head_name
                    default_professional_status = str(
                        getattr(head_profile, "professional_status_short", "") or ""
                    ).strip()
                    default_base_rate_share = int(
                        getattr(getattr(head_profile, "grade", None), "base_rate_share", 0) or 0
                    )
                    if not any(option.get("name") == head_name for option in specialist_options):
                        specialist_options = [
                            {
                                "name": head_name,
                                "professional_status": default_professional_status,
                                "base_rate_share": default_base_rate_share,
                            },
                            *specialist_options,
                        ]
            specialty_policy_dir = getattr(section, "expertise_dir", None)
            specialty_is_director = (
                not specialty_policy_dir
                or (getattr(specialty_policy_dir, "short_name", "") or "").strip() == "—"
            )
            section_tariff_days = int(
                (section_tariff_map.get(product_id, {}).get((section.code or "").strip()))
                or (section_tariff_map.get(product_id, {}).get((section.name_ru or "").strip()))
                or 0
            )
            bucket.append(
                {
                    "name": section.name_ru,
                    "code": section.code or "",
                    "select_key": _section_select_key(section.name_ru, section.code),
                    "display_name": _section_display_name(section.name_ru, section.code),
                    "is_system": bool(section.is_system),
                    "is_system_dsc": bool(section.is_system_dsc),
                    "accounting_type": str(getattr(section, "accounting_type", "") or "").strip(),
                    "executor": executor_display,
                    "exclude_from_tkp_autofill": bool(section.exclude_from_tkp_autofill),
                    "default_specialist": default_specialist,
                    "default_professional_status": default_professional_status,
                    "default_base_rate_share": default_base_rate_share,
                    "specialty_tariff_rate_eur": specialty_tariff_map.get(specialty_name, ""),
                    "service_days_tkp": section_tariff_days,
                    "specialty_is_director": specialty_is_director,
                    "specialist_options": specialist_options,
                }
            )
    service_goal_reports_map = {}
    for item in service_goal_reports:
        product_id = str(item.product_id or "")
        if not product_id or product_id in service_goal_reports_map:
            continue
        service_goal_reports_map[product_id] = {
            "report_title": item.report_title or "",
            "service_goal": item.service_goal or "",
            "service_goal_genitive": item.service_goal_genitive or "",
        }
    typical_service_compositions_map = {}
    for item in typical_service_compositions:
        product_id = str(item.product_id or "")
        if not product_id:
            continue
        bucket = typical_service_compositions_map.setdefault(product_id, [])
        bucket.append(
            {
                "code": (getattr(item.section, "code", "") or "").strip(),
                "service_name": (getattr(item.section, "name_ru", "") or "").strip(),
                "service_composition": item.service_composition or "",
                "service_composition_editor_state": item.service_composition_editor_state or {},
            }
        )
    typical_service_terms_map = {}
    for item in typical_service_terms:
        product_id = str(item.product_id or "")
        if not product_id or product_id in typical_service_terms_map:
            continue
        typical_service_terms_map[product_id] = {
            "source_data_term": format(item.source_data_weeks, ".1f"),
            "source_data_term_unit": item.source_data_term_unit,
            "preliminary_report_months": format(item.preliminary_report_months, ".1f"),
            "preliminary_report_term_unit": item.preliminary_report_term_unit,
            "final_report_weeks": format(item.final_report_weeks, ".1f"),
            "final_report_term_unit": item.final_report_term_unit,
        }
    return {
        "typical_sections_json": sections_map,
        "service_goal_reports_json": service_goal_reports_map,
        "typical_service_compositions_json": typical_service_compositions_map,
        "typical_service_terms_json": typical_service_terms_map,
    }


def _proposal_form_with_message(proposal, message, user=None):
    form = ProposalRegistrationForm(instance=proposal, user=user)
    form.cleaned_data = {}
    form.add_error(None, message)
    return form


def _save_locked_proposal_status(request, proposal):
    status = str(request.POST.get("status") or "")
    allowed = allowed_manual_proposal_statuses(request.user, proposal.status)
    if status not in allowed:
        form = ProposalRegistrationForm(instance=proposal, user=request.user)
        form.cleaned_data = {}
        form.add_error("status", "Выберите корректное значение.")
        return _render_proposal_form(request, form=form, action="edit", proposal=proposal)
    if status != proposal.status:
        proposal.status = status
        proposal.save(update_fields=["status"])
    return _render_proposals_updated(request)


def _render_proposal_form(request, *, form, action, proposal=None):
    customer_identifier_record_id, customer_identifier_selected = _autocomplete_link_state(
        form,
        "customer_autocomplete",
        getattr(proposal, "customer_identifier_record_id", None),
    )
    owner_stored_id = getattr(proposal, "asset_owner_identifier_record_id", None)
    if proposal is not None and proposal.asset_owner_matches_customer:
        owner_stored_id = proposal.customer_identifier_record_id
    asset_owner_identifier_record_id, asset_owner_identifier_selected = _autocomplete_link_state(
        form,
        "asset_owner_autocomplete",
        owner_stored_id,
    )
    return render(
        request,
        PROPOSAL_FORM_TEMPLATE,
        {
            "form": form,
            "action": action,
            "proposal": proposal,
            "customer_identifier_record_id": customer_identifier_record_id,
            "customer_identifier_selected": customer_identifier_selected,
            "asset_owner_identifier_record_id": asset_owner_identifier_record_id,
            "asset_owner_identifier_selected": asset_owner_identifier_selected,
            "proposal_type_meta_json": json.dumps(_proposal_product_catalog(), ensure_ascii=False),
            **_proposal_product_autofill_data(
                group_member=getattr(proposal, "group_member", None),
            ),
        },
    )


def _attach_dispatch_form_file_urls(proposal, user) -> None:
    """Build DOCX/PDF open links from persisted file ids and the stored mount path.

    The dispatch form only displays those two links. Listing every Nextcloud
    share (or PROPFINDing a folder) would grow with the registry size, so this
    path never calls the share or WebDAV APIs and never writes back to the DB.
    """
    client = None
    viewer_has_nextcloud_link = False
    stored_target_path = ""
    if is_nextcloud_primary():
        configured_client = NextcloudApiClient()
        if configured_client.is_configured:
            client = configured_client
            stored_target_path = _normalize_viewer_target_path(
                str(getattr(proposal, "proposal_workspace_target_path", "") or "").strip(),
            )
            if user is not None and getattr(user, "is_authenticated", False):
                link = NextcloudUserLink.objects.filter(user=user).first()
                viewer_has_nextcloud_link = bool(
                    link
                    and link.nextcloud_user_id
                    and link.nextcloud_user_id != client.username
                )

    proposal.proposal_docx_file_url = _resolve_proposal_docx_open_url(
        proposal,
        client=client,
        viewer_has_nextcloud_link=viewer_has_nextcloud_link,
        resolved_workspace_target_path=stored_target_path,
        owner_file_id=_stored_proposal_file_id(proposal, "docx_file_id"),
    )
    proposal.proposal_pdf_file_url = _resolve_proposal_pdf_open_url(
        proposal,
        client=client,
        viewer_has_nextcloud_link=viewer_has_nextcloud_link,
        resolved_workspace_target_path=stored_target_path,
        owner_file_id=_stored_proposal_file_id(proposal, "pdf_file_id"),
    )


def _render_dispatch_form(request, *, form, proposal):
    _attach_dispatch_form_file_urls(proposal, request.user)
    recipient_identifier_record_id, recipient_identifier_selected = _autocomplete_link_state(
        form,
        "recipient_autocomplete",
        getattr(proposal, "recipient_identifier_record_id", None),
    )
    dispatch_recipients = form.display_recipients()
    ordered_recipients = [
        row
        for row in dispatch_recipients
        if getattr(row, "role", "") == ProposalDispatchRecipient.Role.TO
    ] + [
        row
        for row in dispatch_recipients
        if getattr(row, "role", "") == ProposalDispatchRecipient.Role.BCC
    ]
    for index, row in enumerate(ordered_recipients, start=1):
        row.contact_index = index
    dispatch_recipients = annotate_staff_locked_contacts(dispatch_recipients)
    return render(
        request,
        PROPOSAL_DISPATCH_FORM_TEMPLATE,
        {
            "form": form,
            "proposal": proposal,
            "docx_download_available": bool(proposal.docx_file_name),
            "recipient_identifier_record_id": recipient_identifier_record_id,
            "recipient_identifier_selected": recipient_identifier_selected,
            "dispatch_recipients": dispatch_recipients,
            "has_bcc_recipients": any(
                getattr(row, "role", "") == ProposalDispatchRecipient.Role.BCC and (getattr(row, "email", "") or "")
                for row in dispatch_recipients
            ),
            "empty_dispatch_recipient": DispatchRecipientFormRow({}),
            "recipient_countries": form.fields["recipient_country"].queryset,
            "default_recipient_country_id": form.fields["recipient_country"].initial or "",
        },
    )


def _render_proposal_template_form(request, *, form, action, template_obj=None):
    return render(
        request,
        PROPOSAL_TEMPLATE_FORM_TEMPLATE,
        {
            "form": form,
            "action": action,
            "template_obj": template_obj,
        },
    )


def _proposal_variable_form_ctx(**extra):
    ctx = {"registry_json": proposal_variable_registry_json()}
    ctx.update(extra)
    return ctx


def _render_proposal_variable_form(request, *, form, action, variable=None):
    return render(
        request,
        PROPOSAL_VARIABLE_FORM_TEMPLATE,
        _proposal_variable_form_ctx(form=form, action=action, variable=variable),
    )


def _normalize_proposal_positions():
    items = _order_proposals_for_display(ProposalRegistration.objects.all())
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ProposalRegistration.objects.filter(pk=item.pk).update(position=idx)


def _proposal_order_signature(proposal_ids):
    return ":".join(str(proposal_id) for proposal_id in proposal_ids)


def _normalize_proposal_template_positions():
    items = ProposalTemplate.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ProposalTemplate.objects.filter(pk=item.pk).update(position=idx)


def _normalize_proposal_variable_positions():
    items = ProposalVariable.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ProposalVariable.objects.filter(pk=item.pk).update(position=idx)


def _parse_proposal_sent_at(raw_value: str):
    if not raw_value:
        return timezone.localtime().replace(second=0, microsecond=0)
    try:
        value = datetime.fromisoformat(raw_value)
    except ValueError:
        raise forms.ValidationError("Некорректная дата отправки ТКП.")
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.replace(second=0, microsecond=0)


def _proposal_template_group_ids(template):
    groups = list(template.group_members.all())
    if groups:
        return {group.pk for group in groups}
    if template.group_member_id:
        return {template.group_member_id}
    return set()


def _proposal_template_product_ids(template):
    products = list(template.products.all())
    if products:
        return {product.pk for product in products}
    if template.product_id:
        return {template.product_id}
    return set()


def _proposal_selected_product_ids(proposal):
    products = list(proposal.ordered_products()) if getattr(proposal, "pk", None) else []
    if not products and getattr(proposal, "type_id", None):
        return {proposal.type_id}
    return {product.pk for product in products if getattr(product, "pk", None)}


def _find_proposal_template(proposal, templates):
    proposal_product_ids = _proposal_selected_product_ids(proposal)
    if not proposal_product_ids:
        return None

    candidates = []
    for template in templates:
        template_product_ids = _proposal_template_product_ids(template)
        if template_product_ids and not proposal_product_ids.issubset(template_product_ids):
            continue
        template_group_ids = _proposal_template_group_ids(template)
        if template_group_ids and proposal.group_member_id not in template_group_ids:
            continue
        candidates.append(template)

    if not candidates:
        return None

    def _version_key(template):
        try:
            return int(template.version)
        except (TypeError, ValueError):
            return 0

    candidates.sort(
        key=lambda template: (
            1 if _proposal_template_product_ids(template) else 0,
            -len(_proposal_template_product_ids(template)),
            1 if _proposal_template_group_ids(template) else 0,
            -len(_proposal_template_group_ids(template)),
            _version_key(template),
            template.pk,
        ),
        reverse=True,
    )
    return candidates[0]


def _is_htmx_request(request):
    return request.headers.get("HX-Request", "").lower() == "true"


def _wants_proposal_tables(request):
    return str(request.GET.get("tables") or "") == "1"


@login_required
@user_passes_test(staff_required)
@require_GET
def proposals_partial(request):
    if _is_htmx_request(request) and not _wants_proposal_tables(request):
        return render(request, PROPOSALS_PARTIAL_TEMPLATE, {"proposal_lazy_shell": True})
    try:
        context = _proposals_context(
            request=request,
            debug_nextcloud_links=_proposal_link_debug_enabled(request),
        )
    except NextcloudApiError:
        return HttpResponse(
            "Nextcloud временно недоступен. Не удалось полностью загрузить ссылки на файлы.",
            status=503,
        )
    return render(request, PROPOSALS_PARTIAL_TEMPLATE, context)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_form_create(request):
    if request.method == "GET":
        return _render_proposal_form(request, form=ProposalRegistrationForm(user=request.user), action="create")

    form = ProposalRegistrationForm(request.POST, user=request.user)
    if not form.is_valid():
        return _render_proposal_form(request, form=form, action="create")

    proposal = form.save(commit=False)
    if not getattr(proposal, "position", 0):
        proposal.position = _next_position(ProposalRegistration)
    proposal.save()
    form._save_ranked_products(proposal)
    _remember_proposal_party_links(proposal, request)
    _link_proposal_service_volume(proposal, form, request.user)
    form.save_assets(proposal, request.user)
    form.save_legal_entities(proposal, request.user)
    form.save_objects(proposal, request.user)
    form.save_commercial_offers(proposal, request.user)
    _maybe_create_nextcloud_proposal_workspace(request, proposal)
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_commercial_xlsx_export(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        content = build_commercial_xlsx(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return JsonResponse(
            {"ok": False, "message": str(error) or "Не удалось обработать данные для экспорта."},
            status=400,
        )

    proposal_label = str(payload.get("proposal_label") or "").strip()
    if proposal_label == "Новое ТКП":
        proposal_label = ""
    safe_label = "".join(
        char if char not in '<>:"/\\|?*\r\n\t' else "_"
        for char in proposal_label
    ).strip(" ._")[:120]
    filename = f"{safe_label}_commercial.xlsx" if safe_label else "commercial_offer_draft.xlsx"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    response["Cache-Control"] = "no-store"
    return response


@login_required
@user_passes_test(staff_required)
@require_GET
def proposal_cbr_eur_rate(request):
    eur_rate = get_cbr_eur_rate_for_today()
    return JsonResponse(
        {
            "ok": eur_rate is not None,
            "exchange_rate": format(eur_rate.quantize(Decimal("0.0001")), "f") if eur_rate is not None else "",
            "rub_total_service_text": get_cbr_eur_rate_text(),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_GET
def proposal_product_autofill(request, product_id: int):
    product = get_object_or_404(Product, pk=product_id)
    product_key = str(product.pk)
    group_member = None
    raw_group_member = request.GET.get("group_member")
    if str(raw_group_member or "").isdigit():
        from group_app.models import GroupMember

        group_member = GroupMember.objects.filter(pk=int(raw_group_member)).first()
    data = _proposal_product_autofill_data(product_ids=[product.pk], group_member=group_member)
    response = JsonResponse(
        {
            "ok": True,
            "product_id": product_key,
            "typical_sections": data["typical_sections_json"].get(product_key, []),
            "service_goal_report": data["service_goal_reports_json"].get(product_key, {}),
            "typical_service_compositions": data["typical_service_compositions_json"].get(product_key, []),
            "typical_service_term": data["typical_service_terms_json"].get(product_key, {}),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_form_edit(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    if request.method == "GET":
        return _render_proposal_form(
            request,
            form=ProposalRegistrationForm(instance=proposal, user=request.user),
            action="edit",
            proposal=proposal,
        )

    if proposal.is_content_locked:
        if not can_edit_locked_proposal_status(request.user, proposal.status):
            return _render_proposal_form(
                request,
                form=_proposal_form_with_message(
                    proposal,
                    "Карточка доступна только для просмотра. Создайте новую версию.",
                    user=request.user,
                ),
                action="edit",
                proposal=proposal,
            )
        return _save_locked_proposal_status(request, proposal)

    form = ProposalRegistrationForm(request.POST, instance=proposal, user=request.user)
    if not form.is_valid():
        return _render_proposal_form(request, form=form, action="edit", proposal=proposal)

    proposal = form.save()
    _remember_proposal_party_links(proposal, request)
    _link_proposal_service_volume(proposal, form, request.user)
    form.save_assets(proposal, request.user)
    form.save_legal_entities(proposal, request.user)
    form.save_objects(proposal, request.user)
    form.save_commercial_offers(proposal, request.user)
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_create_version(request, pk: int):
    with transaction.atomic():
        proposal = get_object_or_404(ProposalRegistration.objects.select_for_update(), pk=pk)
        if not proposal.is_content_locked:
            return _render_proposal_form(
                request,
                form=_proposal_form_with_message(
                    proposal,
                    "Версию можно создать только для отправленного, завершённого, отложенного или несостоявшегося ТКП.",
                    user=request.user,
                ),
                action="edit",
                proposal=proposal,
            )
        try:
            created = proposal.create_next_version()
        except ProposalVersionError as exc:
            return _render_proposal_form(
                request,
                form=_proposal_form_with_message(proposal, str(exc), user=request.user),
                action="edit",
                proposal=proposal,
            )
    return _render_proposal_form(
        request,
        form=ProposalRegistrationForm(instance=created, user=request.user),
        action="edit",
        proposal=created,
    )


def _upsert_dispatch_recipient_email(person, email, email_record_id):
    from contacts_app.models import EmailRecord

    record = None
    if email_record_id:
        record = EmailRecord.objects.filter(pk=email_record_id, person=person).first()
    if record is None and email:
        record = (
            EmailRecord.objects.filter(person=person, email__iexact=email)
            .order_by("position", "id")
            .first()
        )
    if not email:
        return record
    if record is None:
        next_position = (EmailRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        return EmailRecord.objects.create(
            person=person,
            email=email,
            valid_from=dt_date.today(),
            record_date=dt_date.today(),
            position=next_position,
        )
    if record.email != email:
        record.email = email
        record.save(update_fields=["email"])
    return record


def _upsert_dispatch_recipient_position(person, organization, job_title, position_record_id):
    from contacts_app.models import PositionRecord

    record = None
    if position_record_id:
        record = PositionRecord.objects.filter(pk=position_record_id, person=person).first()
    if not organization and not job_title:
        if record is not None:
            record.organization_short_name = ""
            record.job_title = ""
            record.save(update_fields=["organization_short_name", "job_title"])
        return record
    if record is None:
        record = (
            PositionRecord.objects.filter(person=person, is_active=True)
            .order_by("position", "id")
            .first()
        )
    if record is None:
        next_position = (PositionRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        return PositionRecord.objects.create(
            person=person,
            organization_short_name=organization,
            job_title=job_title,
            record_date=dt_date.today(),
            position=next_position,
        )
    record.organization_short_name = organization
    record.job_title = job_title
    record.save(update_fields=["organization_short_name", "job_title"])
    return record


def _sync_dispatch_recipient_person(payload, user=None):
    from contacts_app.models import EmailRecord, PersonRecord
    from contacts_app.views import _ensure_person_phone_record, _refresh_person_position_sources

    email = (payload.get("email") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    first_name = (payload.get("first_name") or "").strip()
    middle_name = (payload.get("middle_name") or "").strip()
    organization = (payload.get("organization_short_name") or "").strip()
    job_title = (payload.get("job_title") or "").strip()
    if not any([email, last_name, first_name, middle_name, organization, job_title]):
        return None, None, None

    person = None
    person_id = payload.get("person_id")
    if person_id:
        person = PersonRecord.objects.filter(pk=person_id).first()
    if person is None and email:
        existing_email = (
            EmailRecord.objects.filter(email__iexact=email)
            .select_related("person")
            .order_by("position", "id")
            .first()
        )
        if existing_email is not None:
            person = existing_email.person
    if person is None:
        next_position = (PersonRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        person = PersonRecord.objects.create(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            position=next_position,
        )
        _ensure_person_phone_record(person, user=user)
    elif person_id or any([last_name, first_name, middle_name]):
        person.last_name = last_name
        person.first_name = first_name
        person.middle_name = middle_name
        person.save(update_fields=["last_name", "first_name", "middle_name"])

    email_record = _upsert_dispatch_recipient_email(person, email, payload.get("email_record_id"))
    position_record = _upsert_dispatch_recipient_position(
        person,
        organization,
        job_title,
        payload.get("position_record_id"),
    )
    _refresh_person_position_sources(person)
    return person, email_record, position_record


def _apply_staff_dispatch_recipient(row):
    employee = staff_employee_for_dispatch_contact(
        email=row.email,
        person_id=row.person_id,
        email_record_id=row.email_record_id,
    )
    if employee is None:
        return contact_fields_are_staff_locked(
            email=row.email,
            person_id=row.person_id,
            email_record_id=row.email_record_id,
        )
    row.last_name = employee.user.last_name or ""
    row.first_name = employee.user.first_name or ""
    row.middle_name = employee.patronymic or ""
    row.email = employee.user.email or ""
    position = employee.managed_position_record
    if position is not None:
        row.organization_short_name = position.organization_short_name or ""
        row.job_title = position.job_title or ""
    row.person = employee.person_record
    row.email_record = employee.managed_email_record
    row.position_record = position
    row.save(
        update_fields=[
            "last_name",
            "first_name",
            "middle_name",
            "email",
            "organization_short_name",
            "job_title",
            "person",
            "email_record",
            "position_record",
        ]
    )
    return True


def _sync_dispatch_recipient_registry(proposal, payloads, user):
    rows = list(proposal.dispatch_recipients.order_by("position", "id"))
    for row, payload in zip(rows, payloads):
        if _apply_staff_dispatch_recipient(row):
            continue
        selected_identifier_record_id = payload.get("identifier_record_id")
        selected_from_autocomplete = bool(payload.get("selected_from_autocomplete"))
        if selected_identifier_record_id and not selected_from_autocomplete:
            selected_from_autocomplete = True
        identifier = _sync_to_legal_entity_record(
            row.organization_short_name,
            row.country,
            row.identifier,
            row.registration_number,
            row.registration_date,
            user,
            selected_identifier_record_id=selected_identifier_record_id,
            selected_from_autocomplete=selected_from_autocomplete,
            business_entity_source="[ТКП / Отправка ТКП / Наименование организации]",
        )
        person, email_record, position_record = _sync_dispatch_recipient_person(payload, user=user)
        row.identifier_record = identifier
        row.person = person
        row.email_record = email_record
        row.position_record = position_record
        row.save(update_fields=["identifier_record", "person", "email_record", "position_record"])
    mirror_primary_dispatch_recipient(proposal)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_dispatch_form_edit(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    if request.method == "GET":
        return _render_dispatch_form(
            request,
            form=ProposalDispatchForm(instance=proposal),
            proposal=proposal,
        )

    form = ProposalDispatchForm(request.POST, instance=proposal)
    if not form.is_valid():
        return _render_dispatch_form(request, form=form, proposal=proposal)

    with transaction.atomic():
        proposal = form.save()
        _sync_dispatch_recipient_registry(
            proposal,
            form.cleaned_dispatch_recipients,
            request.user,
        )
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_dispatch_send(request):
    raw_ids = request.POST.getlist("proposal_ids[]") or request.POST.getlist("proposal_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для отправки."}, status=400)

    try:
        proposal_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_proposal_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    try:
        sent_at = _parse_proposal_sent_at(request.POST.get("sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    selected_proposals = list(
        ProposalRegistration.objects
        .filter(pk__in=proposal_ids)
        .select_related("type")
        .prefetch_related(
            Prefetch(
                "dispatch_recipients",
                queryset=ProposalDispatchRecipient.objects.order_by("position", "id"),
            )
        )
        .order_by("position", "id")
    )
    if len(selected_proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    sent_at_display = timezone.localtime(sent_at).strftime("%d.%m.%Y %H:%M")
    if delivery_channels == (PROPOSAL_DELIVERY_CHANNEL_STATUS_ONLY,):
        email_result = {
            "delivery_channels": delivery_channels,
            "email_delivery": {
                "requested": False,
                "attempted": 0,
                "sent": 0,
                "failed": 0,
                "errors": [],
            },
            "sent_proposal_ids": [proposal.pk for proposal in selected_proposals],
        }
    else:
        try:
            _source_kind, local_folder = resolve_proposal_generation_source(request)
        except LocalProposalFolderError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        if local_folder is not None:
            email_result = {
                "delivery_channels": delivery_channels,
                "email_delivery": {
                    "requested": False,
                    "simulated": True,
                    "attempted": 0,
                    "sent": len(selected_proposals),
                    "failed": 0,
                    "errors": [],
                },
                "sent_proposal_ids": [proposal.pk for proposal in selected_proposals],
            }
        else:
            email_result = send_proposal_dispatch_emails(
                proposals=selected_proposals,
                sender=request.user,
                delivery_channels=delivery_channels,
            )
    sent_proposal_ids = email_result["sent_proposal_ids"]
    updated = 0
    sent_updates = []
    if sent_proposal_ids:
        sent_proposal_ids_set = {int(pk) for pk in sent_proposal_ids}
        proposals_to_update = []
        for proposal in selected_proposals:
            if proposal.pk not in sent_proposal_ids_set:
                continue
            proposal.sent_date = sent_at_display
            if proposal.status != ProposalRegistration.ProposalStatus.COMPLETED:
                proposal.status = ProposalRegistration.ProposalStatus.SENT
            proposals_to_update.append(proposal)
            sent_updates.append(
                {
                    "id": proposal.pk,
                    "status": proposal.status,
                    "status_label": proposal.get_status_display(),
                    "sent_date": sent_at_display,
                }
            )
        if proposals_to_update:
            ProposalRegistration.objects.bulk_update(proposals_to_update, ["sent_date", "status"])
            updated = len(proposals_to_update)

    if updated == 0:
        return JsonResponse(
            {
                "ok": False,
                "error": "Не удалось отправить ни одного письма.",
                "email_delivery": email_result["email_delivery"],
                "delivery_channels": list(email_result["delivery_channels"]),
            },
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "sent_at": sent_at_display,
            "proposal_ids": sent_proposal_ids,
            "status": ProposalRegistration.ProposalStatus.SENT,
            "status_label": ProposalRegistration.ProposalStatus.SENT.label,
            "updates": sent_updates,
            "delivery_channels": list(email_result["delivery_channels"]),
            "email_delivery": email_result["email_delivery"],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_dispatch_transfer_to_contract(request):
    raw_ids = request.POST.getlist("proposal_ids[]") or request.POST.getlist("proposal_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для передачи в договор."}, status=400)

    try:
        proposal_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    proposals = list(
        ProposalRegistration.objects
        .filter(pk__in=proposal_ids)
        .select_related("group_member", "type", "country")
        .prefetch_related("product_links__product")
        .order_by("position", "id")
    )
    if len(proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    created = 0
    existing = 0
    transferred_at_display = timezone.localtime().strftime("%d.%m.%Y %H:%M")

    def iter_ranked_proposal_products(proposal):
        links = list(getattr(proposal, "product_links", []).all()) if hasattr(getattr(proposal, "product_links", None), "all") else []
        if links:
            for index, link in enumerate(sorted(links, key=lambda item: ((item.rank or 0), item.pk or 0)), start=1):
                if getattr(link, "product_id", None):
                    yield link.product, index
            return
        if proposal.type_id:
            yield proposal.type, 1

    def sync_project_products_from_proposal(project, proposal):
        has_products = False
        for product, rank in iter_ranked_proposal_products(proposal):
            has_products = True
            ProjectRegistrationProduct.objects.update_or_create(
                registration=project,
                product=product,
                defaults={"rank": rank},
            )
        if has_products:
            _sync_project_registration_primary_product(project.pk)

    with transaction.atomic():
        next_position = (ProjectRegistration.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1
        for proposal in proposals:
            group_alpha2 = (
                getattr(getattr(proposal, "group_member", None), "country_alpha2", "")
                or getattr(proposal, "group", "")
                or ""
            ).strip().upper()
            agreement_number = f"IMCM/{proposal.number}" if group_alpha2 == "RU" else ""
            project = (
                ProjectRegistration.objects
                .filter(
                    number=proposal.number,
                    group_member=proposal.group_member,
                    agreement_type=ProjectRegistration.AgreementType.MAIN,
                    agreement_number=agreement_number,
                )
                .filter(
                    Q(proposal_registration=proposal)
                    | Q(
                        proposal_registration__isnull=True,
                        sub_number=proposal.sub_number,
                    )
                )
                .order_by("position", "id")
                .first()
            )
            was_created = project is None
            if was_created:
                owner_identifier_id = (
                    proposal.customer_identifier_record_id
                    if proposal.asset_owner_matches_customer
                    else proposal.asset_owner_identifier_record_id
                )
                project = ProjectRegistration.objects.create(
                    number=proposal.number,
                    sub_number=proposal.sub_number,
                    group_member=proposal.group_member,
                    agreement_type=ProjectRegistration.AgreementType.MAIN,
                    agreement_number=agreement_number,
                    proposal_registration=proposal,
                    position=next_position,
                    group=proposal.group,
                    type=proposal.type,
                    name=proposal.name,
                    year=proposal.year,
                    customer=proposal.customer,
                    country=proposal.country,
                    identifier=proposal.identifier,
                    registration_number=proposal.registration_number,
                    registration_date=proposal.registration_date,
                    customer_identifier_record_id=proposal.customer_identifier_record_id,
                    asset_owner_identifier_record_id=owner_identifier_id,
                )
                sync_project_products_from_proposal(project, proposal)
                created += 1
                next_position += 1
            else:
                if not project.product_links.exists():
                    sync_project_products_from_proposal(project, proposal)
                existing += 1

        ProposalRegistration.objects.filter(pk__in=proposal_ids).update(
            status=ProposalRegistration.ProposalStatus.COMPLETED,
            transfer_to_contract_date=transferred_at_display,
        )

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "existing": existing,
            "updated": len(proposal_ids),
            "proposal_ids": proposal_ids,
            "status": ProposalRegistration.ProposalStatus.COMPLETED,
            "status_label": ProposalRegistration.ProposalStatus.COMPLETED.label,
            "transfer_to_contract_date": transferred_at_display,
        }
    )


def _onlyoffice_endpoint_unavailable(exc: BaseException) -> bool:
    message = str(exc)
    return (
        "ONLYOFFICE недоступен для генерации PDF" in message
        or "Не удалось скачать PDF из ONLYOFFICE" in message
    )


def _generate_signed_proposal_pdf(user, proposal, signed_docx_bytes: bytes, *, source_url: str) -> dict[str, str]:
    """PDF подписанного ТКП: локальный LibreOffice для local:-файла и запасной путь, если ONLYOFFICE недоступен."""
    docx_link = str(getattr(proposal, "docx_file_link", "") or "")
    source_name = str(getattr(proposal, "docx_file_name", "") or "").strip() or "proposal.docx"

    def render_locally() -> dict[str, str]:
        pdf_bytes = convert_docx_bytes_to_pdf_locally(signed_docx_bytes, source_name=source_name)
        return store_generated_pdf_document(user, proposal, pdf_bytes)

    if is_local_proposal_path(docx_link):
        return render_locally()

    onlyoffice_error = None
    if is_onlyoffice_conversion_configured():
        try:
            return generate_and_store_proposal_pdf(user, proposal, source_url=source_url)
        except RuntimeError as exc:
            if not (local_proposal_folder_enabled() and _onlyoffice_endpoint_unavailable(exc)):
                raise
            onlyoffice_error = exc
    elif not local_proposal_folder_enabled():
        raise RuntimeError("Не настроен ONLYOFFICE Document Server для генерации PDF.")

    try:
        return render_locally()
    except RuntimeError as exc:
        if onlyoffice_error is None:
            raise
        raise RuntimeError(f"{onlyoffice_error}; локальная генерация PDF: {exc}") from exc


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_dispatch_sign_documents(request):
    raw_ids = request.POST.getlist("proposal_ids[]") or request.POST.getlist("proposal_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для подписи ТКП."}, status=400)

    try:
        proposal_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    proposals = list(
        ProposalRegistration.objects
        .filter(pk__in=proposal_ids)
        .select_related("type")
        .order_by("position", "id")
    )
    if len(proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    try:
        facsimile_bytes = _load_proposal_signer_facsimile_bytes(getattr(request.user, "pk", None))
    except RuntimeError as exc:
        return JsonResponse(
            {
                "ok": False,
                "error": str(exc),
                "generated": 0,
                "warnings": [],
            },
            status=400,
        )

    document_updates = []
    errors = []

    for proposal in proposals:
        if not str(getattr(proposal, "docx_file_name", "") or "").strip():
            errors.append(f"Для {proposal.short_uid} сначала сформируйте DOCX-файл ТКП.")
            continue
        try:
            original_docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip()
            original_docx_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
            docx_bytes = load_existing_proposal_docx_bytes(request.user, proposal)
            from contracts_app.docx_processor import insert_floating_image_at_placeholder

            signed_docx_bytes = insert_floating_image_at_placeholder(
                docx_bytes,
                facsimile_bytes,
                placeholder=PROPOSAL_FACSIMILE_PLACEHOLDER,
            )
            stored_docx = store_existing_proposal_docx_bytes(request.user, proposal, signed_docx_bytes)
            proposal.docx_file_name = stored_docx["docx_name"]
            proposal.docx_file_link = stored_docx["docx_path"]
            if (
                proposal.docx_file_name != original_docx_name
                or proposal.docx_file_link != original_docx_link
            ):
                ProposalRegistration.objects.filter(pk=proposal.pk).update(
                    docx_file_name=proposal.docx_file_name,
                    docx_file_link=proposal.docx_file_link,
                )

            stored_pdf = _generate_signed_proposal_pdf(
                request.user,
                proposal,
                signed_docx_bytes,
                source_url=build_proposal_docx_source_url(
                    request,
                    proposal,
                    signer_user_id=getattr(request.user, "pk", None),
                ),
            )
        except Exception as exc:
            errors.append(f"{proposal.short_uid}: {exc}")
            continue
        proposal.docx_file_name = stored_docx["docx_name"]
        proposal.docx_file_link = stored_docx["docx_path"]
        proposal.pdf_file_name = stored_pdf["pdf_name"]
        proposal.pdf_file_link = stored_pdf["pdf_path"]
        document_updates.append(proposal)

    if errors and not document_updates:
        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(errors),
                "generated": 0,
                "warnings": [],
            },
            status=400,
        )

    if document_updates:
        ProposalRegistration.objects.bulk_update(
            document_updates,
            ["docx_file_name", "docx_file_link", "pdf_file_name", "pdf_file_link"],
        )
        _refresh_proposal_nextcloud_file_ids(document_updates)
        _attach_proposal_folder_urls(document_updates, request.user, request=request)

    return JsonResponse(
        {
            "ok": True,
            "message": "PDF для ТКП успешно сформирован.",
            "generated": len(document_updates),
            "warnings": errors,
            "updates": [
                {
                    "id": proposal.pk,
                    "docx_file_name": proposal.docx_file_name,
                    "proposal_docx_file_url": getattr(proposal, "proposal_docx_file_url", "") or "",
                    "pdf_file_name": proposal.pdf_file_name,
                    "proposal_pdf_file_url": getattr(proposal, "proposal_pdf_file_url", "") or "",
                }
                for proposal in document_updates
            ],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_dispatch_create_documents(request):
    raw_ids = request.POST.getlist("proposal_ids[]") or request.POST.getlist("proposal_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для создания ТКП."}, status=400)

    try:
        _source_kind, local_folder = resolve_proposal_generation_source(request)
    except LocalProposalFolderError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    try:
        proposal_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    proposals = list(
        ProposalRegistration.objects
        .filter(pk__in=proposal_ids)
        .select_related("group_member", "type", "country", "currency")
        .prefetch_related("product_links__product")
        .order_by("position", "id")
    )
    if len(proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    templates = list(
        ProposalTemplate.objects
        .select_related("group_member", "product")
        .prefetch_related("group_members", "products")
        .filter(file__gt="")
    )
    variables = list(
        ProposalVariable.objects.order_by("position", "id")
    )

    errors = []
    warnings = []
    generated_count = 0
    generated_updates = []

    for proposal in proposals:
        template = _find_proposal_template(proposal, templates)
        if not template:
            errors.append(f"Не найден образец шаблона для {proposal.short_uid}.")
            continue

        try:
            template.file.open("rb")
            try:
                template_bytes = template.file.read()
            finally:
                template.file.close()
        except Exception:
            errors.append(f"Не удалось прочитать образец «{template.sample_name}» для {proposal.short_uid}.")
            continue

        try:
            replacements, list_replacements, table_replacements = resolve_variables(proposal, variables)
            from contracts_app.docx_processor import process_template

            docx_bytes = process_template(
                template_bytes,
                replacements,
                table_replacements=table_replacements or None,
                list_replacements=list_replacements or None,
                default_language_code="ru-RU",
            )
            if local_folder is not None:
                stored = store_generated_documents_locally(proposal, docx_bytes, local_folder)
            else:
                stored = store_generated_documents(request.user, proposal, docx_bytes, None)
        except Exception as exc:
            errors.append(f"{proposal.short_uid}: {exc}")
            continue

        stored_fields = {
            "docx_file_name": stored["docx_name"],
            "docx_file_link": stored["docx_path"],
            "pdf_file_name": stored["pdf_name"],
            "pdf_file_link": stored["pdf_path"],
        }
        if local_folder is not None:
            stored_fields["docx_file_id"] = ""
            stored_fields["pdf_file_id"] = ""
        ProposalRegistration.objects.filter(pk=proposal.pk).update(**stored_fields)
        proposal.docx_file_name = stored["docx_name"]
        proposal.docx_file_link = stored["docx_path"]
        proposal.pdf_file_name = stored["pdf_name"]
        proposal.pdf_file_link = stored["pdf_path"]
        if local_folder is not None:
            proposal.docx_file_id = ""
            proposal.pdf_file_id = ""
        generated_updates.append(proposal)
        generated_count += 1

    if errors and not generated_count:
        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(errors),
                "warnings": warnings,
                "generated": generated_count,
            },
            status=400,
        )

    if errors:
        warnings.extend(errors)

    if generated_updates:
        _refresh_proposal_nextcloud_file_ids(generated_updates)
        _attach_proposal_folder_urls(generated_updates, request.user, request=request)

    return JsonResponse(
        {
            "ok": True,
            "message": "Документы ТКП успешно созданы.",
            "generated": generated_count,
            "warnings": warnings,
            "updates": [
                {
                    "id": proposal.pk,
                    "docx_file_name": proposal.docx_file_name,
                    "proposal_docx_file_url": getattr(proposal, "proposal_docx_file_url", "") or "",
                    "pdf_file_name": proposal.pdf_file_name,
                    "proposal_pdf_file_url": getattr(proposal, "proposal_pdf_file_url", "") or "",
                }
                for proposal in generated_updates
            ],
        }
    )


@require_GET
def proposal_onlyoffice_docx_source(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    token = str(request.GET.get("token") or "").strip()
    token_payload = get_proposal_docx_source_token_payload(proposal, token)
    if token_payload is None:
        return HttpResponseForbidden("Недействительная ссылка на DOCX-файл ТКП.")

    try:
        docx_bytes = load_existing_proposal_docx_bytes(
            request.user if getattr(request.user, "is_authenticated", False) else None,
            proposal,
        )
    except RuntimeError as exc:
        raise Http404(str(exc))

    signer_user_id = token_payload.get("signer_user_id") if isinstance(token_payload, dict) else None
    if signer_user_id:
        try:
            facsimile_bytes = _load_proposal_signer_facsimile_bytes(signer_user_id)
            from contracts_app.docx_processor import insert_floating_image_at_placeholder

            docx_bytes = insert_floating_image_at_placeholder(
                docx_bytes,
                facsimile_bytes,
                placeholder=PROPOSAL_FACSIMILE_PLACEHOLDER,
            )
        except RuntimeError as exc:
            return HttpResponse(str(exc), status=400)

    file_name = str(getattr(proposal, "docx_file_name", "") or "").strip() or "proposal.docx"
    response = HttpResponse(docx_bytes, content_type=DOCX_CONTENT_TYPE)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(file_name)}"
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_GET
def proposal_generated_docx_download(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    file_path = get_generated_docx_path(proposal)
    if not file_path:
        if is_local_proposal_path(getattr(proposal, "docx_file_link", "")):
            raise Http404("Файл DOCX не найден")
        _attach_proposal_folder_urls([proposal], user=request.user, request=request)
        proposal_docx_file_url = str(getattr(proposal, "proposal_docx_file_url", "") or "").strip()
        if proposal_docx_file_url:
            return redirect(proposal_docx_file_url)
        raise Http404("Файл DOCX не найден")

    response = FileResponse(
        open(file_path, "rb"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(proposal.docx_file_name)}"
    return response


@login_required
@require_GET
def proposal_generated_pdf_download(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    file_path = get_generated_pdf_path(proposal)
    if not file_path:
        if is_local_proposal_path(getattr(proposal, "pdf_file_link", "")):
            raise Http404("Файл PDF не найден")
        _attach_proposal_folder_urls([proposal], user=request.user, request=request)
        proposal_pdf_file_url = str(getattr(proposal, "proposal_pdf_file_url", "") or "").strip()
        if proposal_pdf_file_url:
            return redirect(proposal_pdf_file_url)
        raise Http404("Файл PDF не найден")

    file_name = str(getattr(proposal, "pdf_file_name", "") or "").strip() or file_path.name
    response = FileResponse(open(file_path, "rb"), content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file_name)}"
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_template_form_create(request):
    if request.method == "GET":
        return _render_proposal_template_form(request, form=ProposalTemplateForm(), action="create")

    form = ProposalTemplateForm(request.POST, request.FILES)
    if not form.is_valid():
        response = _render_proposal_template_form(request, form=form, action="create")
        response["HX-Retarget"] = "#proposals-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response

    form.instance.position = _next_position(ProposalTemplate)
    form.save()
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_template_form_edit(request, pk: int):
    template_obj = get_object_or_404(ProposalTemplate, pk=pk)
    if request.method == "GET":
        return _render_proposal_template_form(
            request,
            form=ProposalTemplateForm(instance=template_obj),
            action="edit",
            template_obj=template_obj,
        )

    form = ProposalTemplateForm(request.POST, request.FILES, instance=template_obj)
    if not form.is_valid():
        response = _render_proposal_template_form(
            request,
            form=form,
            action="edit",
            template_obj=template_obj,
        )
        response["HX-Retarget"] = "#proposals-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response

    form.save()
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_template_delete(request, pk: int):
    obj = get_object_or_404(ProposalTemplate, pk=pk)
    if obj.file:
        obj.file.delete(save=False)
    obj.delete()
    _normalize_proposal_template_positions()
    return _render_proposals_updated_or_empty(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_template_move_up(request, pk: int):
    obj = get_object_or_404(ProposalTemplate, pk=pk)
    prev = ProposalTemplate.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ProposalTemplate.objects.filter(pk=obj.pk).update(position=obj.position)
        ProposalTemplate.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_proposals_updated_or_empty(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_template_move_down(request, pk: int):
    obj = get_object_or_404(ProposalTemplate, pk=pk)
    nxt = ProposalTemplate.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ProposalTemplate.objects.filter(pk=obj.pk).update(position=obj.position)
        ProposalTemplate.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_proposals_updated_or_empty(request)


@login_required
@require_http_methods(["GET"])
def proposal_template_download(request, pk: int):
    obj = get_object_or_404(ProposalTemplate, pk=pk)
    if not obj.file:
        raise Http404("Файл не найден")
    file_path = obj.file.path
    if not os.path.isfile(file_path):
        raise Http404("Файл не найден на диске")
    from urllib.parse import quote

    basename = os.path.basename(file_path)
    response = FileResponse(open(file_path, "rb"), content_type="application/octet-stream")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(basename)}"
    return response


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_variable_form_create(request):
    if request.method == "GET":
        return _render_proposal_variable_form(request, form=ProposalVariableForm(), action="create")

    form = ProposalVariableForm(request.POST)
    if not form.is_valid():
        response = _render_proposal_variable_form(request, form=form, action="create")
        response["HX-Retarget"] = "#proposals-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response

    variable = form.save(commit=False)
    variable.position = _next_position(ProposalVariable)
    variable.save()
    return _render_proposal_variables_updated(request, close_modal=True)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_variable_form_edit(request, pk: int):
    variable = get_object_or_404(ProposalVariable, pk=pk)
    if request.method == "GET":
        return _render_proposal_variable_form(request, form=ProposalVariableForm(instance=variable), action="edit", variable=variable)

    form = ProposalVariableForm(request.POST, instance=variable)
    if not form.is_valid():
        response = _render_proposal_variable_form(request, form=form, action="edit", variable=variable)
        response["HX-Retarget"] = "#proposals-modal .modal-content"
        response["HX-Reswap"] = "innerHTML"
        return response

    form.save()
    return _render_proposal_variables_updated(request, close_modal=True)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_variable_delete(request, pk: int):
    get_object_or_404(ProposalVariable, pk=pk).delete()
    _normalize_proposal_variable_positions()
    return _render_proposal_variables_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_variable_move_up(request, pk: int):
    obj = get_object_or_404(ProposalVariable, pk=pk)
    prev = ProposalVariable.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ProposalVariable.objects.filter(pk=obj.pk).update(position=obj.position)
        ProposalVariable.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_proposal_variables_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_variable_move_down(request, pk: int):
    obj = get_object_or_404(ProposalVariable, pk=pk)
    nxt = ProposalVariable.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ProposalVariable.objects.filter(pk=obj.pk).update(position=obj.position)
        ProposalVariable.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_proposal_variables_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_delete(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    proposal.delete()
    _normalize_proposal_positions()
    return _render_proposals_updated_or_empty(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_row_order(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Некорректный формат порядка ТКП."}, status=400)

    raw_ids = payload.get("ordered_proposal_ids") or []
    try:
        ordered_proposal_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Порядок ТКП содержит некорректные идентификаторы."}, status=400)
    if len(ordered_proposal_ids) != len(set(ordered_proposal_ids)):
        return JsonResponse({"ok": False, "error": "Порядок ТКП содержит дубли."}, status=400)

    base_signature = str(payload.get("base_order_signature") or "")
    selected_years = _selected_proposal_years(request)
    with transaction.atomic():
        current_items = list(
            ProposalRegistration.objects.select_for_update().order_by("position", "id")
        )
        by_id = {item.pk: item for item in current_items}
        full_groups, current_proposal_ids = _scoped_proposal_display_ids(current_items, selected_years)
        current_signature = _proposal_order_signature(current_proposal_ids)

        conflict_payload = {
            "ok": False,
            "error": "Порядок ТКП был изменен. Таблица будет обновлена.",
            "current_proposal_ids": current_proposal_ids,
            "order_signature": current_signature,
        }
        if base_signature and base_signature != current_signature:
            if ordered_proposal_ids == current_proposal_ids:
                return JsonResponse({"ok": True, "order_signature": current_signature})
            return JsonResponse(conflict_payload, status=409)
        if (
            any(proposal_id not in by_id for proposal_id in ordered_proposal_ids)
            or set(ordered_proposal_ids) != set(current_proposal_ids)
        ):
            return JsonResponse(conflict_payload, status=409)

        normalized_ids = _normalize_proposal_version_order(ordered_proposal_ids, by_id)
        merged_ids = _merge_scoped_proposal_order(full_groups, normalized_ids, by_id)
        desired_signature = _proposal_order_signature(normalized_ids)
        _persist_proposal_positions(merged_ids)
    return JsonResponse({"ok": True, "order_signature": desired_signature})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def proposal_move_up(request, pk: int):
    _move_proposal_group(pk, "up")
    return _render_proposals_updated_or_empty(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def proposal_move_down(request, pk: int):
    _move_proposal_group(pk, "down")
    return _render_proposals_updated_or_empty(request)
