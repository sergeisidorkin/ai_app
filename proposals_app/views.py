import json
import logging
import os
import sys
from datetime import date as dt_date, datetime
from decimal import Decimal
from urllib.parse import quote

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from classifiers_app.models import LegalEntityRecord
from core.cloud_storage import (
    build_folder_url,
    get_nextcloud_root_path,
    get_primary_cloud_storage_label,
    is_nextcloud_primary,
)
from core.proposal_registry_columns import get_proposal_registry_ui_columns
from core.section_labels import get_app_section_label
from experts_app.models import ExpertProfile, ExpertProfileSpecialty
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.workspace import build_proposal_workspace_path, create_proposal_workspace
from policy_app.models import (
    Product,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalSectionSpecialty,
    TypicalServiceComposition,
    TypicalServiceTerm,
    build_consulting_catalog_meta,
)
from projects_app.models import ProjectRegistration, ProjectRegistrationProduct, _sync_project_registration_primary_product
from smtp_app.models import ExternalSMTPAccount
from users_app.models import Employee

from .cbr import get_cbr_eur_rate_for_today, get_cbr_eur_rate_text
from .forms import (
    ProposalDispatchForm,
    ProposalRegistrationForm,
    ProposalTemplateForm,
    ProposalVariableForm,
    _proposal_group_member_order_map,
    _proposal_group_member_short,
    proposal_variable_registry_json,
)
from .document_generation import (
    DOCX_CONTENT_TYPE,
    build_proposal_docx_source_url,
    generate_and_store_proposal_pdf,
    get_generated_docx_path,
    get_proposal_docx_source_token_payload,
    is_onlyoffice_conversion_configured,
    load_existing_proposal_docx_bytes,
    store_existing_proposal_docx_bytes,
    store_generated_documents,
)
from .models import ProposalRegistration, ProposalTemplate, ProposalVariable
from .services import normalize_proposal_delivery_channels, send_proposal_dispatch_emails
from .variable_resolver import resolve_variables

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
):
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path or normalized_path == "/":
        return "", None

    current_path = normalized_path
    last_share = None
    while current_path and current_path != "/":
        share = client.get_user_share(owner_user_id, current_path, share_with_user_id)
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

    sync_autocomplete_registry_entry(
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
            if not path:
                continue
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

    normalized_root_path = _get_normalized_nextcloud_root_path()
    resolved_cache = {}
    cached_target_paths = _get_cached_proposal_target_paths(request, root_path=normalized_root_path)
    if share_resolution_paths and user is not None and getattr(user, "is_authenticated", False):
        link = NextcloudUserLink.objects.filter(user=user).first()
        if (
            link
            and link.nextcloud_user_id
            and link.nextcloud_user_id != client.username
        ):
            viewer_has_nextcloud_link = True
            try:
                share_map = client.list_user_shares(client.username, link.nextcloud_user_id)
            except NextcloudApiError as exc:
                logger.warning("Could not resolve Nextcloud share targets for proposals table: %s", exc)
                share_map = {}

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
                if not target_path:
                    try:
                        target_path, lookup_share = _resolve_target_path_via_user_share_lookup(
                            client,
                            client.username,
                            path,
                            link.nextcloud_user_id,
                            root_path=normalized_root_path,
                        )
                    except NextcloudApiError as exc:
                        logger.warning(
                            "Could not resolve Nextcloud share target for proposal path %s: %s",
                            path,
                            exc,
                        )
                        target_path = ""
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
                if target_path:
                    resolved_target_cache[path] = target_path
                    resolved_cache[path] = client.build_files_url(target_path)
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
        # Avoid an extra PROPFIND when the file id is already persisted in DB.
        stored_file_id = _stored_proposal_file_id(proposal, stored_attr)
        if stored_file_id:
            return stored_file_id
        if not _is_nextcloud_cloud_path(cloud_path):
            return ""
        try:
            return _resolve_nextcloud_file_id(
                client,
                client.username,
                cloud_path,
                resource_cache=resource_cache,
            )
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


def _proposals_context(request=None, user=None, *, debug_nextcloud_links=False):
    if request is not None and user is None:
        user = request.user
    proposals = ProposalRegistration.objects.select_related(
        "group_member",
        "country",
        "asset_owner_country",
        "type",
        "currency",
    ).prefetch_related("product_links__product").all()
    _attach_proposal_folder_urls(proposals, user=user, request=request, debug_nextcloud_links=debug_nextcloud_links)
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
    return {
        "proposals": proposals,
        "proposal_templates": proposal_templates,
        "proposal_variables": proposal_variables,
        "proposal_registry_ui_columns": get_proposal_registry_ui_columns(),
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "proposal_request_sent_initial": timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
        "has_active_smtp_connection": has_active_smtp_connection,
    }


def _render_proposals_updated(request):
    response = render(
        request,
        PROPOSALS_PARTIAL_TEMPLATE,
        _proposals_context(request=request, debug_nextcloud_links=_proposal_link_debug_enabled(request)),
    )
    response[HX_TRIGGER_HEADER] = HX_PROPOSALS_UPDATED_EVENT
    return response


def _render_proposal_variables_updated(request):
    return render(
        request,
        PROPOSAL_VARIABLES_SECTION_TEMPLATE,
        _proposals_context(request=request, debug_nextcloud_links=_proposal_link_debug_enabled(request)),
    )


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
    products = list(Product.objects.order_by("position", "id"))
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
            }
            for product in products
        ],
    }


def _render_proposal_form(request, *, form, action, proposal=None):
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

    sections = list(
        TypicalSection.objects
        .select_related("product", "expertise_dir", "expertise_direction")
        .prefetch_related(
            Prefetch(
                "ranked_specialties",
                queryset=(
                    TypicalSectionSpecialty.objects
                    .select_related("specialty")
                    .order_by("rank", "id")
                ),
            )
        )
        .order_by("product_id", "position", "id")
    )
    service_goal_reports = list(
        ServiceGoalReport.objects
        .select_related("product")
        .order_by("product_id", "position", "id")
    )
    typical_service_compositions = list(
        TypicalServiceComposition.objects
        .select_related("product", "section")
        .order_by("product_id", "position", "id")
    )
    typical_service_terms = list(
        TypicalServiceTerm.objects
        .select_related("product")
        .order_by("product_id", "position", "id")
    )
    specialty_tariffs = list(
        SpecialtyTariff.objects
        .prefetch_related("specialties")
        .order_by("position", "id")
    )
    section_tariffs = list(
        Tariff.objects
        .select_related("product", "section")
        .order_by("product_id", "position", "id")
    )
    direction_ids = {
        section.expertise_direction_id
        for section in sections
        if section.expertise_direction_id and section.expertise_dir_id
    }
    direction_heads = {}
    if direction_ids:
        for employee in (
            Employee.objects
            .select_related("user")
            .filter(department_id__in=direction_ids, role="Руководитель направления")
            .order_by("position", "id")
        ):
            direction_heads.setdefault(employee.department_id, employee)
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
    for section in sections:
        product_id = str(section.product_id or "")
        if not product_id or not section.name_ru:
            continue
        bucket = sections_map.setdefault(product_id, [])
        if not any(item.get("name") == section.name_ru for item in bucket):
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
            if section.expertise_dir_id and section.expertise_direction_id:
                head = direction_heads.get(section.expertise_direction_id)
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
            "preliminary_report_months": format(item.preliminary_report_months, ".1f"),
            "final_report_weeks": format(item.final_report_weeks, ".1f"),
        }
    return render(
        request,
        PROPOSAL_FORM_TEMPLATE,
        {
            "form": form,
            "action": action,
            "proposal": proposal,
            "proposal_type_meta_json": json.dumps(_proposal_product_catalog(), ensure_ascii=False),
            "typical_sections_json": sections_map,
            "service_goal_reports_json": service_goal_reports_map,
            "typical_service_compositions_json": typical_service_compositions_map,
            "typical_service_terms_json": typical_service_terms_map,
        },
    )


def _render_dispatch_form(request, *, form, proposal):
    _attach_proposal_folder_urls([proposal], user=request.user, request=request)
    return render(
        request,
        PROPOSAL_DISPATCH_FORM_TEMPLATE,
        {
            "form": form,
            "proposal": proposal,
            "docx_download_available": bool(proposal.docx_file_name),
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
    items = ProposalRegistration.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ProposalRegistration.objects.filter(pk=item.pk).update(position=idx)


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
            1 if _proposal_template_group_ids(template) else 0,
            1 if _proposal_template_product_ids(template) else 0,
            -len(_proposal_template_group_ids(template)),
            -len(_proposal_template_product_ids(template)),
            _version_key(template),
            template.pk,
        ),
        reverse=True,
    )
    return candidates[0]


@login_required
@user_passes_test(staff_required)
@require_GET
def proposals_partial(request):
    return render(
        request,
        PROPOSALS_PARTIAL_TEMPLATE,
        _proposals_context(request=request, debug_nextcloud_links=_proposal_link_debug_enabled(request)),
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def proposal_form_create(request):
    if request.method == "GET":
        return _render_proposal_form(request, form=ProposalRegistrationForm(), action="create")

    form = ProposalRegistrationForm(request.POST)
    if not form.is_valid():
        return _render_proposal_form(request, form=form, action="create")

    proposal = form.save(commit=False)
    if not getattr(proposal, "position", 0):
        proposal.position = _next_position(ProposalRegistration)
    proposal.save()
    form._save_ranked_products(proposal)
    form.save_assets(proposal, request.user)
    form.save_legal_entities(proposal, request.user)
    form.save_objects(proposal, request.user)
    form.save_commercial_offers(proposal, request.user)
    _sync_to_legal_entity_record(
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
    if not proposal.asset_owner_matches_customer:
        _sync_to_legal_entity_record(
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
    for asset in getattr(form, "cleaned_assets", []):
        if not _should_sync_proposal_related_row(asset):
            continue
        _sync_to_legal_entity_record(
            asset["short_name"],
            asset["country"],
            asset["identifier"],
            asset["registration_number"],
            asset["registration_date"],
            request.user,
            selected_identifier_record_id=asset.get("selected_identifier_record_id"),
            selected_from_autocomplete=asset.get("selected_from_autocomplete", False),
            business_entity_source="[ТКП / Объем услуг: активы]",
        )
    for legal_entity in getattr(form, "cleaned_legal_entities", []):
        if not _should_sync_proposal_related_row(legal_entity):
            continue
        _sync_to_legal_entity_record(
            legal_entity["short_name"],
            legal_entity["country"],
            legal_entity["identifier"],
            legal_entity["registration_number"],
            legal_entity["registration_date"],
            request.user,
            selected_identifier_record_id=legal_entity.get("selected_identifier_record_id"),
            selected_from_autocomplete=legal_entity.get("selected_from_autocomplete", False),
            business_entity_source="[ТКП / Объем услуг: юрлица]",
        )
    _maybe_create_nextcloud_proposal_workspace(request, proposal)
    return _render_proposals_updated(request)


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
@require_http_methods(["GET", "POST"])
def proposal_form_edit(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    if request.method == "GET":
        return _render_proposal_form(
            request,
            form=ProposalRegistrationForm(instance=proposal),
            action="edit",
            proposal=proposal,
        )

    form = ProposalRegistrationForm(request.POST, instance=proposal)
    if not form.is_valid():
        return _render_proposal_form(request, form=form, action="edit", proposal=proposal)

    proposal = form.save()
    form.save_assets(proposal, request.user)
    form.save_legal_entities(proposal, request.user)
    form.save_objects(proposal, request.user)
    form.save_commercial_offers(proposal, request.user)
    _sync_to_legal_entity_record(
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
    if not proposal.asset_owner_matches_customer:
        _sync_to_legal_entity_record(
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
    for asset in getattr(form, "cleaned_assets", []):
        if not _should_sync_proposal_related_row(asset):
            continue
        _sync_to_legal_entity_record(
            asset["short_name"],
            asset["country"],
            asset["identifier"],
            asset["registration_number"],
            asset["registration_date"],
            request.user,
            selected_identifier_record_id=asset.get("selected_identifier_record_id"),
            selected_from_autocomplete=asset.get("selected_from_autocomplete", False),
            business_entity_source="[ТКП / Объем услуг: активы]",
        )
    for legal_entity in getattr(form, "cleaned_legal_entities", []):
        if not _should_sync_proposal_related_row(legal_entity):
            continue
        _sync_to_legal_entity_record(
            legal_entity["short_name"],
            legal_entity["country"],
            legal_entity["identifier"],
            legal_entity["registration_number"],
            legal_entity["registration_date"],
            request.user,
            selected_identifier_record_id=legal_entity.get("selected_identifier_record_id"),
            selected_from_autocomplete=legal_entity.get("selected_from_autocomplete", False),
            business_entity_source="[ТКП / Объем услуг: юрлица]",
        )
    return _render_proposals_updated(request)


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

    proposal = form.save()
    _sync_to_legal_entity_record(
        proposal.recipient,
        proposal.recipient_country,
        proposal.recipient_identifier,
        proposal.recipient_registration_number,
        proposal.recipient_registration_date,
        request.user,
        business_entity_source="[ТКП / Отправка ТКП / Наименование организации]",
        **_sync_selection_kwargs(request, "recipient_autocomplete"),
    )
    _sync_dispatch_contact_to_person_registry(
        last_name=form.cleaned_data.get("contact_last_name", ""),
        first_name=form.cleaned_data.get("contact_first_name", ""),
        middle_name=form.cleaned_data.get("contact_middle_name", ""),
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
        .order_by("position", "id")
    )
    if len(selected_proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    sent_at_display = timezone.localtime(sent_at).strftime("%d.%m.%Y %H:%M")
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
                .order_by("position", "id")
                .first()
            )
            was_created = project is None
            if was_created:
                project = ProjectRegistration.objects.create(
                    number=proposal.number,
                    group_member=proposal.group_member,
                    agreement_type=ProjectRegistration.AgreementType.MAIN,
                    agreement_number=agreement_number,
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

    if not is_onlyoffice_conversion_configured():
        return JsonResponse(
            {"ok": False, "error": "Не настроен ONLYOFFICE Document Server для генерации PDF."},
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

            stored_pdf = generate_and_store_proposal_pdf(
                request.user,
                proposal,
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
            stored = store_generated_documents(request.user, proposal, docx_bytes, None)
        except Exception as exc:
            errors.append(f"{proposal.short_uid}: {exc}")
            continue

        ProposalRegistration.objects.filter(pk=proposal.pk).update(
            docx_file_name=stored["docx_name"],
            docx_file_link=stored["docx_path"],
            pdf_file_name=stored["pdf_name"],
            pdf_file_link=stored["pdf_path"],
        )
        proposal.docx_file_name = stored["docx_name"]
        proposal.docx_file_link = stored["docx_path"]
        proposal.pdf_file_name = stored["pdf_name"]
        proposal.pdf_file_link = stored["pdf_path"]
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
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def proposal_variable_delete(request, pk: int):
    get_object_or_404(ProposalVariable, pk=pk).delete()
    _normalize_proposal_variable_positions()
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def proposal_move_up(request, pk: int):
    _normalize_proposal_positions()
    items = list(ProposalRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        ProposalRegistration.objects.filter(pk=current.id).update(position=previous.position)
        ProposalRegistration.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_proposal_positions()
    return _render_proposals_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def proposal_move_down(request, pk: int):
    _normalize_proposal_positions()
    items = list(ProposalRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, next_item = items[idx], items[idx + 1]
        ProposalRegistration.objects.filter(pk=current.id).update(position=next_item.position)
        ProposalRegistration.objects.filter(pk=next_item.id).update(position=current.position)
        _normalize_proposal_positions()
    return _render_proposals_updated(request)
