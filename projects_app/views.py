import copy
import csv
import io
import logging
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core import signing
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse, QueryDict, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db import models, transaction
from django.db.models import Max, Q
from django.db.models.functions import Trim
from django import forms
from django.utils import timezone
from urllib.parse import urlencode
from classifiers_app.models import LegalEntityIdentifier, LegalEntityRecord, OKSMCountry
from contracts_app.models import ContractProjectRegistration
from group_app.models import GroupMember
from .models import (
    LegalEntity,
    Performer,
    PerformerParticipationSnapshot,
    PerformerReportUpload,
    ProjectRegistration,
    ProjectRegistrationProduct,
    RegistrationGroupSummaryState,
    RegistrationWorkspaceFolder,
    ReportCheckRule,
    ReportReviewEntry,
    ReportMacro,
    WorkVolume,
    WorkVolumeItem,
    _ensure_performer_rows_for_work_item,
    _sync_project_registration_primary_product,
)
from .registration_summary import (
    DEFERRED_STATUS,
    deferred_pairs_for_numbers,
    is_group_deferred,
    legacy_summary_status_dates,
    registration_summary_state,
    block_is_deferred,
    summary_block_for_group,
    summary_block_for_project,
    summary_block_for_pk,
    summary_indicator_class,
    sync_summary_status_date_for_label_change,
    sync_summary_status_date_for_status_change,
    summary_payload,
    summary_payload_for_registration,
)
from .report_access import (
    annotate_report_submission_rows,
    can_adjust_report_findings,
    can_manage_report_checks,
    can_mutate_report_slot,
    can_mutate_report_upload,
    can_send_reports,
    can_view_report_upload,
    show_finding_adjustment_columns,
    is_admin_user,
    is_expert_user,
    is_report_readonly_user,
    report_visible_registration_ids,
)
from .report_macro_runner import report_acceptance_threshold
from .local_contract_storage import (
    LocalContractCloud,
    LocalContractFolderError,
    encode_local_contract_path,
    is_local_contract_path,
    local_contract_cloud_path,
    read_local_contract_docx,
    resolve_local_contract_folder,
)
from .report_submission import (
    ReportUploadError,
    annotate_performers_report_section_lock,
    annotate_performers_section_codes,
    annotate_work_volumes_for_projects_table,
    FindingCorrectionError,
    apply_finding_correction,
    build_report_history_row,
    build_report_review_current_row,
    build_report_slot_current_row,
    build_report_slot_rows,
    build_report_submission_rows,
    clear_report_check_result,
    delete_report_upload,
    format_grouped_count,
    format_report_datetime,
    format_report_finding_count,
    format_report_public_finding_count,
    mark_corrected_workflow_status,
    report_finding_edit_payload,
    report_finding_context,
    report_finding_groups,
    report_upload_section_label,
    format_report_status_date,
    format_report_version,
    is_local_report_path,
    local_report_folder_enabled,
    local_report_folder_placeholder,
    locked_report_section_sequences,
    next_work_volume_asset_code,
    parse_local_report_path,
    performer_has_report_uploads,
    performer_report_section_locked,
    performer_section_code_ids_by_asset,
    previous_report_upload,
    read_local_report_bytes,
    report_workflow_status,
    report_workflow_status_class,
    report_section_number,
    report_slot_row_id,
    recover_abandoned_report_checks,
    report_check_error_reason,
    pending_report_check_payload,
    resolve_report_upload_source,
    accept_report_review_without_remarks,
    resume_report_check,
    send_report_upload,
    submit_report_review_file,
    withdraw_pending_report_remarks,
    upload_report_file,
    validate_workspace_folder_roles,
    work_scope_order_lock_reason,
    work_item_report_folder_locked,
    work_volume_asset_code,
)
from .forms import (
    ProjectRegistrationForm,
    ContractConditionsForm,
    ProjectScheduleTaskForm,
    WorkVolumeForm,
    PerformerForm,
    BootstrapMixin,
    LegalEntityForm,
    ReportCheckRuleForm,
    ReportMacroForm,
    _parse_project_form_date,
    _project_coordinator_choices,
    _project_manager_choices,
    _resolve_project_coordinator_choice,
    _resolve_project_manager_choice,
)
from .service_scope import (
    align_project_service_scope,
    collapse_service_rows,
    delete_work_scope,
    legal_scope_copies,
    mirror_legal_positions,
    mirror_work_positions,
)
from .services.schedule_copy import copy_typical_gantt_to_project
from .services import gantt_tasks

import json
import os
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import quote

from experts_app.models import ExpertProfile
from core.cloud_storage import (
    CloudStorageNotReadyError,
    build_workspace_folder_tree,
    contains_workspace_project_variable,
    create_basic_project_workspace_stream as routed_create_basic_project_workspace_stream,
    create_folder as cloud_create_folder,
    create_project_workspace as routed_create_project_workspace,
    create_source_data_workspace_stream as routed_create_source_data_workspace_stream,
    download_file as cloud_download_file,
    get_any_connected_service_user,
    get_primary_cloud_storage_label,
    get_registration_standard_folders,
    get_selected_root_path,
    get_workspace_result_class,
    is_nextcloud_primary,
    list_folder_resources,
    publish_resource as cloud_publish_resource,
    sanitize_folder_name,
    upload_file as cloud_upload_file,
)
from core.cloud_paths import (
    CONTRACTS_PERFORMERS_FOLDER,
    CONTRACTS_SECTION_FOLDER,
    join_cloud_path,
    normalize_cloud_path,
)
from policy_app.models import (
    ADMIN_GROUP,
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    EXPERT_GROUP,
    LAWYER_GROUP,
    Product,
    PROJECTS_COORDINATOR_GROUP,
    PROJECTS_HEAD_GROUP,
    ServiceGoalReport,
    SYSTEM_DSC_SECTION_CODE,
    TypicalSection,
    TypicalServiceTerm,
    build_consulting_catalog_meta,
)
from smtp_app.models import ExternalSMTPAccount
from users_app.models import Employee
from users_app.forms import FREELANCER_LABEL
from notifications_app.services import (
    complete_contract_notifications_for_performers,
    create_contract_notifications,
    create_info_request_notifications,
    create_participation_notifications,
    create_payment_request_notifications,
    normalize_delivery_channels,
    complete_report_remarks_for_upload,
    send_report_remarks_notices,
    sync_payment_request_notifications_for_performers,
)
from proposals_app.document_generation import (
    DOCX_CONTENT_TYPE,
    convert_docx_source_to_pdf,
    is_onlyoffice_conversion_configured,
)
from contracts_app.docx_processor import (
    clear_text_highlighting,
    document_contains_literal,
    insert_floating_image_at_placeholder,
    remove_literal_placeholders,
)
from contracts_app.services import build_contract_file_name, build_contract_number, contract_executor_short_name
from contracts_app.services import (
    contract_project_folder_name,
    contract_project_registration_display_id,
    contract_registration_folder_name,
)

PROJECTS_PARTIAL_TEMPLATE = "projects_app/projects_partial.html"
REG_FORM_TEMPLATE       = "projects_app/registration_form.html"
CONTRACT_FORM_TEMPLATE  = "projects_app/contract_form.html"
SCHEDULE_FORM_TEMPLATE  = "projects_app/project_schedule_form.html"
WORK_FORM_TEMPLATE      = "projects_app/work_form.html"
LEGAL_FORM_TEMPLATE     = "projects_app/legal_entity_form.html"
REPORT_CHECK_FORM_TEMPLATE = "projects_app/report_check_form.html"
REPORT_MACRO_FORM_TEMPLATE = "projects_app/report_macro_form.html"
REPORT_MACROS_SECTION_TEMPLATE = "projects_app/report_macros_section.html"
PROJECTS_MODAL_CONTENT_SELECTOR = "#projects-modal .modal-content"


def _render_projects_modal_form_error(request, template_name, context):
    """Невалидная форма из #projects-modal.

    Формы модалки целятся в #projects-pane (outerHTML) — это нужно для
    успешного ответа, который перерисовывает весь пан. Ошибочный ответ
    содержит только разметку формы, поэтому перенаправляем swap обратно в
    .modal-content, иначе фрагмент формы заменит собой весь пан.
    """
    response = render(request, template_name, context)
    response["HX-Retarget"] = PROJECTS_MODAL_CONTENT_SELECTOR
    response["HX-Reswap"] = "innerHTML"
    return response


REPORT_MACRO_CSV_HEADERS = [
    "Курс",
    "Секция",
    "Раздел",
    "Номер",
    "Название",
    "Описание",
    "Код",
    "Вид проверки",
    "Наименование навыка DHS",
    "Модель",
    "Уровень рассуждений",
    "Без инструментов",
    "Режим обработки",
    "Температура",
    "Модель валидации",
    "Уровень рассуждений валидации",
    "Температура валидации",
]
REPORT_MACRO_CSV_SKILL_COLUMNS = 10
REPORT_MACRO_CSV_LEGACY_COLUMNS = 5
REPORT_MACRO_CSV_MIN_COLUMNS = 7
REPORT_MACRO_PAGE_SIZE = 25
REPORT_MACRO_PAGE_SIZE_OPTIONS = (25, 50, 100)
REPORT_SUBMISSION_TABLE_TEMPLATE = "projects_app/report_submission_table.html"
REPORT_TABLE_PAGE_SIZE = 25
REPORT_TABLE_PAGE_SIZE_OPTIONS = (25, 50, 100)

PERF_FORM_TEMPLATE    = "projects_app/performer_form.html"
PERFORMERS_PARTIAL_TEMPLATE = "projects_app/performers_partial.html"

HX_TRIGGER_HEADER = "HX-Trigger"
HX_PERFORMERS_UPDATED_EVENT = "performers-updated"
HX_PROJECTS_UPDATED_EVENT = "projects-updated"
logger = logging.getLogger(__name__)

CONTRACT_DOCX_SOURCE_TOKEN_SALT = "projects_app.contract_docx_source"
CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER = "[[facsimile_prfrm]]"
CONTRACT_IMAGE_PLACEHOLDER_SPECS = (
    ("[[seal]]", "Печать организации"),
    ("[[facsimile_imcm]]", "Подпись руководителя организации"),
)

def staff_required(user):
    return user.is_authenticated and user.is_staff


def _is_admin_user(user):
    return is_admin_user(user)


def _normalize_contract_person_name(value):
    return " ".join(str(value or "").split()).strip()


def performer_contract_signing_required(user):
    if not staff_required(user):
        return False
    employee = getattr(user, "employee_profile", None)
    employee_role = getattr(employee, "role", "") or ""
    return (
        user.groups.filter(name=ADMIN_GROUP).exists()
        or user.groups.filter(name=EXPERT_GROUP).exists()
        or employee_role in {ADMIN_GROUP, EXPERT_GROUP}
    )


def _confirmed_project_ids_for_expert(user):
    employee = getattr(user, "employee_profile", None)
    is_expert = getattr(employee, "role", "") == EXPERT_GROUP
    if not is_expert and user and getattr(user, "is_authenticated", False):
        is_expert = user.groups.filter(name=EXPERT_GROUP).exists()
    if not is_expert:
        return None
    if not employee:
        return []
    return list(
        Performer.objects
        .filter(
            employee=employee,
        )
        .filter(
            Q(participation_response=Performer.ParticipationResponse.CONFIRMED)
            | Q(participation_request_sent_at__isnull=False)
        )
        .exclude(participation_response=Performer.ParticipationResponse.DECLINED)
        .values_list("registration_id", flat=True)
        .distinct()
    )


def _uniform_summary_text(block, getter):
    values = [" ".join(str(getter(item) or "").split()) for item in block]
    if all(value == values[0] for value in values):
        return values[0]
    return None


def _uniform_summary_date(block, getter, date_format="%d.%m.%y"):
    values = [getter(item) for item in block]
    if not all(value == values[0] for value in values):
        return None
    value = values[0]
    return value.strftime(date_format) if value else ""


def _uniform_summary_country(block, id_attr, relation_attr):
    ids = [getattr(item, id_attr) for item in block]
    if not all(value == ids[0] for value in ids):
        return None
    related = getattr(block[0], relation_attr, None)
    return getattr(related, "short_name", "") if related else ""


def _summary_status_date_label(first, legacy_status_dates):
    if getattr(first, "registration_summary_label", "") == "Не начат":
        return ""
    if first.stage_project_id:
        parent = first.stage_project
        value = parent.summary_status_date if parent is not None else None
    else:
        value = (legacy_status_dates or {}).get((first.number, first.group_display))
    return value.strftime("%d.%m.%Y") if value else ""


def _annotate_registration_summary_columns(first, block, legacy_status_dates=None):
    source = first.stage_project if first.stage_project_id else first
    last = block[-1]
    last_deadline = last.deadline
    first.registration_summary_year = source.year or ""
    first.registration_summary_manager = source.project_manager or ""
    first.registration_summary_manager_value = source.project_manager_prs_id or source.project_manager or ""
    first.registration_summary_coordinator = source.project_coordinator or ""
    first.registration_summary_coordinator_value = (
        source.project_coordinator_prs_id or source.project_coordinator or ""
    )
    first.registration_summary_evaluation_date = _uniform_summary_date(
        block, lambda item: item.evaluation_date, "%d.%m.%Y"
    )
    first.registration_summary_status_date = _summary_status_date_label(first, legacy_status_dates)
    first.registration_summary_deadline = last_deadline.strftime("%d.%m.%Y") if last_deadline else ""
    first.registration_summary_deadline_iso = last_deadline.isoformat() if last_deadline else ""
    first.registration_summary_last_id = last.pk
    first.registration_summary_customer = _uniform_summary_text(block, lambda item: item.customer)
    first.registration_summary_country = _uniform_summary_country(block, "country_id", "country")
    first.registration_summary_identifier = _uniform_summary_text(block, lambda item: item.identifier)
    first.registration_summary_registration_number = _uniform_summary_text(
        block, lambda item: item.registration_number
    )
    first.registration_summary_region = _uniform_summary_text(block, lambda item: item.registration_region)
    first.registration_summary_registration_date = _uniform_summary_date(
        block, lambda item: item.registration_date
    )
    first.registration_summary_asset_owner = _uniform_summary_text(block, lambda item: item.asset_owner)
    first.registration_summary_asset_owner_country = _uniform_summary_country(
        block, "asset_owner_country_id", "asset_owner_country"
    )
    first.registration_summary_asset_owner_identifier = _uniform_summary_text(
        block, lambda item: item.asset_owner_identifier
    )
    first.registration_summary_asset_owner_registration_number = _uniform_summary_text(
        block, lambda item: item.asset_owner_registration_number
    )
    first.registration_summary_asset_owner_region = _uniform_summary_text(
        block, lambda item: item.asset_owner_region
    )
    first.registration_summary_asset_owner_date = _uniform_summary_date(
        block, lambda item: item.asset_owner_registration_date
    )
    party_hides = {
        "registration_hide_customer": first.registration_summary_customer is not None,
        "registration_hide_country": first.registration_summary_country is not None,
        "registration_hide_identifier": first.registration_summary_identifier is not None,
        "registration_hide_registration_number": first.registration_summary_registration_number is not None,
        "registration_hide_region": first.registration_summary_region is not None,
        "registration_hide_registration_date": first.registration_summary_registration_date is not None,
        "registration_hide_asset_owner": first.registration_summary_asset_owner is not None,
        "registration_hide_asset_owner_country": first.registration_summary_asset_owner_country is not None,
        "registration_hide_asset_owner_identifier": first.registration_summary_asset_owner_identifier is not None,
        "registration_hide_asset_owner_registration_number": (
            first.registration_summary_asset_owner_registration_number is not None
        ),
        "registration_hide_asset_owner_region": first.registration_summary_asset_owner_region is not None,
        "registration_hide_asset_owner_date": first.registration_summary_asset_owner_date is not None,
    }
    for item in block:
        for name, hidden in party_hides.items():
            setattr(item, name, hidden)


def _apply_registration_summary(block, summary_key, group_label, deferred, legacy_status_dates=None):
    first = block[0]
    contract_ids = {item.contract_project_registration_id for item in block}
    agreements = {item.agreement_type for item in block}
    uniform_contract = len(contract_ids) == 1 and len(agreements) == 1
    summary_type = "-".join(item.type_short_display for item in block if item.type_short_display)
    contract = first.contract_project_registration if uniform_contract else None
    summary_state = registration_summary_state([item.status for item in block], deferred)
    first.opens_registration_summary = True
    first.registration_summary_type = summary_type
    first.registration_summary_hide_contract = uniform_contract
    first.registration_summary_contract_label = contract.short_uid if contract else ""
    first.registration_summary_agreement = first.get_agreement_type_display() if uniform_contract else ""
    first.registration_summary_label = summary_state["label"]
    first.registration_summary_auto_label = summary_state["auto_label"]
    first.registration_summary_deferred = summary_state["deferred"]
    first.registration_summary_can_launch = summary_state["can_launch"]
    first.registration_summary_group = group_label
    first.registration_summary_indicator_class = (
        "" if summary_state["can_launch"] else summary_indicator_class(summary_state["label"])
    )
    for item in block:
        item.in_registration_summary = True
        item.registration_summary_key = summary_key
        item.registration_summary_hide_contract = uniform_contract
        item.registry_uid = item.short_uid
    _annotate_registration_summary_columns(first, block, legacy_status_dates)


def _annotate_registration_number_groups(registrations):
    items = list(registrations)
    for registration in items:
        registration.opens_registration_summary = False
        registration.in_registration_summary = False
        registration.registration_summary_key = ""
        registration.registration_summary_type = ""
        registration.registration_summary_hide_contract = False
        registration.registration_summary_contract_label = ""
        registration.registration_summary_agreement = ""
        registration.registration_summary_label = ""
        registration.registration_summary_auto_label = ""
        registration.registration_summary_deferred = False
        registration.registration_summary_can_launch = False
        registration.registration_summary_group = ""
        registration.registration_summary_indicator_class = ""
        registration.registration_summary_status_date = ""
        registration.registry_uid = registration.short_uid
    deferred_pairs = deferred_pairs_for_numbers({item.number for item in items})
    legacy_status_dates = legacy_summary_status_dates({item.number for item in items})
    start = 0
    while start < len(items):
        current_number = items[start].number
        end = start + 1
        while end < len(items) and items[end].number == current_number:
            end += 1
        group_size = end - start
        group_key = f"{current_number}:{start}"
        for offset, registration in enumerate(items[start:end], start=1):
            registration.number_group_key = group_key
            registration.is_first_for_number = offset == 1
            registration.is_continuation = offset > 1
            registration.has_next_for_number = offset < group_size
            if offset < group_size:
                next_registration = items[start + offset]
                registration.has_next_for_different_contract_in_number_group = (
                    next_registration.contract_project_registration_id
                    != registration.contract_project_registration_id
                )
            else:
                registration.has_next_for_different_contract_in_number_group = False
        start = end
    for index, registration in enumerate(items):
        previous = items[index - 1] if index > 0 else None
        registration.is_first_for_number_contract = (
            previous is None
            or previous.number != registration.number
            or previous.contract_project_registration_id != registration.contract_project_registration_id
        )
    parent_blocks = {}
    for registration in items:
        if registration.stage_project_id:
            parent_blocks.setdefault(registration.stage_project_id, []).append(registration)
    for block in parent_blocks.values():
        if len(block) >= 2:
            parent = block[0].stage_project
            group_label = parent.group_display if parent is not None else block[0].group_display
            deferred = bool(parent.summary_deferred) if parent is not None else False
            _apply_registration_summary(
                block,
                f"project:{block[0].stage_project_id}",
                group_label,
                deferred,
                legacy_status_dates,
            )
    start = 0
    while start < len(items):
        current_group = items[start].group_display
        end = start + 1
        while (
            end < len(items)
            and items[end].number == items[start].number
            and items[end].group_display == current_group
        ):
            end += 1
        block = [item for item in items[start:end] if not item.in_registration_summary and not item.stage_project_id]
        if len(block) >= 2 and block == items[start:end]:
            first = block[0]
            contract_ids = {item.contract_project_registration_id for item in block}
            agreements = {item.agreement_type for item in block}
            uniform_contract = len(contract_ids) == 1 and len(agreements) == 1
            summary_key = f"{first.formatted_number}:{current_group}"
            summary_type = "-".join(
                item.type_short_display for item in block if item.type_short_display
            )
            contract = first.contract_project_registration if uniform_contract else None
            first.opens_registration_summary = True
            first.registration_summary_type = summary_type
            first.registration_summary_hide_contract = uniform_contract
            first.registration_summary_contract_label = (
                contract.short_uid if contract else ""
            )
            first.registration_summary_agreement = (
                first.get_agreement_type_display() if uniform_contract else ""
            )
            summary_state = registration_summary_state(
                [item.status for item in block],
                (first.number, current_group) in deferred_pairs,
            )
            first.registration_summary_label = summary_state["label"]
            first.registration_summary_auto_label = summary_state["auto_label"]
            first.registration_summary_deferred = summary_state["deferred"]
            first.registration_summary_can_launch = summary_state["can_launch"]
            first.registration_summary_group = current_group
            first.registration_summary_indicator_class = (
                "" if summary_state["can_launch"] else summary_indicator_class(summary_state["label"])
            )
            for item in block:
                item.in_registration_summary = True
                item.registration_summary_key = summary_key
                item.registration_summary_hide_contract = uniform_contract
                item.registry_uid = item.short_uid
            _annotate_registration_summary_columns(first, block, legacy_status_dates)
        start = end
    for registration in items:
        parent = registration.stage_project if registration.stage_project_id else None
        if parent is not None and not registration.in_registration_summary:
            registration.registry_uid = parent.short_uid or registration.short_uid
    return items


def _owning_project_ids(registration_ids):
    ids = []
    seen = set()
    rows = ProjectRegistration.objects.filter(pk__in=list(registration_ids)).values_list("pk", "stage_project_id")
    for pk, parent_id in rows:
        owning_id = parent_id or pk
        if owning_id in seen:
            continue
        seen.add(owning_id)
        ids.append(owning_id)
    return ids


def _projects_context(user=None):
    expert_project_ids = _confirmed_project_ids_for_expert(user)
    is_expert = expert_project_ids is not None
    product_prefetch = models.Prefetch(
        "product_links",
        queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    stage_prefetch = models.Prefetch(
        "stages",
        queryset=(
            ProjectRegistration.objects
            .select_related("type")
            .prefetch_related(product_prefetch)
            .order_by("position", "id")
        ),
    )
    registrations = (
        ProjectRegistration.objects
        .registry_rows()
        .select_related(
            "country",
            "asset_owner_country",
            "group_member",
            "type",
            "contract_project_registration",
            "stage_project",
            "stage_project__group_member",
        )
        .prefetch_related(product_prefetch)
    )
    if expert_project_ids is not None:
        registrations = registrations.filter(id__in=expert_project_ids)
    work_items = (
        WorkVolume.objects
        .select_related("project", "project__group_member", "project__type", "country")
        .prefetch_related(
            models.Prefetch(
                "project__product_links",
                queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
            )
        )
        .all()
    )
    if expert_project_ids is not None:
        work_items = work_items.filter(project_id__in=expert_project_ids)
    work_items = work_items.select_related("project__stage_project").prefetch_related(
        models.Prefetch("project__stages", queryset=stage_prefetch.queryset),
        models.Prefetch("project__stage_project__stages", queryset=stage_prefetch.queryset),
    )
    work_items = collapse_service_rows(annotate_work_volumes_for_projects_table(work_items))
    legal_entities = (
        LegalEntity.objects
        .select_related(
            "project",
            "project__group_member",
            "project__type",
            "work_item",
            "work_item__project",
            "work_item__project__type",
            "country",
        )
        .prefetch_related(
            models.Prefetch(
                "project__product_links",
                queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
            ),
            models.Prefetch(
                "work_item__project__product_links",
                queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
            ),
        )
        .all()
    )
    if expert_project_ids is not None:
        legal_entities = legal_entities.filter(project_id__in=expert_project_ids)
    legal_entities = legal_entities.select_related("project__stage_project").prefetch_related(
        models.Prefetch("project__stages", queryset=stage_prefetch.queryset),
        models.Prefetch("project__stage_project__stages", queryset=stage_prefetch.queryset),
    )
    legal_entities = collapse_service_rows(list(legal_entities))
    legal_stage_ids = [entity.project_id for entity in legal_entities]
    work_stage_ids = [item.project_id for item in work_items]
    filter_projects = (
        ProjectRegistration.objects
        .project_records()
        .select_related("type")
        .prefetch_related(product_prefetch, stage_prefetch)
        .order_by("-number", "-id")
    )
    if expert_project_ids is not None:
        filter_projects = filter_projects.filter(
            Q(pk__in=expert_project_ids) | Q(stages__pk__in=expert_project_ids)
        ).distinct()
    registration_rows = list(registrations)
    schedule_items = gantt_tasks.iter_schedule_rows(registration_rows)
    reg_filter_projects = filter_projects
    schedule_projects = filter_projects
    work_projects = filter_projects.filter(pk__in=_owning_project_ids(work_stage_ids))
    legal_projects = filter_projects.filter(pk__in=_owning_project_ids(legal_stage_ids))
    return {
        "registrations": _annotate_registration_number_groups(registration_rows),
        "reg_filter_projects": reg_filter_projects,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "schedule_items": schedule_items,
        "schedule_projects": schedule_projects,
        "work_items": work_items,
        "work_projects": work_projects,
        "legal_entities": legal_entities,
        "legal_projects": legal_projects,
        "registration_status_choices": ProjectRegistration.STATUS_CHOICES,
        "registration_manager_choices": _project_manager_choices("", show_prs_label=False),
        "registration_coordinator_choices": _project_coordinator_choices("", show_prs_label=False),
        "is_expert": is_expert,
        "is_admin": _is_admin_user(user),
    }


def _short_fio_label(value):
    parts = " ".join(str(value or "").split()).split(" ")
    if not parts or not parts[0]:
        return ""
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{parts[0]} {initials}".strip()


def _short_date_label(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _status_date_fields(registration):
    if registration is None or registration.status == "Не начат":
        return {"statusDate": "", "statusDateLabel": ""}
    value = registration.status_date
    return {
        "statusDate": value.isoformat() if value else "",
        "statusDateLabel": _short_date_label(value),
    }


def _product_option_label(product):
    return " ".join(
        part for part in ((product.short_name or "").strip(), (product.display_name or "").strip()) if part
    )


def _registration_product_catalog():
    from policy_app.product_groups import catalog_group_payload, product_catalog_queryset

    products = list(product_catalog_queryset())
    typical_terms = {}
    service_goal_reports = {}
    for item in (
        ServiceGoalReport.objects
        .filter(product__in=products)
        .order_by("product_id", "position", "id")
    ):
        product_id = str(item.product_id or "")
        if not product_id or product_id in service_goal_reports:
            continue
        service_goal_reports[product_id] = {
            "report_title": item.report_title or "",
            "service_goal": item.service_goal or "",
        }
    for item in (
        TypicalServiceTerm.objects
        .filter(product__in=products)
        .order_by("product_id", "position", "id")
    ):
        product_id = str(item.product_id or "")
        if not product_id or product_id in typical_terms:
            continue
        typical_terms[product_id] = {
            "source_data_weeks": str(item.source_data_weeks),
            "source_data_term_unit": item.source_data_term_unit,
            "preliminary_report_months": format(item.preliminary_report_months, ".1f"),
            "preliminary_report_term_unit": item.preliminary_report_term_unit,
            "final_report_weeks": format(item.final_report_weeks, ".1f"),
            "final_report_term_unit": item.final_report_term_unit,
        }
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
        "options": [
            {"id": product.pk, "label": _product_option_label(product)}
            for product in products
        ],
        "meta": {
            "consulting_types": consulting_types,
            "service_categories": service_categories,
            "products": [
                {
                    "id": product.pk,
                    "label": _product_option_label(product),
                    "short_label": (product.short_name or "").strip(),
                    "consulting_type": (product.consulting_type_display or "").strip(),
                    "service_category": (product.service_category_display or "").strip(),
                    "service_subtype": (product.service_subtype_display or "").strip(),
                    "service_goal_report": service_goal_reports.get(str(product.pk), {}),
                    "typical_service_terms": typical_terms.get(str(product.pk), {}),
                    **catalog_group_payload(product),
                }
                for product in products
            ],
        },
    }


def _request_list(data, key):
    if hasattr(data, "getlist"):
        return [str(value or "").strip() for value in data.getlist(key)]
    value = data.get(key, [])
    if isinstance(value, (list, tuple)):
        return [str(item or "").strip() for item in value]
    return [str(value or "").strip()]


def _request_decimal_at(data, key, index):
    values = _request_list(data, key)
    if index >= len(values):
        return None
    raw = values[index].replace(",", ".").strip()
    if not raw:
        return None
    try:
        return forms.DecimalField(required=False, min_value=0).clean(raw)
    except forms.ValidationError:
        return None


def _registration_selected_type_rows(form, registration=None):
    if form.is_bound:
        consulting_types = _request_list(form.data, "type_consulting")
        service_categories = _request_list(form.data, "type_service_category")
        service_subtypes = _request_list(form.data, "type_service_subtype")
        product_ids = _request_list(form.data, "type_id")
        group_ids = _request_list(form.data, "row_group_id")
        row_count = max(
            len(consulting_types),
            len(service_categories),
            len(service_subtypes),
            len(product_ids),
            1,
        )
        rows = []
        for index in range(row_count):
            row = {
                "rank": index + 1,
                "consulting_type": consulting_types[index] if index < len(consulting_types) else "",
                "service_category": service_categories[index] if index < len(service_categories) else "",
                "service_subtype": service_subtypes[index] if index < len(service_subtypes) else "",
                "product_id": product_ids[index] if index < len(product_ids) else "",
                "product_group_id": group_ids[index] if index < len(group_ids) else "",
            }
            has_data = any(
                row[key]
                for key in ("consulting_type", "service_category", "service_subtype", "product_id")
            )
            if has_data or row_count == 1:
                rows.append(row)
        return rows or [{
            "rank": 1,
            "consulting_type": "",
            "service_category": "",
            "service_subtype": "",
            "product_id": "",
            "product_group_id": "",
        }]
    if registration is None:
        registration = getattr(form, "instance", None)
    if registration and getattr(registration, "pk", None):
        links = list(registration._ordered_product_links()) if hasattr(registration, "_ordered_product_links") else []
        if links:
            rows = []
            for index, link in enumerate(links, start=1):
                product = getattr(link, "product", None)
                if product is None:
                    continue
                rows.append({
                    "rank": index,
                    "consulting_type": (product.consulting_type_display or "").strip(),
                    "service_category": (product.service_category_display or "").strip(),
                    "service_subtype": (product.service_subtype_display or "").strip(),
                    "product_id": str(product.pk),
                    "product_group_id": str(getattr(link, "product_group_id", "") or ""),
                })
            if rows:
                return rows
        return [
            {
                "rank": index,
                "consulting_type": (product.consulting_type_display or "").strip(),
                "service_category": (product.service_category_display or "").strip(),
                "service_subtype": (product.service_subtype_display or "").strip(),
                "product_id": str(product.pk),
                "product_group_id": "",
            }
            for index, product in enumerate(registration.ordered_products(), start=1)
        ] or [{
            "rank": 1,
            "consulting_type": "",
            "service_category": "",
            "service_subtype": "",
            "product_id": "",
            "product_group_id": "",
        }]
    return [{
        "rank": 1,
        "consulting_type": "",
        "service_category": "",
        "service_subtype": "",
        "product_id": "",
        "product_group_id": "",
    }]


def _registration_form_page_label(action, registration):
    if action == "create" or registration is None:
        return "Новый проект"
    parent_uid = ""
    if getattr(registration, "stage_project_id", None):
        parent = getattr(registration, "stage_project", None)
        parent_uid = getattr(parent, "short_uid", "") or ""
    return parent_uid or getattr(registration, "short_uid", "") or "Проект"


def _terms_project_storage_key(registration):
    """Ключ localStorage для свёрнутых столбцов сроков одного проекта."""
    if registration is None or not getattr(registration, "pk", None):
        return ""
    if getattr(registration, "stage_project_id", None):
        parent = getattr(registration, "stage_project", None)
        uid = (getattr(parent, "short_uid", "") or "").strip()
        return uid or str(registration.stage_project_id)
    return (getattr(registration, "short_uid", "") or "").strip() or str(registration.pk)


def _registration_form_page_url(action, registration, group_number, group_label):
    if action == "create" or registration is None or not getattr(registration, "pk", None):
        return reverse("registration_form_create")
    if action == "group_edit":
        number = registration.number if group_number in ("", None) else group_number
        params = {"number": number, "group": group_label or ""}
        project_id = getattr(registration, "stage_project_id", None)
        if project_id:
            params["project"] = project_id
        return f"{reverse('registration_group_summary_edit')}?{urlencode(params)}"
    return reverse("registration_form_edit", args=[registration.pk])


def _registration_form_context(form, action, registration=None, ranked_products=None, **extra):
    catalog = _registration_product_catalog()
    if ranked_products is None:
        ranked_products = _registration_selected_type_rows(form, registration)
    context = {
        "form": form,
        "action": action,
        "registration": registration,
        "allow_multiple_products": getattr(form, "allow_multiple_products", True),
        "product_options": catalog["options"],
        "registration_type_meta_json": json.dumps(catalog["meta"], ensure_ascii=False),
        "ranked_products": ranked_products,
        "group_number": "",
        "group_label": "",
        "group_source_ids": [],
        "single_contract_id": "",
    }
    # Поле «Договор ID» есть у проектов. Форма самого договора его не содержит.
    if action in {"create", "edit"} and "contract_project_registration" in form.fields:
        context["single_contract_id"] = _apply_single_registration_contract_fields(form, registration)
    context.update(extra)
    context["terms_project_key"] = _terms_project_storage_key(registration)
    if action in {"create", "edit"} and "contract_project_registration" in form.fields:
        context["registration_contract_meta_json"] = _registration_contract_meta_json(form)
    if "registration_stage_rows" not in context:
        context["registration_stage_rows"] = _display_registration_stage_rows(form, registration)
    customer_rows = _customer_rows_for_form(
        form,
        action,
        registration,
        context.get("customer_source_block"),
    )
    _include_customer_row_countries(form, customer_rows)
    context["customer_rows"] = customer_rows
    context["lock_customer_product"] = action == "edit" and bool(getattr(form, "lock_project_roles", False))
    owner_rows = _owner_rows_for_form(
        form,
        action,
        registration,
        context.get("customer_source_block"),
        customer_rows,
    )
    _include_owner_row_countries(form, owner_rows)
    context["owner_rows"] = owner_rows
    context["owner_matches_customer"] = _owner_matches_customer(form, registration)
    stage_rows = context.get("registration_stage_rows") or []
    from .stage_terms import evaluation_dates_are_common

    context["evaluation_date_common"] = evaluation_dates_are_common(stage_rows)
    context["evaluation_dates_disabled"] = bool(stage_rows) and all(
        not row.get("evaluation_date_enabled", True) for row in stage_rows
    )
    context["registration_stage_groups"] = _registration_stage_groups(
        form,
        stage_rows,
        registration,
    )
    context["header_current_label"] = _registration_form_page_label(action, registration)
    context["header_current_url"] = _registration_form_page_url(
        action,
        registration,
        context.get("group_number"),
        context.get("group_label") or "",
    )
    return context


def _display_registration_stage_rows(form, registration=None):
    from .stage_terms import _blank_stage, parse_posted_stages, stages_from_registration

    if getattr(form, "is_bound", False):
        posted = parse_posted_stages(form.data, getattr(form, "cleaned_type_ids", None))
        if posted:
            return posted
    if registration is not None and getattr(registration, "pk", None):
        return stages_from_registration(registration)
    return [_blank_stage()]


def _posted_contract_group_ends(data):
    from .stage_terms import parse_date

    contract_ids = _request_list(data, "contract_group_id")
    ends = _request_list(data, "contract_group_end")
    result = {}
    for index, contract_id in enumerate(contract_ids):
        raw_end = ends[index] if index < len(ends) else ""
        result[str(contract_id or "")] = parse_date(raw_end)
    return result


def _posted_contract_group_end_flags(data):
    if data is None or "contract_group_end_enabled" not in getattr(data, "keys", lambda: [])():
        return None
    contract_ids = _request_list(data, "contract_group_id")
    flags = _request_list(data, "contract_group_end_enabled")
    result = {}
    for index, contract_id in enumerate(contract_ids):
        raw = flags[index] if index < len(flags) else "true"
        result[str(contract_id or "")] = str(raw).strip().lower() not in {"0", "false", "off", "no", "нет"}
    return result


def _apply_posted_contract_end(target, contract_id, ends, flags):
    key = str(contract_id or "")
    if ends is not None:
        target.contract_end = ends.get(key)
    if flags is not None:
        target.contract_end_enabled = flags.get(key, True)


def _stamp_stage_contract_ids(form, rows, registration):
    stamped = [dict(row) for row in rows]
    posted_ids = None
    if getattr(form, "is_bound", False) and "stage_contract_id" in form.data:
        posted_ids = _request_list(form.data, "stage_contract_id")
    ends = {}
    flags = None
    if getattr(form, "is_bound", False) and "contract_group_id" in form.data:
        ends = _posted_contract_group_ends(form.data)
        flags = _posted_contract_group_end_flags(form.data)
    for index, row in enumerate(stamped):
        if posted_ids is not None:
            contract_id = posted_ids[index] if index < len(posted_ids) else ""
            row["contract_id"] = str(contract_id or "")
        elif not row.get("contract_id") and registration is not None:
            row["contract_id"] = str(getattr(registration, "contract_project_registration_id", "") or "")
            if not row.get("contract_end"):
                row["contract_end"] = getattr(registration, "contract_end", None)
            if "contract_end_enabled" not in row:
                row["contract_end_enabled"] = bool(getattr(registration, "contract_end_enabled", True))
        else:
            row["contract_id"] = str(row.get("contract_id") or "")
        if ends:
            row["contract_end"] = ends.get(row["contract_id"])
        if flags is not None:
            row["contract_end_enabled"] = flags.get(str(row.get("contract_id") or ""), True)
        elif "contract_end_enabled" not in row and registration is not None:
            row["contract_end_enabled"] = bool(getattr(registration, "contract_end_enabled", True))
    return stamped


def _registration_stage_groups(form, rows, registration):
    from .stage_terms import decorate_contract_term_groups, parse_date

    stamped = _stamp_stage_contract_ids(form, rows, registration)
    if getattr(form, "is_bound", False):
        project_start = parse_date(form.data.get("project_start_date"))
    else:
        project_start = parse_date((form.initial or {}).get("project_start_date"))
        if project_start is None and registration is not None:
            project_start = getattr(registration, "project_start_date", None)
    return decorate_contract_term_groups(stamped, _registration_contract_meta(form), project_start)


def _group_member_stage_rows(block):
    from .stage_terms import stages_from_registration

    rows = []
    for index, registration in enumerate(block, start=1):
        stages = stages_from_registration(registration)
        stage = dict(stages[0] if stages else {})
        stage["rank"] = index
        products = registration.ordered_products()
        if products:
            stage["product_id"] = str(products[0].pk)
        stage["contract_id"] = str(registration.contract_project_registration_id or "")
        stage["contract_end"] = registration.contract_end
        stage["contract_end_enabled"] = bool(getattr(registration, "contract_end_enabled", True))
        rows.append(stage)
    return rows


def _registration_weeks_text(value):
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return format(number.quantize(Decimal("0.1")), "f")


def _group_product_row(index, product, registration_id, stage1_weeks, stage2_weeks, contract_id=""):
    return {
        "rank": index,
        "consulting_type": (getattr(product, "consulting_type_display", "") or "").strip() if product else "",
        "service_category": (getattr(product, "service_category_display", "") or "").strip() if product else "",
        "service_subtype": (getattr(product, "service_subtype_display", "") or "").strip() if product else "",
        "product_id": str(product.pk) if product is not None else "",
        "product_group_id": "",
        "registration_row_id": registration_id or "",
        "contract_id": str(contract_id or ""),
        "stage1_weeks": _registration_weeks_text(stage1_weeks),
        "stage2_weeks": _registration_weeks_text(stage2_weeks),
    }


def _group_edit_ranked_products(block):
    rows = []
    for index, registration in enumerate(block, start=1):
        products = registration.ordered_products()
        product = products[0] if products else None
        rows.append(_group_product_row(
            index,
            product,
            registration.pk,
            registration.stage1_weeks,
            registration.stage2_weeks,
            registration.contract_project_registration_id,
        ))
    return rows


def _group_edit_ranked_products_from_data(data):
    consulting_types = _request_list(data, "type_consulting")
    service_categories = _request_list(data, "type_service_category")
    service_subtypes = _request_list(data, "type_service_subtype")
    product_ids = _request_list(data, "type_id")
    group_ids = _request_list(data, "row_group_id")
    row_ids = _request_list(data, "registration_row_id")
    stage1_values = _request_list(data, "stage1_weeks")
    stage2_values = _request_list(data, "stage2_weeks")
    row_count = max(len(product_ids), len(row_ids), len(consulting_types), 1)
    rows = []
    for index in range(row_count):
        product_id = product_ids[index] if index < len(product_ids) else ""
        row_id = row_ids[index] if index < len(row_ids) else ""
        consulting_type = consulting_types[index] if index < len(consulting_types) else ""
        service_category = service_categories[index] if index < len(service_categories) else ""
        service_subtype = service_subtypes[index] if index < len(service_subtypes) else ""
        has_data = any((consulting_type, service_category, service_subtype, product_id, row_id))
        if not has_data and row_count != 1:
            continue
        product = None
        if product_id:
            product = Product.objects.filter(pk=product_id).first()
        rows.append({
            "rank": len(rows) + 1,
            "consulting_type": consulting_type or ((product.consulting_type_display or "").strip() if product else ""),
            "service_category": service_category or ((product.service_category_display or "").strip() if product else ""),
            "service_subtype": service_subtype or ((product.service_subtype_display or "").strip() if product else ""),
            "product_id": product_id,
            "product_group_id": group_ids[index] if index < len(group_ids) else "",
            "registration_row_id": row_id,
            "stage1_weeks": stage1_values[index] if index < len(stage1_values) else "",
            "stage2_weeks": stage2_values[index] if index < len(stage2_values) else "",
        })
    return rows or [_group_product_row(1, None, "", "", "")]


def _group_source_ids(data):
    source_ids = []
    for raw in _request_list(data, "group_source_id"):
        if not raw:
            continue
        try:
            source_ids.append(int(raw))
        except ValueError:
            continue
    return source_ids


def _registration_group_edit_target(request):
    raw_project = (request.GET.get("project") or request.POST.get("project") or "").strip()
    if raw_project:
        try:
            project_id = int(raw_project)
        except ValueError:
            return None, "", None
        block, group_label = summary_block_for_project(project_id)
        if not block:
            return None, group_label, None
        return block, group_label, block[0].number
    raw_number = (request.GET.get("number") or "").strip()
    group_label = (request.GET.get("group") or "").strip()
    try:
        number = int(raw_number)
    except ValueError:
        return None, group_label, None
    return summary_block_for_group(number, group_label), group_label, number


def _registration_group_edit_specs(data, valid_product_ids):
    raw_products = _request_list(data, "type_id")
    raw_row_ids = _request_list(data, "registration_row_id")
    count = max(len(raw_products), len(raw_row_ids))
    specs = []
    seen_ids = set()
    valid_ids = set(valid_product_ids)
    for index in range(count):
        raw_product = raw_products[index] if index < len(raw_products) else ""
        raw_row_id = raw_row_ids[index] if index < len(raw_row_ids) else ""
        if not raw_product and not raw_row_id:
            continue
        if not raw_product:
            return None, "Укажите продукт для каждой строки группы."
        try:
            product_id = int(raw_product)
        except ValueError:
            return None, "Укажите продукт для каждой строки группы."
        if product_id not in valid_ids:
            return None, "Укажите продукт для каждой строки группы."
        registration_id = None
        if raw_row_id:
            try:
                registration_id = int(raw_row_id)
            except ValueError:
                return None, "Некорректная строка группы."
            if registration_id in seen_ids:
                return None, "Строка группы повторяется."
            seen_ids.add(registration_id)
        specs.append({
            "product_id": product_id,
            "registration_id": registration_id,
            "stage_index": index,
            "stage1_weeks": _request_decimal_at(data, "stage1_weeks", index),
            "stage2_weeks": _request_decimal_at(data, "stage2_weeks", index),
        })
    if not specs:
        return None, "Укажите хотя бы один продукт."
    return specs, None


REGISTRATION_GROUP_SHARED_FIELDS = [
    "number",
    "group_member",
    "name",
    "status",
    "deadline",
    "year",
    "country",
    "customer",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "project_manager",
    "project_manager_prs_id",
    "project_coordinator",
    "project_coordinator_prs_id",
    "asset_owner",
    "asset_owner_matches_customer",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
    "project_start_date",
    "stage3_weeks",
]


REGISTRATION_GROUP_STAGE_EXCLUDE = frozenset({"status", "deadline"})
STAGE_TO_PARENT_ROLE_EXCLUDE = frozenset({
    "project_manager",
    "project_manager_prs_id",
    "project_coordinator",
    "project_coordinator_prs_id",
})


def _apply_shared_registration_fields(target, source, *, include_contract_subject=False, exclude=()):
    skipped = set(exclude)
    for field_name in REGISTRATION_GROUP_SHARED_FIELDS:
        if field_name in skipped:
            continue
        setattr(target, field_name, getattr(source, field_name))
    if include_contract_subject:
        target.contract_subject = source.contract_subject


REGISTRATION_GROUP_UPDATE_FIELDS = REGISTRATION_GROUP_SHARED_FIELDS + [
    "group",
    "contract_project_registration",
    "agreement_type",
    "agreement_number",
    "contract_start",
    "contract_end",
    "contract_end_enabled",
    "evaluation_date",
    "input_data",
    "stage1_weeks",
    "stage2_weeks",
    "stage1_end",
    "stage2_end",
    "term_weeks",
    "completion_calc",
    "stage_terms_json",
    "position",
]


def _prepare_registration_group_row(target):
    member = target._resolved_group_member()
    if member:
        target.group = member.country_alpha2 or target.group
    if (
        not target.agreement_number
        and target.group_alpha2 == "RU"
        and target.agreement_type == ProjectRegistration.AgreementType.MAIN
    ):
        target.agreement_number = f"IMCM/{target.number}"
    if target.stage_terms_json:
        target.term_weeks = target._calculate_term_weeks()
        target.completion_calc = target.stage2_end
    else:
        target.stage1_end = target._calculate_stage1_end()
        target.stage2_end = target._calculate_stage2_end()
        target.term_weeks = target._calculate_term_weeks()
        target.completion_calc = target._calculate_completion_calc()


def _persist_registration_group_row(target, *, is_new):
    _prepare_registration_group_row(target)
    if is_new:
        target.save()
        return
    # Позиция и номер меняют Проект ID. save() записывает новый код сразу и
    # сталкивается с кодом соседней строки. Поля пишем напрямую, коды
    # пересчитывает один общий refresh_number_sequences.
    values = {
        field_name: getattr(target, field_name)
        for field_name in REGISTRATION_GROUP_UPDATE_FIELDS
    }
    ProjectRegistration.objects.filter(pk=target.pk).update(**values)


def _shift_registrations_after_group(block, extra_slots):
    if extra_slots <= 0 or not block:
        return
    last = block[-1]
    block_ids = [item.pk for item in block]
    later = list(
        ProjectRegistration.objects.exclude(pk__in=block_ids)
        .filter(Q(position__gt=last.position) | Q(position=last.position, pk__gt=last.pk))
        .order_by("position", "id")
    )
    cursor = block[0].position + len(block) + extra_slots
    changed = []
    for row in later:
        if row.position < cursor:
            row.position = cursor
            changed.append(row)
            cursor += 1
        else:
            cursor = row.position + 1
    if changed:
        ProjectRegistration.objects.bulk_update(changed, ["position"])


def _contracts_by_pk(contract_ids):
    parsed = []
    for raw in contract_ids:
        try:
            parsed.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return {}
    return {
        str(item.pk): item
        for item in ContractProjectRegistration.objects.filter(pk__in=set(parsed))
    }


def _assign_stage_contract(target, contract_id, contracts_by_pk):
    contract = contracts_by_pk.get(str(contract_id or ""))
    if contract is None:
        target.contract_project_registration = None
        target.agreement_type = ProjectRegistration.AgreementType.MAIN
        target.agreement_number = ""
        target.contract_start = None
        return
    target.contract_project_registration = contract
    target.agreement_type = contract.agreement_type or ProjectRegistration.AgreementType.MAIN
    target.agreement_number = contract.agreement_number or ""
    target.contract_start = contract.contract_date


def _stage_contract_id_for_spec(spec, posted_contract_ids, existing_by_pk):
    if posted_contract_ids is not None:
        index = spec["stage_index"]
        return str(posted_contract_ids[index] if index < len(posted_contract_ids) else "")
    registration_id = spec.get("registration_id")
    if registration_id:
        return str(existing_by_pk.get(registration_id) or "")
    return ""


def _save_registration_group_edit(request, form, block, specs, source_ids):
    from .stage_terms import (
        compute_grouped_stage_chains,
        parse_posted_stages,
        store_stage_snapshot,
    )

    if len(specs) > 9:
        return "В одном проекте не больше девяти этапов."
    base = form.save(commit=False)
    customer_rows = _customer_rows_from_post(request.POST)
    customer_countries = _customer_country_map(customer_rows)
    owner_rows = _owner_rows_from_post(request.POST)
    owner_countries = _customer_country_map(owner_rows)
    parent = block[0].stage_project if block and block[0].stage_project_id else None
    posted_stages = parse_posted_stages(request.POST) or []
    posted_contract_ids = (
        _request_list(request.POST, "stage_contract_id")
        if "stage_contract_id" in request.POST
        else None
    )
    contract_ends = (
        _posted_contract_group_ends(request.POST)
        if "contract_group_id" in request.POST
        else None
    )
    contract_end_flags = (
        _posted_contract_group_end_flags(request.POST)
        if contract_ends is not None
        else None
    )
    existing_contract_ids = {
        item.pk: item.contract_project_registration_id
        for item in block
    }
    chain_contract_ids = [
        _stage_contract_id_for_spec(spec, posted_contract_ids, existing_contract_ids)
        for spec in specs
    ]
    chain_input = []
    for spec in specs:
        index = spec["stage_index"]
        if index < len(posted_stages):
            stage = dict(posted_stages[index])
            stage["product_id"] = spec["product_id"]
            chain_input.append(stage)
        else:
            chain_input.append(
                {
                    "product_id": spec["product_id"],
                    "source_data_term": "0",
                    "source_data_term_unit": "days",
                    "service_term_months": spec["stage1_weeks"] if spec["stage1_weeks"] is not None else 0,
                    "preliminary_report_term_unit": "months",
                    "final_report_term_weeks": spec["stage2_weeks"] if spec["stage2_weeks"] is not None else 0,
                    "final_report_term_unit": "weeks",
                }
            )
    chain = compute_grouped_stage_chains(base.project_start_date, chain_input, chain_contract_ids)
    contracts_by_pk = _contracts_by_pk(chain_contract_ids)
    block_ids = [item.pk for item in block]
    posted_ids = {spec["registration_id"] for spec in specs if spec["registration_id"]}
    delete_ids = [pk for pk in source_ids if pk in set(block_ids) and pk not in posted_ids]
    with transaction.atomic():
        locked_rows = list(
            ProjectRegistration.objects.select_for_update()
            .filter(pk__in=block_ids)
            .order_by("position", "id")
        )
        if len(locked_rows) != len(set(block_ids)):
            transaction.set_rollback(True)
            return "Состав группы изменился. Обновите страницу и откройте группу снова."
        anchor_position = locked_rows[0].position
        _shift_registrations_after_group(locked_rows, len(specs) - len(locked_rows))
        locked = {item.pk: item for item in locked_rows}
        first_saved = None
        for index, spec in enumerate(specs):
            is_last = index == len(specs) - 1
            if spec["registration_id"]:
                target = locked.get(spec["registration_id"])
                if target is None:
                    transaction.set_rollback(True)
                    return "Строка не входит в эту группу."
                _apply_shared_registration_fields(
                    target,
                    base,
                    exclude=REGISTRATION_GROUP_STAGE_EXCLUDE,
                )
            else:
                target = ProjectRegistration()
                _apply_shared_registration_fields(
                    target,
                    base,
                    include_contract_subject=True,
                    exclude=REGISTRATION_GROUP_STAGE_EXCLUDE,
                )
                if parent is not None:
                    target.stage_project = parent
            if is_last:
                target.deadline = base.deadline
            if customer_rows:
                _write_customer_party(
                    target,
                    _customer_party_for_product(customer_rows, spec["product_id"]) or _blank_customer_party(),
                    customer_countries,
                )
            _apply_posted_owner_party(target, owner_rows, owner_countries, spec["product_id"])
            contract_id = chain_contract_ids[index] if index < len(chain_contract_ids) else ""
            if posted_contract_ids is not None or not spec["registration_id"]:
                _assign_stage_contract(target, contract_id, contracts_by_pk)
            if contract_ends is not None:
                _apply_posted_contract_end(target, contract_id, contract_ends, contract_end_flags)
            stage = chain[index] if index < len(chain) else None
            if stage is not None:
                store_stage_snapshot(target, stage, base.project_start_date)
            else:
                target.stage1_weeks = spec["stage1_weeks"] if spec["stage1_weeks"] is not None else 0
                target.stage2_weeks = spec["stage2_weeks"] if spec["stage2_weeks"] is not None else 0
            target.position = anchor_position + index
            if first_saved is None:
                first_saved = target
            _persist_registration_group_row(target, is_new=not spec["registration_id"])
            _save_ranked_registration_products(target, [spec["product_id"]])
            if spec["registration_id"]:
                for work_item in target.work_items.select_related("project").all():
                    _ensure_performer_rows_for_work_item(work_item)
        owner = parent
        if owner is None and locked_rows:
            owner = locked_rows[0].stage_project or locked_rows[0]
        if owner is not None and owner.pk:
            align_project_service_scope(owner)
        for pk in delete_ids:
            row = locked.get(pk)
            if row is not None:
                row.delete()
        if parent is not None:
            _apply_shared_registration_fields(
                parent,
                base,
                include_contract_subject=True,
                exclude=REGISTRATION_GROUP_STAGE_EXCLUDE,
            )
            if posted_contract_ids is not None and first_saved is not None:
                parent.contract_project_registration_id = first_saved.contract_project_registration_id
                parent.agreement_type = first_saved.agreement_type
                parent.agreement_number = first_saved.agreement_number
                parent.contract_start = first_saved.contract_start
                parent.contract_end = first_saved.contract_end
                parent.contract_end_enabled = first_saved.contract_end_enabled
            parent.deadline = base.deadline
            if customer_rows and specs:
                _write_customer_party(
                    parent,
                    _customer_party_for_product(customer_rows, specs[0]["product_id"]) or _blank_customer_party(),
                    customer_countries,
                )
            if specs:
                _apply_posted_owner_party(parent, owner_rows, owner_countries, specs[0]["product_id"])
            if not ProjectRegistration.objects.filter(stage_project=parent).exclude(pk__in=delete_ids).exists():
                parent.delete()
                parent = None
            else:
                parent.save()
        numbers = {item.number for item in locked_rows}
        numbers.add(base.number)
        ProjectRegistration.refresh_number_sequences(numbers)
    _sync_posted_customer_parties(request, customer_rows, base)
    _sync_posted_owner_parties(request, owner_rows, base)
    return None


def _save_ranked_registration_products(registration, product_ids):
    normalized_ids = []
    seen = set()
    for raw_id in product_ids:
        try:
            product_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if product_id in seen:
            continue
        seen.add(product_id)
        normalized_ids.append(product_id)

    ProjectRegistrationProduct.objects.filter(registration=registration).delete()
    if normalized_ids:
        ProjectRegistrationProduct.objects.bulk_create(
            [
                ProjectRegistrationProduct(
                    registration=registration,
                    product_id=product_id,
                    rank=rank,
                )
                for rank, product_id in enumerate(normalized_ids, start=1)
            ]
        )
    _sync_project_registration_primary_product(registration.pk)


REGISTRATION_CLONE_FIELDS = [
    "number",
    "contract_project_registration",
    "group_member",
    "agreement_type",
    "agreement_number",
    "name",
    "status",
    "deadline",
    "year",
    "country",
    "customer",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "asset_owner",
    "asset_owner_matches_customer",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
    "project_manager",
    "project_manager_prs_id",
    "contract_start",
    "contract_end",
    "project_start_date",
    "input_data",
    "stage1_weeks",
    "stage2_weeks",
    "contract_subject",
]


def _copy_registration_form_values(source):
    target = ProjectRegistration()
    for field_name in REGISTRATION_CLONE_FIELDS:
        setattr(target, field_name, getattr(source, field_name))
    return target


def _render_projects_updated(request):
    resp = render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))
    resp[HX_TRIGGER_HEADER] = HX_PROJECTS_UPDATED_EVENT
    return resp

def _next_position(model, filters: dict | None = None) -> int:
    qs = model.objects
    if filters:
        qs = qs.filter(**filters)
    last = qs.aggregate(mx=Max("position")).get("mx") or 0
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
    """Create or update autocomplete registry chain from project data."""
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


def _sync_selection_kwargs(request, prefix):
    selected_flag = str(request.POST.get(f"{prefix}_selected_from_autocomplete") or "").strip().lower()
    return {
        "selected_identifier_record_id": (request.POST.get(f"{prefix}_identifier_record_id") or "").strip(),
        "selected_from_autocomplete": selected_flag in {"1", "true", "yes", "on"},
    }


@login_required
@require_http_methods(["GET"])
def projects_partial(request):
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))

# --- Регистрация проекта ---

REGISTRATION_CSV_ADMIN_ERROR = (
    "Загрузка и скачивание CSV доступны только пользователям с ролью Администратор."
)
REGISTRATION_CSV_HEADERS = [
    "Номер",
    "Договор ID",
    "Вид соглашения",
    "Группа",
    "Проект ID",
    "Тип",
    "Название",
    "Год",
    "Дата оценки",
    "Дедлайн",
    "Руководитель проекта",
    "Координатор проекта",
    "Статус",
    "Дата статуса",
    "Заказчик: наименование",
    "Заказчик: страна",
    "Заказчик: идент.",
    "Заказчик: регистр. номер",
    "Заказчик: регион",
    "Заказчик: дата регистр.",
    "Владелец: наименование",
    "Владелец: страна",
    "Владелец: идент.",
    "Владелец: регистр. номер",
    "Владелец: регион",
    "Владелец: дата регистр.",
]
REGISTRATION_CSV_TOGGLE_COLUMNS = (
    ("Оконч. договора вкл.", "contract_end_enabled"),
    ("Исходные данные вкл.", "source_data_term_enabled"),
    ("Исходные данные (дата) вкл.", "source_data_date_enabled"),
    ("Предварительный отчёт вкл.", "service_term_months_enabled"),
    ("Предварительный отчёт (дата) вкл.", "preliminary_report_date_enabled"),
    ("Итоговый отчёт (дата) вкл.", "final_report_date_enabled"),
    ("Дата оценки вкл.", "evaluation_date_enabled"),
    ("Общая для всех этапов", "evaluation_date_common"),
)
REGISTRATION_CSV_HEADERS.extend(label for label, _field in REGISTRATION_CSV_TOGGLE_COLUMNS)
REGISTRATION_CSV_STAGE_TOGGLE_FIELDS = tuple(
    field for _label, field in REGISTRATION_CSV_TOGGLE_COLUMNS
    if field not in {"contract_end_enabled", "evaluation_date_common"}
)
REGISTRATION_CSV_OPTIONAL_HEADERS = {label for label, _field in REGISTRATION_CSV_TOGGLE_COLUMNS}
REGISTRATION_CSV_REQUIRED_HEADERS = {
    "Номер",
    "Вид соглашения",
    "Группа",
    "Тип",
    "Название",
    "Статус",
}


def _registration_csv_header_label(name):
    if name in REGISTRATION_CSV_REQUIRED_HEADERS:
        return f"{name}*"
    return name


def _registration_csv_header_key(name):
    text = str(name or "").strip()
    if text.endswith("*"):
        text = text[:-1].strip()
    return text


def _registration_csv_forbidden():
    return JsonResponse({"ok": False, "error": REGISTRATION_CSV_ADMIN_ERROR}, status=403)


def _registration_csv_queryset(request):
    product_prefetch = models.Prefetch(
        "product_links",
        queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    queryset = (
        ProjectRegistration.objects
        .select_related(
            "country",
            "asset_owner_country",
            "group_member",
            "type",
            "contract_project_registration",
        )
        .prefetch_related(
            product_prefetch,
            models.Prefetch(
                "stages",
                queryset=ProjectRegistration.objects.only(
                    "id", "stage_project_id", "status", "stage_terms_json", "evaluation_date",
                ).order_by("position", "id"),
            ),
        )
        .order_by("position", "id")
    )
    raw = request.GET.get("project")
    if raw is None:
        return queryset
    raw = raw.strip()
    if raw in {"", "__all__"}:
        return queryset
    ids = [int(part) for part in raw.split(",") if part.strip().isdigit()]
    return queryset.filter(pk__in=ids)


def _registration_csv_date(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _registration_csv_bool(value):
    return "да" if value else "нет"


def _registration_csv_stage_rows(registration):
    if registration is None or not getattr(registration, "pk", None):
        return []
    prefetched = getattr(registration, "_prefetched_objects_cache", {}).get("stages")
    if prefetched is not None:
        return list(prefetched)
    return list(
        registration.stages.only("id", "stage_project_id", "status").order_by("position", "id")
    )


def _registration_csv_is_project_shell(registration):
    if registration is None or not getattr(registration, "pk", None) or registration.stage_project_id:
        return False
    return bool(_registration_csv_stage_rows(registration))


def _registration_csv_summary_status_label(registration):
    from .registration_summary import registration_summary_state

    stages = _registration_csv_stage_rows(registration)
    return registration_summary_state(
        [stage.status for stage in stages],
        getattr(registration, "summary_deferred", False),
    )["label"]


def _registration_csv_status_date_cell(registration):
    if _registration_csv_is_project_shell(registration):
        if _registration_csv_summary_status_label(registration) == "Не начат":
            return ""
        return _registration_csv_date(registration.summary_status_date)
    if registration.status == "Не начат":
        return ""
    return _registration_csv_date(registration.status_date)


def _registration_csv_toggle_stage(registration):
    from .stage_terms import stages_from_registration

    stages = stages_from_registration(registration)
    return stages[0] if stages else {}


def _registration_csv_project_members(registration):
    if registration is None or not getattr(registration, "pk", None):
        return []
    if getattr(registration, "stage_project_id", None):
        return list(
            ProjectRegistration.objects.filter(stage_project_id=registration.stage_project_id)
            .order_by("position", "id")
        )
    if _registration_csv_is_project_shell(registration):
        return _registration_csv_stage_rows(registration)
    return [registration]


def _registration_csv_common_evaluation_enabled(registration):
    from .stage_terms import enabled_flag, evaluation_dates_are_common, stages_from_registration

    snapshots = []
    for member in _registration_csv_project_members(registration):
        stages = stages_from_registration(member)
        if stages:
            snapshots.append(stages[0])
    if len(snapshots) <= 1:
        stage = snapshots[0] if snapshots else {}
        if "evaluation_date_common" in stage:
            return enabled_flag(stage.get("evaluation_date_common"), True)
        return True
    return evaluation_dates_are_common(snapshots)


def _registration_csv_toggle_cells(registration):
    shell = _registration_csv_is_project_shell(registration)
    stage = {} if shell else _registration_csv_toggle_stage(registration)
    cells = []
    for _label, field in REGISTRATION_CSV_TOGGLE_COLUMNS:
        if field == "contract_end_enabled":
            cells.append(_registration_csv_bool(registration.contract_end_enabled))
        elif field == "evaluation_date_common":
            cells.append(_registration_csv_bool(_registration_csv_common_evaluation_enabled(registration)))
        elif shell:
            cells.append("")
        else:
            cells.append(_registration_csv_bool(stage.get(field)))
    return cells


def _registration_csv_toggle_value(raw):
    text = " ".join(str(raw or "").split()).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "да", "вкл", "on"}:
        return True
    if text in {"0", "false", "no", "n", "нет", "выкл", "off"}:
        return False
    return "invalid"


def _registration_csv_toggles(row, indexes):
    toggles = {}
    for label, field in REGISTRATION_CSV_TOGGLE_COLUMNS:
        if label not in indexes:
            continue
        raw = _registration_csv_cell(row, indexes, label)
        value = _registration_csv_toggle_value(raw)
        if value == "invalid":
            return None, f"некорректное значение «{raw}» в столбце «{label}»."
        if value is not None:
            toggles[field] = value
    return toggles, None


def _registration_csv_row(registration):
    return [
        f"{int(registration.number or 0):04d}",
        (
            registration.contract_project_registration.short_uid
            if registration.contract_project_registration_id
            else ""
        ),
        registration.get_agreement_type_display(),
        registration.group_display,
        registration.short_uid,
        registration.type_short_display,
        registration.name,
        "" if registration.year is None else str(registration.year),
        _registration_csv_date(registration.evaluation_date),
        _registration_csv_date(registration.deadline),
        registration.project_manager,
        registration.project_coordinator,
        registration.status,
        _registration_csv_status_date_cell(registration),
        registration.customer,
        registration.country.short_name if registration.country_id else "",
        registration.identifier,
        registration.registration_number,
        registration.registration_region,
        _registration_csv_date(registration.registration_date),
        registration.asset_owner,
        registration.asset_owner_country.short_name if registration.asset_owner_country_id else "",
        registration.asset_owner_identifier,
        registration.asset_owner_registration_number,
        registration.asset_owner_region,
        _registration_csv_date(registration.asset_owner_registration_date),
        *_registration_csv_toggle_cells(registration),
    ]


def _registration_csv_form_error_text(form) -> str:
    parts = []
    for field, errors in form.errors.items():
        if field == "__all__":
            prefix = ""
        elif field == "type_ids":
            prefix = "Тип: "
        else:
            bound = form.fields.get(field)
            prefix = f"{bound.label}: " if bound and bound.label else f"{field}: "
        for err in errors:
            parts.append(f"{prefix}{err}")
    return "; ".join(parts)


def _registration_csv_label_index(items, label_getter):
    found = {}
    ambiguous = set()
    for item in items:
        label = " ".join(str(label_getter(item) or "").split()).strip()
        if not label:
            continue
        key = label.casefold()
        if key in ambiguous:
            continue
        if key in found:
            ambiguous.add(key)
            found.pop(key, None)
            continue
        found[key] = item
    return found, ambiguous


def _registration_csv_active_countries():
    today = timezone.now().date()
    return OKSMCountry.objects.filter(
        models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
    )


def _read_registration_csv_upload(csv_file):
    if not csv_file:
        return None, JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return None, JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)
    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return None, JsonResponse(
                {
                    "ok": False,
                    "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251).",
                },
                status=400,
            )
    try:
        rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
        if not rows:
            return None, JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            rows = list(csv.reader(io.StringIO(raw), delimiter=","))
    except csv.Error as exc:
        return None, JsonResponse(
            {"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."},
            status=400,
        )
    if len(rows) < 2:
        return None, JsonResponse(
            {"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."},
            status=400,
        )
    return rows, None


def _registration_csv_cell(row, indexes, name):
    index = indexes[name]
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _registration_csv_number(raw):
    text = "".join(str(raw or "").split())
    if not text:
        return None, "не заполнено обязательное поле «Номер»."
    if not text.isdigit() or int(text) > 9999:
        return None, "некорректный номер."
    return int(text), None


def _registration_csv_year(raw):
    text = "".join(str(raw or "").split())
    if not text:
        return "", None
    if not text.isdigit() or len(text) > 9:
        return None, "некорректный год."
    return text, None


def _registration_csv_optional_date(raw, label):
    text = str(raw or "").strip()
    if not text:
        return "", None, None
    parsed = _parse_project_form_date(text)
    if parsed is None:
        return None, None, f"некорректная дата в столбце «{label}»."
    return parsed.strftime("%d.%m.%Y"), parsed, None


def _registration_csv_agreement_type(raw):
    key = " ".join(str(raw or "").split()).strip().casefold()
    if not key:
        return None
    for value, label in ProjectRegistration.AgreementType.choices:
        if key in {value.casefold(), label.casefold()}:
            return value
    return None


def _registration_csv_status(raw):
    key = " ".join(str(raw or "").split()).strip().casefold()
    if not key:
        return None
    for value, label in ProjectRegistration.STATUS_CHOICES:
        if key in {value.casefold(), str(label).casefold()}:
            return value
    return None


def _registration_csv_products(raw, products_by_key, ambiguous_products):
    text = " ".join(str(raw or "").split()).strip()
    if not text:
        return None, "не заполнено обязательное поле «Тип»."
    key = text.casefold()
    if key in ambiguous_products:
        return None, f"неоднозначный тип «{text}»."
    product = products_by_key.get(key)
    if product is not None:
        return [product], None
    parts = [part.strip() for part in text.split("-") if part.strip()]
    if len(parts) <= 1:
        return None, f"неизвестный тип «{text}»."
    resolved = []
    seen = set()
    for part in parts:
        part_key = part.casefold()
        if part_key in ambiguous_products or part_key not in products_by_key:
            return None, f"неизвестный тип «{text}»."
        product = products_by_key[part_key]
        if product.pk in seen:
            continue
        seen.add(product.pk)
        resolved.append(product)
    if not resolved:
        return None, f"неизвестный тип «{text}»."
    return resolved, None


def _registration_csv_named_choice(raw, choices, ambiguous, *, empty_message, ambiguous_message, unknown_message):
    text = " ".join(str(raw or "").split()).strip()
    if not text:
        if empty_message:
            return None, empty_message
        return None, None
    key = text.casefold()
    if key in ambiguous:
        return None, ambiguous_message.format(value=text)
    choice = choices.get(key)
    if choice is None:
        return None, unknown_message.format(value=text)
    return choice, None


def _registration_csv_country(raw, countries, ambiguous, current=None):
    text = " ".join(str(raw or "").split()).strip()
    if not text:
        return None, None
    key = text.casefold()
    if current is not None:
        current_name = " ".join(str(getattr(current, "short_name", "") or "").split()).strip().casefold()
        if current_name and current_name == key:
            return current, None
    if key in ambiguous:
        return None, f"неоднозначная страна «{text}»."
    country = countries.get(key)
    if country is None:
        return None, f"неизвестная страна «{text}»."
    return country, None


def _registration_csv_person_value(raw, *, stored_name="", stored_prs="", resolver):
    text = " ".join(str(raw or "").split()).strip()
    resolved = resolver(text)
    prs_id = resolved[1]
    if prs_id:
        return prs_id
    stored_name = " ".join(str(stored_name or "").split()).strip()
    stored_prs = " ".join(str(stored_prs or "").split()).strip()
    if text and stored_prs and text.casefold() in {stored_name.casefold(), stored_prs.casefold()}:
        return stored_prs
    return resolved[0]


def _registration_csv_preserved_fields(instance):
    if instance is None:
        return {
            "agreement_number": "",
            "contract_start": "",
            "contract_end": "",
            "input_data": "0",
            "stage1_weeks": "0",
            "stage2_weeks": "0",
            "stage2_end": "",
            "stage3_weeks": "0",
        }
    return {
        "agreement_number": instance.agreement_number or "",
        "contract_start": _registration_csv_date(instance.contract_start),
        "contract_end": _registration_csv_date(instance.contract_end),
        "input_data": "" if instance.input_data is None else str(instance.input_data),
        "stage1_weeks": "" if instance.stage1_weeks is None else str(instance.stage1_weeks),
        "stage2_weeks": "" if instance.stage2_weeks is None else str(instance.stage2_weeks),
        "stage2_end": _registration_csv_date(instance.stage2_end),
        "stage3_weeks": "" if instance.stage3_weeks is None else str(instance.stage3_weeks),
    }


def _registration_parties_match(
    customer, country, identifier, registration_number, region, registration_date,
    asset_owner, asset_owner_country, asset_owner_identifier, asset_owner_number, asset_owner_region, asset_owner_date,
):
    def norm(value):
        return " ".join(str(value or "").split()).casefold()

    return (
        norm(customer) == norm(asset_owner)
        and getattr(country, "pk", None) == getattr(asset_owner_country, "pk", None)
        and norm(identifier) == norm(asset_owner_identifier)
        and norm(registration_number) == norm(asset_owner_number)
        and norm(region) == norm(asset_owner_region)
        and registration_date == asset_owner_date
    )


def _registration_csv_form_data(instance, values):
    preserved = _registration_csv_preserved_fields(instance)
    data = QueryDict(mutable=True)
    data["number"] = str(values["number"])
    data["contract_project_registration"] = str(values["contract"].pk) if values["contract"] else ""
    data["group_member"] = str(values["group_member"].pk)
    data["agreement_type"] = values["agreement_type"]
    data["agreement_number"] = preserved["agreement_number"]
    data["name"] = values["name"]
    data["status"] = values["status"]
    data["deadline"] = values["deadline"]
    data["year"] = values["year"]
    data["evaluation_date"] = values["evaluation_date"]
    data["country"] = str(values["country"].pk) if values["country"] else ""
    data["customer"] = values["customer"]
    data["identifier"] = values["identifier"]
    data["registration_number"] = values["registration_number"]
    data["registration_region"] = values["registration_region"]
    data["registration_date"] = values["registration_date"]
    data["project_manager"] = values["project_manager"]
    data["project_coordinator"] = values["project_coordinator"]
    data["asset_owner"] = values["asset_owner"]
    data["asset_owner_country"] = str(values["asset_owner_country"].pk) if values["asset_owner_country"] else ""
    data["asset_owner_identifier"] = values["asset_owner_identifier"]
    data["asset_owner_registration_number"] = values["asset_owner_registration_number"]
    data["asset_owner_region"] = values["asset_owner_region"]
    data["asset_owner_registration_date"] = values["asset_owner_registration_date"]
    data["contract_start"] = preserved["contract_start"]
    data["contract_end"] = preserved["contract_end"]
    data["input_data"] = preserved["input_data"]
    data["stage1_weeks"] = preserved["stage1_weeks"]
    data["stage2_weeks"] = preserved["stage2_weeks"]
    data["stage2_end"] = preserved["stage2_end"]
    data["stage3_weeks"] = preserved["stage3_weeks"]
    if values["matches_customer"]:
        data["asset_owner_matches_customer"] = "on"
    data.setlist("type_id", [str(product.pk) for product in values["products"]])
    return data


def _apply_registration_csv_status_date(obj, previous_status, status_date_value):
    if _registration_csv_is_project_shell(obj):
        # Пустая ячейка у группы «Не начат» не стирает сохранённую дату: в файле её нет,
        # потому что реестр такую дату не показывает.
        if status_date_value is None and _registration_csv_summary_status_label(obj) == "Не начат":
            return
        if obj.summary_status_date != status_date_value:
            obj.summary_status_date = status_date_value
            obj.save(update_fields=["summary_status_date"])
        return
    if obj.status == "Не начат":
        target = None
    elif status_date_value is not None:
        target = status_date_value
    elif previous_status != obj.status:
        target = obj.status_date
    else:
        target = None
    if obj.status_date != target:
        obj.status_date = target
        obj.save(update_fields=["status_date"])


def _registration_csv_store_common_evaluation(registration, enabled):
    from .stage_terms import apply_stages_to_registration, legacy_stage_from_registration

    enabled = bool(enabled)
    stored = [dict(item) for item in (registration.stage_terms_json or []) if isinstance(item, dict)]
    if stored:
        stages = stored
        changed = False
    else:
        stages = [legacy_stage_from_registration(registration)]
        changed = True
    for stage in stages:
        if "evaluation_date_common" not in stage or bool(stage.get("evaluation_date_common")) != enabled:
            changed = True
        stage["evaluation_date_common"] = enabled
    if not changed:
        return
    if stored:
        registration.stage_terms_json = stages
        registration.save(update_fields=["stage_terms_json"])
        return
    apply_stages_to_registration(registration, stages, registration.project_start_date)
    registration.save(update_fields=[
        "stage_terms_json",
        "project_start_date",
        "input_data",
        "stage1_weeks",
        "stage2_weeks",
        "stage1_end",
        "stage2_end",
        "evaluation_date",
        "completion_calc",
    ])


def _registration_csv_share_common_evaluation_dates(registrations):
    """Включённый общий чекбокс копирует дату оценки первого этапа на остальные."""
    from .stage_terms import (
        apply_stages_to_registration,
        evaluation_dates_are_common,
        stages_from_registration,
    )

    seen = set()
    for registration in registrations:
        if getattr(registration, "stage_project_id", None):
            parent_id = registration.stage_project_id
        elif _registration_csv_is_project_shell(registration):
            parent_id = registration.pk
        else:
            continue
        if parent_id in seen:
            continue
        seen.add(parent_id)
        members = list(
            ProjectRegistration.objects.filter(stage_project_id=parent_id).order_by("position", "id")
        )
        if len(members) < 2:
            continue
        snapshots = []
        for member in members:
            stages = stages_from_registration(member)
            snapshots.append(dict(stages[0]) if stages else {})
        if not evaluation_dates_are_common(snapshots):
            continue
        shared_date = snapshots[0].get("evaluation_date") or ""
        shared_enabled = bool(snapshots[0].get("evaluation_date_enabled", True))
        for member, snapshot in zip(members[1:], snapshots[1:]):
            if (
                (snapshot.get("evaluation_date") or "") == shared_date
                and bool(snapshot.get("evaluation_date_enabled", True)) == shared_enabled
            ):
                continue
            stored = [dict(item) for item in (member.stage_terms_json or []) if isinstance(item, dict)]
            stages = stored or [snapshot]
            for stage in stages:
                stage["evaluation_date"] = shared_date
                stage["evaluation_date_enabled"] = shared_enabled
                stage["evaluation_date_common"] = True
            apply_stages_to_registration(member, stages, member.project_start_date)
            member.save(update_fields=[
                "stage_terms_json",
                "project_start_date",
                "input_data",
                "stage1_weeks",
                "stage2_weeks",
                "stage1_end",
                "stage2_end",
                "evaluation_date",
                "completion_calc",
            ])


def _apply_registration_csv_toggles(obj, toggles, evaluation_date):
    """Записывает переключатели сроков из CSV, не трогая свёрнутые столбцы."""
    from .stage_terms import (
        _blank_stage,
        apply_stages_to_registration,
        format_date,
        legacy_stage_from_registration,
        parse_date,
    )

    if "contract_end_enabled" in toggles:
        obj.contract_end_enabled = bool(toggles["contract_end_enabled"])
    stage_updates = {
        field: toggles[field]
        for field in REGISTRATION_CSV_STAGE_TOGGLE_FIELDS
        if field in toggles
    }
    if "evaluation_date_common" in toggles:
        stage_updates["evaluation_date_common"] = bool(toggles["evaluation_date_common"])
    if _registration_csv_is_project_shell(obj):
        if "evaluation_date_common" in toggles:
            for child in ProjectRegistration.objects.filter(stage_project_id=obj.pk).order_by("position", "id"):
                _registration_csv_store_common_evaluation(child, toggles["evaluation_date_common"])
        return
    stored = [dict(item) for item in (obj.stage_terms_json or []) if isinstance(item, dict)]
    if not stored and not stage_updates:
        return
    if stored:
        stages = stored
        other_changed = False
    else:
        stage = legacy_stage_from_registration(obj)
        blank = _blank_stage()
        for field in REGISTRATION_CSV_STAGE_TOGGLE_FIELDS:
            if field not in stage_updates:
                stage[field] = blank[field]
        stages = [stage]
        other_changed = True
    common_changed = False
    for stage in stages:
        for field, value in stage_updates.items():
            missing_common = field == "evaluation_date_common" and field not in stage
            field_changed = missing_common or bool(stage.get(field)) != bool(value)
            if field == "evaluation_date_common" and field_changed:
                common_changed = True
            elif field_changed:
                other_changed = True
            stage[field] = value
    target = stages[-1]
    parsed_evaluation = parse_date(evaluation_date)
    if target.get("evaluation_date_enabled", True):
        formatted_evaluation = format_date(parsed_evaluation)
    else:
        formatted_evaluation = ""
        parsed_evaluation = None
    if (target.get("evaluation_date") or "") != formatted_evaluation:
        target["evaluation_date"] = formatted_evaluation
        other_changed = True
    obj.evaluation_date = parsed_evaluation
    if other_changed:
        apply_stages_to_registration(obj, stages, obj.project_start_date)
    elif common_changed:
        obj.stage_terms_json = stages


def _save_registration_csv_row(request, instance, values):
    previous_status = instance.status if instance is not None else None
    preserved_terms = None
    if instance is not None:
        preserved_terms = {
            "project_start_date": instance.project_start_date,
            "input_data": instance.input_data,
            "stage1_weeks": instance.stage1_weeks,
            "stage2_weeks": instance.stage2_weeks,
            "stage1_end": instance.stage1_end,
            "stage2_end": instance.stage2_end,
            "completion_calc": instance.completion_calc,
            "stage_terms_json": copy.deepcopy(instance.stage_terms_json),
            "contract_end_enabled": instance.contract_end_enabled,
        }
    form = ProjectRegistrationForm(
        _registration_csv_form_data(instance, values),
        instance=instance,
        allow_multiple_products=True,
    )
    if not form.is_valid():
        raise forms.ValidationError(_registration_csv_form_error_text(form))
    with transaction.atomic():
        obj = form.save(commit=False)
        if preserved_terms is not None:
            for field_name, field_value in preserved_terms.items():
                setattr(obj, field_name, field_value)
        if instance is None:
            obj.position = _next_position(ProjectRegistration)
        _apply_registration_csv_toggles(obj, values.get("toggles") or {}, values.get("evaluation_date"))
        obj.save()
        _apply_registration_csv_status_date(obj, previous_status, values.get("status_date"))
        _save_ranked_registration_products(obj, getattr(form, "cleaned_type_ids", []))
        _sync_to_legal_entity_record(
            obj.customer, obj.country, obj.identifier,
            obj.registration_number, obj.registration_date, request.user,
            business_entity_source="[Проекты / Заказчик]",
            registration_region=obj.registration_region,
        )
        _sync_to_legal_entity_record(
            obj.asset_owner, obj.asset_owner_country, obj.asset_owner_identifier,
            obj.asset_owner_registration_number, obj.asset_owner_registration_date, request.user,
            business_entity_source="[Проекты / Владелец активов]",
            registration_region=obj.asset_owner_region,
        )
    return obj


@login_required
@require_http_methods(["GET"])
def registration_csv_download(request):
    if not _is_admin_user(request.user):
        return _registration_csv_forbidden()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow([_registration_csv_header_label(name) for name in REGISTRATION_CSV_HEADERS])
    for registration in _registration_csv_queryset(request):
        writer.writerow(_registration_csv_row(registration))
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="project_registrations.csv"'
    return response


@login_required
@require_POST
def registration_csv_upload(request):
    if not _is_admin_user(request.user):
        return _registration_csv_forbidden()
    rows, error_response = _read_registration_csv_upload(request.FILES.get("csv_file"))
    if error_response:
        return error_response
    header = [_registration_csv_header_key(cell) for cell in rows[0]]
    missing = [
        name for name in REGISTRATION_CSV_HEADERS
        if name not in header and name not in REGISTRATION_CSV_OPTIONAL_HEADERS
    ]
    if missing:
        return JsonResponse(
            {
                "ok": False,
                "error": "В файле нет столбцов: "
                + ", ".join(_registration_csv_header_label(name) for name in missing)
                + ".",
            },
            status=400,
        )
    indexes = {
        name: header.index(name)
        for name in REGISTRATION_CSV_HEADERS
        if name in header
    }
    products_by_key, ambiguous_products = _registration_csv_label_index(
        Product.objects.exclude(short_name=""),
        lambda product: product.short_name,
    )
    groups_by_key, ambiguous_groups = _registration_csv_label_index(
        GroupMember.objects.exclude(country_alpha2=""),
        lambda member: member.group_code_label,
    )
    contracts_by_key, ambiguous_contracts = _registration_csv_label_index(
        ContractProjectRegistration.objects.exclude(short_uid=""),
        lambda contract: contract.short_uid,
    )
    countries_by_key, ambiguous_countries = _registration_csv_label_index(
        _registration_csv_active_countries(),
        lambda country: country.short_name,
    )
    existing_by_uid = {}
    for registration in ProjectRegistration.objects.select_related("country", "asset_owner_country"):
        uid = (registration.short_uid or "").strip()
        if uid:
            existing_by_uid[uid.casefold()] = registration

    created = 0
    updated = 0
    warnings = []
    seen_ids = set()
    common_evaluation_rows = []
    for row_number, row in enumerate(rows[1:], start=2):
        if not any(str(cell or "").strip() for cell in row):
            continue
        project_id = _registration_csv_cell(row, indexes, "Проект ID")
        instance = None
        if project_id:
            uid_key = project_id.casefold()
            if uid_key in seen_ids:
                warnings.append(f"Строка {row_number}: Проект ID «{project_id}» повторяется в файле.")
                continue
            seen_ids.add(uid_key)
            instance = existing_by_uid.get(uid_key)
            if instance is None:
                warnings.append(f"Строка {row_number}: проект «{project_id}» не найден.")
                continue
            instance.refresh_from_db()

        problems = []
        number, number_error = _registration_csv_number(_registration_csv_cell(row, indexes, "Номер"))
        if number_error:
            problems.append(number_error)
        contract, contract_error = _registration_csv_named_choice(
            _registration_csv_cell(row, indexes, "Договор ID"),
            contracts_by_key,
            ambiguous_contracts,
            empty_message="",
            ambiguous_message="неоднозначный договор «{value}».",
            unknown_message="неизвестный договор «{value}».",
        )
        if contract_error:
            problems.append(contract_error)
        agreement_type = _registration_csv_agreement_type(_registration_csv_cell(row, indexes, "Вид соглашения"))
        if agreement_type is None:
            agreement_raw = _registration_csv_cell(row, indexes, "Вид соглашения")
            if agreement_raw:
                problems.append(f"неизвестный вид соглашения «{agreement_raw}».")
            else:
                problems.append("не заполнено обязательное поле «Вид соглашения».")
        group_member, group_error = _registration_csv_named_choice(
            _registration_csv_cell(row, indexes, "Группа"),
            groups_by_key,
            ambiguous_groups,
            empty_message="не заполнено обязательное поле «Группа».",
            ambiguous_message="неоднозначная группа «{value}».",
            unknown_message="неизвестная группа «{value}».",
        )
        if group_error:
            problems.append(group_error)
        products, product_error = _registration_csv_products(
            _registration_csv_cell(row, indexes, "Тип"),
            products_by_key,
            ambiguous_products,
        )
        if product_error:
            problems.append(product_error)
        name = _registration_csv_cell(row, indexes, "Название")
        if not name:
            problems.append("не заполнено обязательное поле «Название».")
        year, year_error = _registration_csv_year(_registration_csv_cell(row, indexes, "Год"))
        if year_error:
            problems.append(year_error)
        evaluation_date, _evaluation_date_value, evaluation_error = _registration_csv_optional_date(
            _registration_csv_cell(row, indexes, "Дата оценки"),
            "Дата оценки",
        )
        if evaluation_error:
            problems.append(evaluation_error)
        deadline, _deadline_value, deadline_error = _registration_csv_optional_date(
            _registration_csv_cell(row, indexes, "Дедлайн"),
            "Дедлайн",
        )
        if deadline_error:
            problems.append(deadline_error)
        status = _registration_csv_status(_registration_csv_cell(row, indexes, "Статус"))
        if status is None:
            status_raw = _registration_csv_cell(row, indexes, "Статус")
            if status_raw:
                problems.append(f"неизвестный статус «{status_raw}».")
            else:
                problems.append("не заполнено обязательное поле «Статус».")
        _status_date_text, status_date_value, status_date_error = _registration_csv_optional_date(
            _registration_csv_cell(row, indexes, "Дата статуса"),
            "Дата статуса",
        )
        if status_date_error:
            problems.append(status_date_error)
        country, country_error = _registration_csv_country(
            _registration_csv_cell(row, indexes, "Заказчик: страна"),
            countries_by_key,
            ambiguous_countries,
            current=instance.country if instance else None,
        )
        if country_error:
            problems.append(country_error)
        registration_date, registration_date_value, registration_date_error = _registration_csv_optional_date(
            _registration_csv_cell(row, indexes, "Заказчик: дата регистр."),
            "Заказчик: дата регистр.",
        )
        if registration_date_error:
            problems.append(registration_date_error)
        asset_owner_country, asset_owner_country_error = _registration_csv_country(
            _registration_csv_cell(row, indexes, "Владелец: страна"),
            countries_by_key,
            ambiguous_countries,
            current=instance.asset_owner_country if instance else None,
        )
        if asset_owner_country_error:
            problems.append(asset_owner_country_error)
        asset_owner_date, asset_owner_date_value, asset_owner_date_error = _registration_csv_optional_date(
            _registration_csv_cell(row, indexes, "Владелец: дата регистр."),
            "Владелец: дата регистр.",
        )
        if asset_owner_date_error:
            problems.append(asset_owner_date_error)
        toggles, toggle_error = _registration_csv_toggles(row, indexes)
        if toggle_error:
            problems.append(toggle_error)
        if problems:
            warnings.append(f"Строка {row_number}: " + " ".join(problems))
            continue

        customer = _registration_csv_cell(row, indexes, "Заказчик: наименование")
        identifier = _registration_csv_cell(row, indexes, "Заказчик: идент.")
        registration_number = _registration_csv_cell(row, indexes, "Заказчик: регистр. номер")
        registration_region = _registration_csv_cell(row, indexes, "Заказчик: регион")
        asset_owner = _registration_csv_cell(row, indexes, "Владелец: наименование")
        asset_owner_identifier = _registration_csv_cell(row, indexes, "Владелец: идент.")
        asset_owner_registration_number = _registration_csv_cell(row, indexes, "Владелец: регистр. номер")
        asset_owner_region = _registration_csv_cell(row, indexes, "Владелец: регион")
        values = {
            "number": number,
            "contract": contract,
            "group_member": group_member,
            "agreement_type": agreement_type,
            "products": products,
            "name": name,
            "year": year,
            "evaluation_date": evaluation_date,
            "deadline": deadline,
            "status": status,
            "status_date": status_date_value,
            "country": country,
            "customer": customer,
            "identifier": identifier,
            "registration_number": registration_number,
            "registration_region": registration_region,
            "registration_date": registration_date,
            "asset_owner": asset_owner,
            "asset_owner_country": asset_owner_country,
            "asset_owner_identifier": asset_owner_identifier,
            "asset_owner_registration_number": asset_owner_registration_number,
            "asset_owner_region": asset_owner_region,
            "asset_owner_registration_date": asset_owner_date,
            "project_manager": _registration_csv_person_value(
                _registration_csv_cell(row, indexes, "Руководитель проекта"),
                stored_name=instance.project_manager if instance else "",
                stored_prs=instance.project_manager_prs_id if instance else "",
                resolver=_resolve_project_manager_choice,
            ),
            "project_coordinator": _registration_csv_person_value(
                _registration_csv_cell(row, indexes, "Координатор проекта"),
                stored_name=instance.project_coordinator if instance else "",
                stored_prs=instance.project_coordinator_prs_id if instance else "",
                resolver=_resolve_project_coordinator_choice,
            ),
            "toggles": toggles or {},
            "matches_customer": _registration_parties_match(
                customer, country, identifier, registration_number, registration_region, registration_date_value,
                asset_owner, asset_owner_country, asset_owner_identifier, asset_owner_registration_number,
                asset_owner_region, asset_owner_date_value,
            ),
        }
        try:
            saved = _save_registration_csv_row(request, instance, values)
        except forms.ValidationError as exc:
            warnings.append(f"Строка {row_number}: {exc.messages[0] if exc.messages else exc}")
            continue
        except Exception as exc:
            warnings.append(f"Строка {row_number}: ошибка сохранения — {exc}")
            continue
        if (values.get("toggles") or {}).get("evaluation_date_common") is True:
            common_evaluation_rows.append(saved)
        if instance is None:
            created += 1
        else:
            updated += 1

    _registration_csv_share_common_evaluation_dates(common_evaluation_rows)
    return JsonResponse({"ok": True, "created": created, "updated": updated, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_create(request):
    if request.method == "GET":
        form = ProjectRegistrationForm()
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "create"))
    form = ProjectRegistrationForm(request.POST)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "create"))
    base_obj = form.save(commit=False)
    customer_rows = _customer_rows_from_post(request.POST)
    customer_countries = _customer_country_map(customer_rows)
    owner_rows = _owner_rows_from_post(request.POST)
    owner_countries = _customer_country_map(owner_rows)
    product_ids = list(getattr(form, "cleaned_type_ids", []))
    if not product_ids:
        form.add_error("type_ids", "Укажите хотя бы один продукт.")
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "create"))
    if len(product_ids) > 9:
        form.add_error("type_ids", "В одном проекте не больше девяти этапов.")
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "create"))
    from .stage_terms import (
        compute_grouped_stage_chains,
        parse_posted_stages,
        store_stage_snapshot,
    )

    posted_stages = parse_posted_stages(request.POST, product_ids) or []
    posted_contract_ids = (
        _request_list(request.POST, "stage_contract_id")
        if "stage_contract_id" in request.POST
        else None
    )
    contract_ends = (
        _posted_contract_group_ends(request.POST)
        if "contract_group_id" in request.POST
        else None
    )
    contract_end_flags = (
        _posted_contract_group_end_flags(request.POST)
        if contract_ends is not None
        else None
    )
    if posted_contract_ids is not None:
        create_contract_ids = [
            str(posted_contract_ids[offset] if offset < len(posted_contract_ids) else "")
            for offset in range(len(product_ids))
        ]
    else:
        fallback_contract_id = str(base_obj.contract_project_registration_id or "")
        create_contract_ids = [fallback_contract_id for _product_id in product_ids]
    chain = compute_grouped_stage_chains(
        base_obj.project_start_date,
        posted_stages,
        create_contract_ids,
    ) if posted_stages else []
    contracts_by_pk = _contracts_by_pk(create_contract_ids) if posted_contract_ids is not None else {}
    with transaction.atomic():
        start_position = _next_position(ProjectRegistration)
        parent = _copy_registration_form_values(base_obj)
        parent.position = start_position
        parent.status = "Не начат"
        parent.type = None
        if customer_rows and product_ids:
            _write_customer_party(
                parent,
                _customer_party_for_product(customer_rows, product_ids[0]) or _blank_customer_party(),
                customer_countries,
            )
        if product_ids:
            _apply_posted_owner_party(parent, owner_rows, owner_countries, product_ids[0])
        if posted_contract_ids is not None and product_ids:
            _assign_stage_contract(parent, create_contract_ids[0], contracts_by_pk)
            if contract_ends is not None:
                _apply_posted_contract_end(
                    parent,
                    create_contract_ids[0],
                    contract_ends,
                    contract_end_flags,
                )
        parent.save()
        for offset, product_id in enumerate(product_ids):
            obj = base_obj if offset == 0 else _copy_registration_form_values(base_obj)
            if customer_rows:
                _write_customer_party(
                    obj,
                    _customer_party_for_product(customer_rows, product_id) or _blank_customer_party(),
                    customer_countries,
                )
            _apply_posted_owner_party(obj, owner_rows, owner_countries, product_id)
            obj.stage_project = parent
            if posted_contract_ids is not None:
                _assign_stage_contract(obj, create_contract_ids[offset], contracts_by_pk)
                if contract_ends is not None:
                    _apply_posted_contract_end(
                        obj,
                        create_contract_ids[offset],
                        contract_ends,
                        contract_end_flags,
                    )
            if offset < len(chain):
                stage = dict(chain[offset])
                stage["product_id"] = product_id
                store_stage_snapshot(obj, stage, base_obj.project_start_date)
            else:
                stage1_value = _request_decimal_at(request.POST, "stage1_weeks", offset)
                stage2_value = _request_decimal_at(request.POST, "stage2_weeks", offset)
                if stage1_value is not None:
                    obj.stage1_weeks = stage1_value
                if stage2_value is not None:
                    obj.stage2_weeks = stage2_value
            obj.position = start_position + offset + 1
            obj.save()
            _save_ranked_registration_products(obj, [product_id])
        ProjectRegistration.refresh_number_sequences([parent.number])
    _sync_posted_customer_parties(request, customer_rows, base_obj)
    _sync_posted_owner_parties(request, owner_rows, base_obj)
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_delete(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    number = reg.number
    parent_id = reg.stage_project_id
    if parent_id:
        align_project_service_scope(reg.stage_project or reg)
    reg.delete()
    if parent_id and not ProjectRegistration.objects.filter(stage_project_id=parent_id).exists():
        ProjectRegistration.objects.filter(pk=parent_id).delete()
    ProjectRegistration.refresh_number_sequences([number])
    return _render_projects_updated(request)

def _registration_json(payload, registration):
    summary = summary_payload_for_registration(registration) if registration is not None else None
    if summary:
        payload["summary"] = summary
    return payload


def _apply_project_start_date_from_status(registration):
    """Дата статуса при запуске становится общей датой начала проекта.

    Поле в карточке проекта не блокируется: дату можно изменить вручную.
    """
    if registration is None or not registration.status_date:
        return
    start_date = registration.status_date
    ids = {registration.pk}
    block, _group_label = summary_block_for_pk(registration.pk)
    if block:
        ids.update(item.pk for item in block if item.pk)
        parent_id = block[0].stage_project_id
        if parent_id:
            ids.add(parent_id)
    elif registration.stage_project_id:
        ids.add(registration.stage_project_id)
    ProjectRegistration.objects.filter(pk__in=ids).update(project_start_date=start_date)
    registration.project_start_date = start_date


def _launch_not_started_registration(pk):
    updated = (
        ProjectRegistration.objects
        .filter(pk=pk, status="Не начат")
        .update(status="В работе", status_date=timezone.localdate())
    )
    if not updated:
        return False, ProjectRegistration.objects.filter(pk=pk).only("id", "status", "status_date").first()

    reg = ProjectRegistration.objects.filter(pk=pk).first()
    if reg is not None:
        sync_summary_status_date_for_status_change(reg, "Не начат")
        _apply_project_start_date_from_status(reg)
        try:
            copy_typical_gantt_to_project(reg, launch_date=date.today())
        except Exception:
            pass
    return True, reg


def _store_summary_deferred(block, group_label, deferred):
    previous_deferred = block_is_deferred(block)
    previous_label = registration_summary_state(
        [item.status for item in block],
        previous_deferred,
    )["label"]
    parent_id = block[0].stage_project_id if block else None
    if parent_id:
        ProjectRegistration.objects.filter(pk=parent_id).update(summary_deferred=deferred)
        parent = block[0].stage_project
        if parent is not None and parent.pk == parent_id:
            parent.summary_deferred = deferred
    else:
        number = block[0].number
        if deferred:
            RegistrationGroupSummaryState.objects.update_or_create(
                number=number,
                group_label=group_label,
                defaults={"deferred": True},
            )
        else:
            RegistrationGroupSummaryState.objects.filter(
                number=number,
                group_label=group_label,
            ).update(deferred=False)
    new_label = registration_summary_state([item.status for item in block], deferred)["label"]
    sync_summary_status_date_for_label_change(block, group_label, previous_label, new_label)


def _summary_group_from_request(request):
    raw_project = (request.POST.get("project") or "").strip()
    if raw_project:
        try:
            project_id = int(raw_project)
        except ValueError:
            return None, "", JsonResponse({"ok": False, "error": "Некорректная группа проектов."}, status=400)
        block, group_label = summary_block_for_project(project_id)
        if not block:
            return None, group_label, JsonResponse({"ok": False, "error": "Группа проектов не найдена."}, status=400)
        return block, group_label, None
    raw_number = (request.POST.get("number") or "").strip()
    group_label = (request.POST.get("group") or "").strip()
    try:
        number = int(raw_number)
    except ValueError:
        return None, "", JsonResponse({"ok": False, "error": "Некорректная группа проектов."}, status=400)
    block = summary_block_for_group(number, group_label)
    if not block:
        return None, group_label, JsonResponse({"ok": False, "error": "Группа проектов не найдена."}, status=400)
    return block, group_label, None


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_launch(request, pk: int):
    launched, reg = _launch_not_started_registration(pk)
    if not launched:
        status = reg.status if reg is not None else ""
        return JsonResponse(
            _registration_json(
                {
                    "ok": False,
                    "error": "Запуск доступен только для проектов со статусом «Не начат».",
                    "status": status,
                },
                reg,
            ),
            status=400,
        )

    return JsonResponse(_registration_json({
        "ok": True,
        "status": "В работе",
        **_status_date_fields(reg),
    }, reg))

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_group_summary_status(request):
    block, group_label, error_response = _summary_group_from_request(request)
    if error_response is not None:
        return error_response

    mode = (request.POST.get("mode") or "").strip()
    if mode not in {"deferred", "auto"}:
        return JsonResponse({"ok": False, "error": "Некорректный статус группы."}, status=400)

    deferred = mode == "deferred"
    _store_summary_deferred(block, group_label, deferred)

    return JsonResponse({
        "ok": True,
        "summary": summary_payload(block, group_label, deferred),
    })


def _save_summary_person(block, field_name, prs_field, name, prs_id):
    for row in _summary_person_targets(block):
        if getattr(row, field_name) == name and getattr(row, prs_field) == prs_id:
            continue
        setattr(row, field_name, name)
        setattr(row, prs_field, prs_id)
        row.save(update_fields=[field_name, prs_field])


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_group_summary_manager(request):
    block, _group_label, error_response = _summary_group_from_request(request)
    if error_response is not None:
        return error_response

    manager_value = (request.POST.get("project_manager") or "").strip()
    manager_name, manager_prs_id = _resolve_project_manager_choice(manager_value)
    _save_summary_person(block, "project_manager", "project_manager_prs_id", manager_name, manager_prs_id)
    return JsonResponse({
        "ok": True,
        "manager": manager_name,
        "managerValue": manager_prs_id or manager_name,
        "managerLabel": _short_fio_label(manager_name),
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_group_summary_coordinator(request):
    block, _group_label, error_response = _summary_group_from_request(request)
    if error_response is not None:
        return error_response

    coordinator_value = (request.POST.get("project_coordinator") or "").strip()
    coordinator_name, coordinator_prs_id, matched = _resolve_project_coordinator_choice(coordinator_value)
    source = block[0].stage_project if block[0].stage_project_id else block[0]
    if coordinator_value and not matched:
        stored_name = (source.project_coordinator or "").strip()
        stored_prs_id = (source.project_coordinator_prs_id or "").strip()
        if coordinator_value not in {stored_name, stored_prs_id}:
            return JsonResponse(
                {"ok": False, "error": "Выберите координатора проектов."},
                status=400,
            )
        coordinator_name = stored_name
        coordinator_prs_id = stored_prs_id
    _save_summary_person(
        block,
        "project_coordinator",
        "project_coordinator_prs_id",
        coordinator_name,
        coordinator_prs_id,
    )
    return JsonResponse({
        "ok": True,
        "coordinator": coordinator_name,
        "coordinatorValue": coordinator_prs_id or coordinator_name,
        "coordinatorLabel": _short_fio_label(coordinator_name),
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_group_summary_launch(request):
    block, group_label, error_response = _summary_group_from_request(request)
    if error_response is not None:
        return error_response

    number = block[0].number
    deferred = block_is_deferred(block)
    state = registration_summary_state([item.status for item in block], deferred)
    if not state["can_launch"]:
        return JsonResponse(
            {
                "ok": False,
                "error": "Запуск группы доступен, когда все этапы «Не начат» и группа не отложена.",
                "summary": summary_payload(block, group_label, deferred),
            },
            status=400,
        )

    with transaction.atomic():
        locked = {
            item.pk: item
            for item in ProjectRegistration.objects.select_for_update().filter(pk__in=[item.pk for item in block])
        }
        ordered = [locked[item.pk] for item in block if item.pk in locked]
        if (
            len(ordered) != len(block)
            or any(item.status != "Не начат" for item in ordered)
            or block_is_deferred(ordered)
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Запуск группы доступен, когда все этапы «Не начат» и группа не отложена.",
                    "summary": summary_payload(ordered or block, group_label, block_is_deferred(ordered or block)),
                },
                status=400,
            )
        launched, reg = _launch_not_started_registration(ordered[0].pk)

    if not launched or reg is None:
        status = reg.status if reg is not None else ""
        return JsonResponse(
            {
                "ok": False,
                "error": "Запуск доступен только для проектов со статусом «Не начат».",
                "status": status,
                "summary": summary_payload_for_registration(ordered[0]) or summary_payload(block, group_label, deferred),
            },
            status=400,
        )

    launched_block, launched_group = summary_block_for_pk(reg.pk)
    summary = summary_payload(
        launched_block or block,
        launched_group or group_label,
        block_is_deferred(launched_block or block),
    )
    return JsonResponse({
        "ok": True,
        "status": "В работе",
        "projectId": reg.pk,
        "summary": summary,
        **_status_date_fields(reg),
    })

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_status_update(request, pk: int):
    status_value = (request.POST.get("status") or "").strip()
    valid_statuses = {value for value, _label in ProjectRegistration.STATUS_CHOICES}
    if status_value not in valid_statuses:
        return JsonResponse({"ok": False, "error": "Некорректный статус проекта."}, status=400)

    reg = get_object_or_404(
        ProjectRegistration.objects.only("id", "status", "status_date", "launched_at", "gantt_data"),
        pk=pk,
    )
    if status_value == DEFERRED_STATUS:
        block, _group_label = summary_block_for_pk(reg.pk)
        if block:
            return JsonResponse(
                {"ok": False, "error": "В строке этапа нельзя выбрать статус «Отложен»."},
                status=400,
            )
    previous_status = reg.status
    if reg.status != status_value:
        reg.status = status_value
        reg.save(update_fields=["status"])

    if previous_status == "Не начат" and status_value == "В работе":
        _apply_project_start_date_from_status(reg)
        try:
            copy_typical_gantt_to_project(reg, launch_date=date.today())
        except Exception:
            pass

    return JsonResponse(_registration_json({
        "ok": True,
        "status": reg.status,
        **_status_date_fields(reg),
    }, reg))

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_manager_update(request, pk: int):
    manager_value = (request.POST.get("project_manager") or "").strip()
    manager_name, manager_prs_id = _resolve_project_manager_choice(manager_value)

    reg = get_object_or_404(
        ProjectRegistration.objects.only("id", "project_manager", "project_manager_prs_id"),
        pk=pk,
    )
    if reg.project_manager != manager_name or reg.project_manager_prs_id != manager_prs_id:
        reg.project_manager = manager_name
        reg.project_manager_prs_id = manager_prs_id
        reg.save(update_fields=["project_manager", "project_manager_prs_id"])

    return JsonResponse(
        {
            "ok": True,
            "manager": reg.project_manager,
            "managerValue": reg.project_manager_prs_id or reg.project_manager,
            "managerLabel": _short_fio_label(reg.project_manager),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_coordinator_update(request, pk: int):
    coordinator_value = (request.POST.get("project_coordinator") or "").strip()
    coordinator_name, coordinator_prs_id, matched = _resolve_project_coordinator_choice(coordinator_value)

    reg = get_object_or_404(
        ProjectRegistration.objects.only(
            "id",
            "project_coordinator",
            "project_coordinator_prs_id",
        ),
        pk=pk,
    )
    if coordinator_value and not matched:
        stored_name = (reg.project_coordinator or "").strip()
        stored_prs_id = (reg.project_coordinator_prs_id or "").strip()
        if coordinator_value not in {stored_name, stored_prs_id}:
            return JsonResponse(
                {"ok": False, "error": "Выберите координатора проектов."},
                status=400,
            )
        coordinator_name = stored_name
        coordinator_prs_id = stored_prs_id
    if reg.project_coordinator != coordinator_name or reg.project_coordinator_prs_id != coordinator_prs_id:
        reg.project_coordinator = coordinator_name
        reg.project_coordinator_prs_id = coordinator_prs_id
        reg.save(update_fields=["project_coordinator", "project_coordinator_prs_id"])

    return JsonResponse(
        {
            "ok": True,
            "coordinator": reg.project_coordinator,
            "coordinatorValue": reg.project_coordinator_prs_id or reg.project_coordinator,
            "coordinatorLabel": _short_fio_label(reg.project_coordinator),
        }
    )

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_deadline_update(request, pk: int):
    raw_deadline = (request.POST.get("deadline") or "").strip()
    deadline = None
    if raw_deadline:
        try:
            deadline = datetime.strptime(raw_deadline, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"ok": False, "error": "Некорректная дата дедлайна."}, status=400)

    reg = get_object_or_404(ProjectRegistration.objects.only("id", "deadline"), pk=pk)
    if reg.deadline != deadline:
        reg.deadline = deadline
        reg.save(update_fields=["deadline"])
        from projects_app.services.schedule_sync import sync_project_gantt_by_id

        sync_project_gantt_by_id(reg.pk)

    return JsonResponse(
        {
            "ok": True,
            "deadline": reg.deadline.isoformat() if reg.deadline else "",
            "deadlineLabel": _short_date_label(reg.deadline),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def registration_evaluation_date_update(request, pk: int):
    raw_evaluation_date = (request.POST.get("evaluation_date") or "").strip()
    evaluation_date = None
    if raw_evaluation_date:
        try:
            evaluation_date = datetime.strptime(raw_evaluation_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"ok": False, "error": "Некорректная дата оценки."}, status=400)

    reg = get_object_or_404(
        ProjectRegistration.objects.only("id", "evaluation_date", "stage_terms_json"),
        pk=pk,
    )
    if reg.evaluation_date != evaluation_date or reg.stage_terms_json:
        reg.evaluation_date = evaluation_date
        update_fields = ["evaluation_date"]
        if reg.stage_terms_json:
            from .stage_terms import format_date

            stages = list(reg.stage_terms_json)
            last_stage = dict(stages[-1]) if stages else {}
            last_stage["evaluation_date_enabled"] = True
            last_stage["evaluation_date"] = format_date(evaluation_date)
            stages[-1] = last_stage
            reg.stage_terms_json = stages
            update_fields.append("stage_terms_json")
        reg.save(update_fields=update_fields)

    return JsonResponse(
        {
            "ok": True,
            "evaluationDate": reg.evaluation_date.isoformat() if reg.evaluation_date else "",
            "evaluationDateLabel": _short_date_label(reg.evaluation_date),
        }
    )


def _normalize_registration_positions():
    items = ProjectRegistration.objects.order_by("position", "id").only("id", "position")
    for idx, it in enumerate(items, start=1):
        if it.position != idx:
            ProjectRegistration.objects.filter(pk=it.pk).update(position=idx)

@require_http_methods(["POST", "GET"])
@login_required
def registration_move_up(request, pk: int):
    _normalize_registration_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position", "number"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx-1]
        ProjectRegistration.objects.filter(pk=cur.id).update(position=prev.position)
        ProjectRegistration.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_registration_positions()
        ProjectRegistration.refresh_number_sequences([cur.number, prev.number])
    return _render_projects_updated(request)

@require_http_methods(["POST", "GET"])
@login_required
def registration_move_down(request, pk: int):
    _normalize_registration_positions()
    items = list(ProjectRegistration.objects.order_by("position", "id").only("id", "position", "number"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx+1]
        ProjectRegistration.objects.filter(pk=cur.id).update(position=nxt.position)
        ProjectRegistration.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_registration_positions()
        ProjectRegistration.refresh_number_sequences([cur.number, nxt.number])
    return _render_projects_updated(request)

# --- Условия контракта ---

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ContractConditionsForm(instance=reg)
        return render(request, CONTRACT_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg,
        })
    form = ContractConditionsForm(request.POST, instance=reg)
    if not form.is_valid():
        return _render_projects_modal_form_error(request, CONTRACT_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg,
        })
    form.save()
    return _render_projects_updated(request)


# --- График проекта ---
# All five views below operate on `ProjectRegistration.gantt_data` (the same
# JSON store backing the Gantt diagram). The (project_pk, task_id) pair
# identifies a row uniquely; task_id is the DHTMLX task id inside the
# `data` array.
def _schedule_form_context(form, action, *, project_pk, task_id=None, project=None):
    return {
        "form": form,
        "action": action,
        "project_pk": project_pk,
        "task_id": task_id,
        "project": project,
    }


def _gantt_task_dict(reg, task_id: str):
    payload = reg.gantt_data if isinstance(reg.gantt_data, dict) else {}
    for task in payload.get("data") or []:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return None


def _initial_from_task(task: dict, payload: dict) -> dict:
    from datetime import date as _date
    def _parse(value):
        if not value:
            return None
        if isinstance(value, _date):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(str(value), fmt).date()
                except ValueError:
                    continue
        return None
    # Resolve predecessors: turn each link.target==task.id into its source's WBS.
    from .services.gantt_tasks import _wbs_for_tasks
    wbs = _wbs_for_tasks(payload.get("data") or [])
    sources = [
        wbs.get(str(link.get("source"))) or str(link.get("source") or "")
        for link in (payload.get("links") or [])
        if str(link.get("target")) == str(task.get("id"))
    ]
    raw_type = str(task.get("type") or "task").strip() or "task"
    section_name = str(task.get("service_section_name") or task.get("section_name") or "").strip()
    text = task.get("text") or ""
    # Lightbox parity: when the saved task is a service section, the textarea
    # holds the optional display name (blank if it equals the section name);
    # the section dropdown is the source of truth for the section identity.
    if raw_type == "service_section":
        display_text = "" if text == section_name else text
    else:
        display_text = text
    return {
        "type": raw_type,
        "service_section_name": section_name,
        "task": display_text,
        "start_date": _parse(task.get("start_date")),
        "end_date": _parse(task.get("end_date")),
        "specialty": task.get("specialty") or "",
        "executor": task.get("executor") or "",
        "deadline": _parse(task.get("deadline")),
        "constraint_type": (task.get("constraint_type") or "").lower(),
        "constraint_date": _parse(task.get("constraint_date")),
        "duration": (
            int(round(float(task["duration"])))
            if task.get("duration") not in (None, "")
            else None
        ),
        "duration_star": (
            (_parse(task.get("end_date")) - _parse(task.get("start_date"))).days
            if _parse(task.get("end_date")) and _parse(task.get("start_date"))
            else None
        ),
        "predecessors": ", ".join([s for s in sources if s]),
        "progress": task.get("progress") or 0,
    }


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def project_schedule_form_create(request, pk: int):
    """Add a new task to ProjectRegistration[pk].gantt_data."""
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ProjectScheduleTaskForm(registration=reg)
        return render(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "create", project_pk=reg.pk, project=reg),
        )
    form = ProjectScheduleTaskForm(request.POST, registration=reg)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "create", project_pk=reg.pk, project=reg),
        )
    try:
        gantt_tasks.add_task(reg, form.task_payload())
    except ValueError as exc:
        form.add_error(None, str(exc))
        return _render_projects_modal_form_error(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "create", project_pk=reg.pk, project=reg),
        )
    return _render_projects_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def project_schedule_form_edit(request, project_pk: int, task_id: str):
    reg = get_object_or_404(ProjectRegistration, pk=project_pk)
    task = _gantt_task_dict(reg, task_id)
    if task is None:
        raise Http404("Задача не найдена.")
    if request.method == "GET":
        form = ProjectScheduleTaskForm(
            initial=_initial_from_task(task, reg.gantt_data or {}),
            registration=reg,
        )
        return render(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "edit", project_pk=reg.pk, task_id=task_id, project=reg),
        )
    form = ProjectScheduleTaskForm(request.POST, registration=reg)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "edit", project_pk=reg.pk, task_id=task_id, project=reg),
        )
    try:
        gantt_tasks.update_task(reg, task_id, form.task_payload())
    except ValueError as exc:
        form.add_error(None, str(exc))
        return _render_projects_modal_form_error(
            request,
            SCHEDULE_FORM_TEMPLATE,
            _schedule_form_context(form, "edit", project_pk=reg.pk, task_id=task_id, project=reg),
        )
    return _render_projects_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def project_schedule_delete(request, project_pk: int, task_id: str):
    reg = get_object_or_404(ProjectRegistration, pk=project_pk)
    gantt_tasks.delete_task(reg, task_id)
    return _render_projects_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def project_schedule_gantt(request, pk: int):
    """Get or save the Gantt diagram payload for a project registration.

    Mirrors policy_app.typical_service_term_gantt but stores into
    ProjectRegistration.gantt_data. We reuse the same JSON normalization
    helpers from policy_app to keep parity with the typical-service-term
    editor used as the UI factory.
    """
    from policy_app.views import (
        _typical_service_term_section_options,
        _typical_service_term_specialty_options,
        _typical_service_term_executor_options,
        _normalize_typical_service_term_gantt_payload,
        _default_typical_service_term_gantt_data,
    )

    reg = get_object_or_404(
        ProjectRegistration.objects.select_related("type"),
        pk=pk,
    )
    if reg.stage_project_id is None:
        only_stage = list(reg.stages.order_by("position", "id")[:2])
        if len(only_stage) == 1:
            reg = only_stage[0]

    primary_product = reg.primary_product
    primary_product_id = getattr(primary_product, "pk", None) or getattr(reg.type, "pk", None)
    from projects_app.services.schedule_sync import sync_project_gantt_from_sources
    sync_project_gantt_from_sources(reg)

    def _build_payload():
        gantt_data = (
            reg.gantt_data
            if isinstance(reg.gantt_data, dict) and reg.gantt_data.get("data")
            else None
        )
        if gantt_data is None:
            placeholder = SimpleNamespace(
                pk=reg.pk,
                source_data_weeks=0,
                source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
                preliminary_report_months=0,
                preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
                final_report_weeks=0,
                final_report_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            )
            gantt_data = _default_typical_service_term_gantt_data(placeholder)
            base_iso = (reg.launched_at or date.today()).isoformat()
            meta = gantt_data.setdefault("meta", {})
            meta["base_date"] = base_iso
            meta["project_start"] = base_iso

        product_label = (
            getattr(primary_product, "short_name", "")
            or getattr(reg.type, "short_name", "")
            or reg.short_uid
        )
        section_options = (
            _typical_service_term_section_options(primary_product_id)
            if primary_product_id
            else []
        )
        section_specialties_by_name = {
            item["label"]: item.get("specialties", []) for item in section_options
        }
        specialty_options = _typical_service_term_specialty_options()
        executor_options = _typical_service_term_executor_options()
        from projects_app.services.schedule_sync import extend_assignment_options_for_managed_tasks

        specialty_options, executor_options = extend_assignment_options_for_managed_tasks(
            copy.deepcopy(gantt_data),
            specialty_options,
            executor_options,
            section_specialties_by_name,
        )
        return {
            "ok": True,
            "gantt": gantt_data,
            "section_options": section_options,
            "specialty_options": specialty_options,
            "executor_options": executor_options,
            "term": {
                "id": reg.pk,
                "product": product_label,
                "project_label": f"{reg.short_uid} {product_label}".strip(),
                "source_data_weeks": 0,
                "source_data_term_unit": TypicalServiceTerm.TermUnit.WEEKS,
                "preliminary_report_months": "0,0",
                "preliminary_report_term_unit": TypicalServiceTerm.TermUnit.MONTHS,
                "final_report_weeks": 0,
                "final_report_term_unit": TypicalServiceTerm.TermUnit.WEEKS,
                "launched_at": reg.launched_at.isoformat() if reg.launched_at else "",
            },
        }

    if request.method == "GET":
        return JsonResponse(_build_payload())

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        from projects_app.services.schedule_sync import (
            canonicalize_managed_assignments_for_validation,
            extend_assignment_options_from_project_payload,
            extend_assignment_options_for_managed_tasks,
            sanitize_project_gantt_resources_for_validation,
            validate_managed_task_changes,
        )

        validate_managed_task_changes(reg.gantt_data, payload)
        section_options = (
            _typical_service_term_section_options(primary_product_id)
            if primary_product_id
            else []
        )
        section_names = [item["label"] for item in section_options]
        section_specialties_by_name = {
            item["label"]: item.get("specialties", []) for item in section_options
        }
        specialty_options = _typical_service_term_specialty_options()
        executor_options = _typical_service_term_executor_options()
        payload_for_normalize = canonicalize_managed_assignments_for_validation(
            copy.deepcopy(payload),
            reg,
        )
        payload_for_normalize = sanitize_project_gantt_resources_for_validation(payload_for_normalize)
        specialty_options, executor_options = extend_assignment_options_from_project_payload(
            payload_for_normalize,
            specialty_options,
            executor_options,
        )
        specialty_options, executor_options = extend_assignment_options_for_managed_tasks(
            payload_for_normalize,
            specialty_options,
            executor_options,
            section_specialties_by_name,
        )
        gantt_data, _dated_tasks, _base_date = _normalize_typical_service_term_gantt_payload(
            payload_for_normalize,
            section_names,
            section_specialties_by_name,
            specialty_options,
            executor_options,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    reg.gantt_data = gantt_data
    reg.save(update_fields=["gantt_data"])

    sync_project_gantt_from_sources(reg)
    return JsonResponse(_build_payload())


@require_http_methods(["POST", "GET"])
@login_required
def project_schedule_move_up(request, project_pk: int, task_id: str):
    reg = get_object_or_404(ProjectRegistration, pk=project_pk)
    gantt_tasks.move_task(reg, task_id, "up")
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))


@require_http_methods(["POST", "GET"])
@login_required
def project_schedule_move_down(request, project_pk: int, task_id: str):
    reg = get_object_or_404(ProjectRegistration, pk=project_pk)
    gantt_tasks.move_task(reg, task_id, "down")
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))


# --- Объем работ ---
@login_required
@require_GET
def work_deps(request):
    """
    Вернёт данные для автоподстановки по выбранному проекту:
      - type / type_short (из Product)
      - name (из ProjectRegistration)
    """
    pid = request.GET.get("project")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False})

    reg = (
        ProjectRegistration.objects
        .select_related("type", "country", "stage_project")
        .prefetch_related("product_links__product", "stages__type", "stages__product_links__product")
        .filter(pk=pid)
        .first()
    )
    if not reg:
        return JsonResponse({"ok": False})
    type_label = reg.filter_type_label or reg.type_short_display

    return JsonResponse({
        "ok": True,
        "type": type_label,
        "type_short": type_label,
        "name": reg.name or "",
        "project_manager": reg.project_manager_prs_id or reg.project_manager or "",
        "country_id": reg.country_id or "",
        "next_asset_code": next_work_volume_asset_code(reg),
    })


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_create(request):
    if request.method == "GET":
        form = WorkVolumeForm()
        return render(request, WORK_FORM_TEMPLATE, _work_form_context(form, "create"))
    form = WorkVolumeForm(request.POST)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request, WORK_FORM_TEMPLATE, _work_form_context(form, "create")
        )
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.asset_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
        business_entity_source="[Проекты / Наименование актива]",
        **_sync_selection_kwargs(request, "asset_autocomplete"),
    )
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response

def _selected_group_contract(form):
    field = form.fields["contract_project_registration"]
    if form.is_bound:
        raw = str(form.data.get("contract_project_registration") or "").strip()
        if not raw:
            return None
        return field.queryset.filter(pk=raw).first()
    instance = getattr(form, "instance", None)
    if instance is not None and instance.contract_project_registration_id:
        return instance.contract_project_registration
    return None


def _append_widget_class(widget, class_name):
    current = widget.attrs.get("class", "")
    classes = [item for item in current.split() if item]
    if class_name not in classes:
        classes.append(class_name)
    widget.attrs["class"] = " ".join(classes)


def _registration_contract_filter_number(form, registration=None):
    if getattr(form, "is_bound", False):
        raw = str(form.data.get("number") or "").strip()
        if raw:
            return raw
    if registration is not None and getattr(registration, "number", None) not in (None, ""):
        return registration.number
    initial = form.initial.get("number")
    if initial not in (None, ""):
        return initial
    return form.fields["number"].initial


def _limit_group_contract_choices(form, number, *, keep_contract_id=None):
    """В сводной строке «Договор ID» — только проекты договоров с тем же номером."""
    field = form.fields["contract_project_registration"]
    base = field.queryset
    try:
        contract_number = int(number)
    except (TypeError, ValueError):
        limited = base.none()
    else:
        limited = base.filter(number=contract_number)
    if keep_contract_id:
        limited = base.filter(Q(pk__in=limited.values("pk")) | Q(pk=keep_contract_id))
    field.queryset = limited


def _apply_single_registration_contract_fields(form, registration=None):
    keep_contract_id = None
    if registration is not None:
        keep_contract_id = getattr(registration, "contract_project_registration_id", None)
    _limit_group_contract_choices(
        form,
        _registration_contract_filter_number(form, registration),
        keep_contract_id=keep_contract_id,
    )
    _prepare_group_contract_fields(form)
    contract = _selected_group_contract(form)
    return contract.pk if contract is not None else ""


def _prepare_group_contract_fields(form):
    agreement_type = form.fields["agreement_type"]
    _append_widget_class(agreement_type.widget, "readonly-field")
    _append_widget_class(agreement_type.widget, "registration-contract-derived")
    _append_widget_class(agreement_type.widget, "registration-contract-agreement-type")
    agreement_type.widget.attrs["tabindex"] = "-1"
    agreement_type.widget.attrs["aria-disabled"] = "true"
    choices = list(agreement_type.choices)
    if not choices or choices[0][0] != "":
        agreement_type.choices = [("", "")] + choices

    agreement_number = form.fields["agreement_number"]
    _append_widget_class(agreement_number.widget, "readonly-field")
    _append_widget_class(agreement_number.widget, "registration-contract-derived")
    _append_widget_class(agreement_number.widget, "registration-contract-agreement-number")
    agreement_number.widget.attrs["readonly"] = True
    agreement_number.widget.attrs["tabindex"] = "-1"

    _append_widget_class(
        form.fields["contract_project_registration"].widget,
        "registration-contract-select",
    )

    if form.is_bound:
        return
    contract = _selected_group_contract(form)
    if contract is None:
        form.initial["agreement_type"] = ""
        form.initial["agreement_number"] = ""
        return
    form.initial["agreement_type"] = contract.agreement_type or ""
    form.initial["agreement_number"] = contract.agreement_number or ""


def _blank_customer_party():
    return {
        "scope": "all",
        "customer": "",
        "country_id": "",
        "identifier": "",
        "registration_number": "",
        "registration_region": "",
        "registration_date": "",
        "product_label": "",
        "product_code": "",
        "selected_identifier_record_id": "",
        "selected_from_autocomplete": False,
    }


def _customer_rows_from_post(data):
    if data is None or "customer_scope" not in data:
        return None
    scopes = _request_list(data, "customer_scope")
    if not scopes:
        return None
    customers = _request_list(data, "customer")
    countries = _request_list(data, "country")
    identifiers = _request_list(data, "identifier")
    numbers = _request_list(data, "registration_number")
    regions = _request_list(data, "registration_region")
    dates = _request_list(data, "registration_date")
    selected_ids = _request_list(data, "customer_autocomplete_identifier_record_id")
    selected_flags = _request_list(data, "customer_autocomplete_selected_from_autocomplete")
    rows = []
    for index, scope in enumerate(scopes):
        normalized = str(scope or "all").strip() or "all"
        if normalized != "all":
            try:
                normalized = str(int(normalized))
            except ValueError:
                continue
        flag = selected_flags[index] if index < len(selected_flags) else ""
        rows.append({
            "scope": normalized,
            "customer": customers[index] if index < len(customers) else "",
            "country_id": countries[index] if index < len(countries) else "",
            "identifier": identifiers[index] if index < len(identifiers) else "",
            "registration_number": numbers[index] if index < len(numbers) else "",
            "registration_region": regions[index] if index < len(regions) else "",
            "registration_date": dates[index] if index < len(dates) else "",
            "product_label": "",
            "product_code": "",
            "selected_identifier_record_id": selected_ids[index] if index < len(selected_ids) else "",
            "selected_from_autocomplete": str(flag or "").strip().lower() in {"1", "true", "yes", "on"},
        })
    if any(row["scope"] == "all" for row in rows):
        rows = [next(row for row in rows if row["scope"] == "all")]
    return rows or None


def _customer_party_for_product(rows, product_id):
    if not rows:
        return None
    shared = None
    specific = None
    product_key = str(product_id or "")
    for row in rows:
        if row["scope"] == "all":
            shared = row
        elif product_key and row["scope"] == product_key:
            specific = row
    return specific or shared


def _customer_country_map(rows):
    ids = []
    for row in rows or []:
        raw = str(row.get("country_id") or "").strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    if not ids:
        return {}
    return {
        str(country.pk): country
        for country in OKSMCountry.objects.filter(pk__in=ids)
    }


def _write_customer_party(target, row, countries):
    party = row or _blank_customer_party()
    target.customer = party.get("customer") or ""
    target.country = countries.get(str(party.get("country_id") or ""))
    target.identifier = party.get("identifier") or ""
    target.registration_number = party.get("registration_number") or ""
    target.registration_region = party.get("registration_region") or ""
    target.registration_date = _parse_project_form_date(party.get("registration_date"))
    if target.asset_owner_matches_customer:
        target.asset_owner = target.customer
        target.asset_owner_country = target.country
        target.asset_owner_identifier = target.identifier
        target.asset_owner_registration_number = target.registration_number
        target.asset_owner_region = target.registration_region
        target.asset_owner_registration_date = target.registration_date


def _attach_customer_product_labels(rows):
    ids = []
    for row in rows:
        if row.get("scope") in {None, "", "all"}:
            continue
        try:
            ids.append(int(row["scope"]))
        except (TypeError, ValueError):
            continue
    products = list(Product.objects.filter(pk__in=ids)) if ids else []
    labels = {str(product.pk): _product_option_label(product) for product in products}
    codes = {str(product.pk): _customer_product_code(product) for product in products}
    for row in rows:
        key = str(row.get("scope") or "")
        if not row.get("product_label"):
            row["product_label"] = labels.get(key, "")
        if not row.get("product_code"):
            row["product_code"] = codes.get(key, "")
    return rows


def _customer_party_from_registration(registration, scope, product_label="", product_code=""):
    party = _blank_customer_party()
    party.update({
        "scope": scope,
        "customer": registration.customer or "",
        "country_id": str(registration.country_id or ""),
        "identifier": registration.identifier or "",
        "registration_number": registration.registration_number or "",
        "registration_region": registration.registration_region or "",
        "registration_date": registration.registration_date.isoformat() if registration.registration_date else "",
        "product_label": product_label or "",
        "product_code": product_code or "",
    })
    return party


def _customer_rows_for_registrations(registrations):
    def party_key(item):
        return (
            " ".join(str(item.customer or "").split()),
            item.country_id,
            item.identifier or "",
            item.registration_number or "",
            item.registration_region or "",
            item.registration_date,
        )

    if not registrations:
        return [_blank_customer_party()]
    if len({party_key(item) for item in registrations}) <= 1:
        return [_customer_party_from_registration(registrations[0], "all")]
    rows = []
    seen = set()
    for item in registrations:
        products = item.ordered_products()
        product = products[0] if products else None
        if product is None or not getattr(product, "pk", None):
            continue
        product_id = str(product.pk)
        if product_id in seen:
            continue
        seen.add(product_id)
        rows.append(_customer_party_from_registration(
            item,
            product_id,
            _product_option_label(product),
            _customer_product_code(product),
        ))
    return rows or [_customer_party_from_registration(registrations[0], "all")]


def _customer_product_code(product):
    return (getattr(product, "short_name", None) or "").strip()


def _apply_customer_product_codes(rows):
    ids = []
    for row in rows or []:
        raw = str(row.get("scope") or "").strip()
        if not raw or raw == "all":
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    if not ids:
        return rows
    codes = {
        str(product.pk): _customer_product_code(product)
        for product in Product.objects.filter(pk__in=ids)
    }
    for row in rows:
        code = codes.get(str(row.get("scope") or ""))
        if code:
            row["product_label"] = code
    return rows


def _customer_product_for_registration(registration):
    if registration is None:
        return None
    products = registration.ordered_products()
    product = products[0] if products else None
    if product is None or not getattr(product, "pk", None):
        return None
    return product


def _customer_rows_for_form(form, action, registration=None, block=None):
    lock_stage_product = action == "edit" and getattr(form, "lock_project_roles", False)
    if getattr(form, "is_bound", False):
        posted = _customer_rows_from_post(form.data)
        if posted:
            rows = _attach_customer_product_labels(posted)
            if lock_stage_product:
                _apply_customer_product_codes(rows)
            return rows
    if lock_stage_product:
        product = _customer_product_for_registration(registration)
        if product is not None:
            return [_customer_party_from_registration(
                registration,
                str(product.pk),
                _customer_product_code(product),
            )]
    if action == "group_edit" and block:
        return _customer_rows_for_registrations(block)
    if registration is not None and getattr(registration, "pk", None):
        return _customer_rows_for_registrations([registration])
    row = _blank_customer_party()
    country_initial = form.fields["country"].initial if "country" in form.fields else ""
    identifier_initial = form.fields["identifier"].initial if "identifier" in form.fields else ""
    row["country_id"] = str(country_initial or "")
    row["identifier"] = identifier_initial or ""
    return [row]


def _include_customer_row_countries(form, rows):
    ids = []
    for row in rows or []:
        raw = str(row.get("country_id") or "").strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    if not ids or "country" not in form.fields:
        return
    field = form.fields["country"]
    # Уже суженный список стран бывает с distinct(); повторный | с ним падает.
    field.queryset = OKSMCountry.objects.filter(
        Q(pk__in=field.queryset.values("pk")) | Q(pk__in=ids)
    ).order_by("short_name")


def _blank_owner_party():
    return {
        "scope": "all",
        "asset_owner": "",
        "country_id": "",
        "identifier": "",
        "registration_number": "",
        "registration_region": "",
        "registration_date": "",
        "product_label": "",
        "product_code": "",
    }


def _owner_matches_customer(form, registration):
    if getattr(form, "is_bound", False):
        return "asset_owner_matches_customer" in (getattr(form, "data", None) or {})
    if registration is not None and getattr(registration, "pk", None):
        return bool(registration.asset_owner_matches_customer)
    return True


def _owner_row_from_customer_row(row):
    return {
        "scope": row.get("scope") or "all",
        "asset_owner": row.get("customer") or "",
        "country_id": str(row.get("country_id") or ""),
        "identifier": row.get("identifier") or "",
        "registration_number": row.get("registration_number") or "",
        "registration_region": row.get("registration_region") or "",
        "registration_date": row.get("registration_date") or "",
        "product_label": row.get("product_label") or "",
        "product_code": row.get("product_code") or "",
    }


def _owner_rows_from_post(data):
    if data is None or "asset_owner_scope" not in data:
        return None
    scopes = _request_list(data, "asset_owner_scope")
    if not scopes:
        return None
    names = _request_list(data, "asset_owner")
    countries = _request_list(data, "asset_owner_country")
    identifiers = _request_list(data, "asset_owner_identifier")
    numbers = _request_list(data, "asset_owner_registration_number")
    regions = _request_list(data, "asset_owner_region")
    dates = _request_list(data, "asset_owner_registration_date")
    selected_ids = _request_list(data, "asset_owner_autocomplete_identifier_record_id")
    selected_flags = _request_list(data, "asset_owner_autocomplete_selected_from_autocomplete")
    rows = []
    for index, scope in enumerate(scopes):
        normalized = str(scope or "all").strip() or "all"
        if normalized != "all":
            try:
                normalized = str(int(normalized))
            except ValueError:
                continue
        flag = selected_flags[index] if index < len(selected_flags) else ""
        rows.append({
            "scope": normalized,
            "asset_owner": names[index] if index < len(names) else "",
            "country_id": countries[index] if index < len(countries) else "",
            "identifier": identifiers[index] if index < len(identifiers) else "",
            "registration_number": numbers[index] if index < len(numbers) else "",
            "registration_region": regions[index] if index < len(regions) else "",
            "registration_date": dates[index] if index < len(dates) else "",
            "product_label": "",
            "product_code": "",
            "selected_identifier_record_id": selected_ids[index] if index < len(selected_ids) else "",
            "selected_from_autocomplete": str(flag or "").strip().lower() in {"1", "true", "yes", "on"},
        })
    if any(row["scope"] == "all" for row in rows):
        rows = [next(row for row in rows if row["scope"] == "all")]
    return rows or None


def _owner_party_for_product(rows, product_id):
    if not rows:
        return None
    shared = None
    specific = None
    product_key = str(product_id or "")
    for row in rows:
        if row["scope"] == "all":
            shared = row
        elif product_key and row["scope"] == product_key:
            specific = row
    return specific or shared


def _write_owner_party(target, row, countries):
    party = row or _blank_owner_party()
    target.asset_owner = party.get("asset_owner") or ""
    target.asset_owner_country = countries.get(str(party.get("country_id") or ""))
    target.asset_owner_identifier = party.get("identifier") or ""
    target.asset_owner_registration_number = party.get("registration_number") or ""
    target.asset_owner_region = party.get("registration_region") or ""
    target.asset_owner_registration_date = _parse_project_form_date(party.get("registration_date"))


def _owner_party_from_registration(registration, scope, product_label="", product_code=""):
    party = _blank_owner_party()
    party.update({
        "scope": scope,
        "asset_owner": registration.asset_owner or "",
        "country_id": str(registration.asset_owner_country_id or ""),
        "identifier": registration.asset_owner_identifier or "",
        "registration_number": registration.asset_owner_registration_number or "",
        "registration_region": registration.asset_owner_region or "",
        "registration_date": (
            registration.asset_owner_registration_date.isoformat()
            if registration.asset_owner_registration_date else ""
        ),
        "product_label": product_label or "",
        "product_code": product_code or "",
    })
    return party


def _owner_rows_for_registrations(registrations):
    def party_key(item):
        return (
            " ".join(str(item.asset_owner or "").split()),
            item.asset_owner_country_id,
            item.asset_owner_identifier or "",
            item.asset_owner_registration_number or "",
            item.asset_owner_region or "",
            item.asset_owner_registration_date,
        )

    if not registrations:
        return [_blank_owner_party()]
    if len({party_key(item) for item in registrations}) <= 1:
        return [_owner_party_from_registration(registrations[0], "all")]
    rows = []
    seen = set()
    for item in registrations:
        products = item.ordered_products()
        product = products[0] if products else None
        if product is None or not getattr(product, "pk", None):
            continue
        product_id = str(product.pk)
        if product_id in seen:
            continue
        seen.add(product_id)
        rows.append(_owner_party_from_registration(
            item,
            product_id,
            _product_option_label(product),
            _customer_product_code(product),
        ))
    return rows or [_owner_party_from_registration(registrations[0], "all")]


def _attach_owner_product_labels(rows):
    ids = []
    for row in rows:
        if row.get("scope") in {None, "", "all"}:
            continue
        try:
            ids.append(int(row["scope"]))
        except (TypeError, ValueError):
            continue
    products = list(Product.objects.filter(pk__in=ids)) if ids else []
    labels = {str(product.pk): _product_option_label(product) for product in products}
    codes = {str(product.pk): _customer_product_code(product) for product in products}
    for row in rows:
        key = str(row.get("scope") or "")
        if not row.get("product_label"):
            row["product_label"] = labels.get(key, "")
        if not row.get("product_code"):
            row["product_code"] = codes.get(key, "")
    return rows


def _owner_rows_for_form(form, action, registration, block, customer_rows):
    matches = _owner_matches_customer(form, registration)
    if matches:
        return [_owner_row_from_customer_row(row) for row in (customer_rows or [_blank_customer_party()])]
    lock_stage_product = action == "edit" and getattr(form, "lock_project_roles", False)
    if getattr(form, "is_bound", False):
        posted = _owner_rows_from_post(form.data)
        if posted:
            rows = _attach_owner_product_labels(posted)
            if lock_stage_product:
                _apply_customer_product_codes(rows)
            return rows
    if action == "group_edit" and block:
        return _owner_rows_for_registrations(block)
    if lock_stage_product and registration is not None:
        product = _customer_product_for_registration(registration)
        if product is not None:
            return [_owner_party_from_registration(
                registration,
                str(product.pk),
                _customer_product_code(product),
                _customer_product_code(product),
            )]
    if registration is not None and getattr(registration, "pk", None):
        return _owner_rows_for_registrations([registration])
    return [_blank_owner_party()]


def _include_owner_row_countries(form, rows):
    ids = []
    for row in rows or []:
        raw = str(row.get("country_id") or "").strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            continue
    if not ids or "asset_owner_country" not in form.fields:
        return
    field = form.fields["asset_owner_country"]
    field.queryset = OKSMCountry.objects.filter(
        Q(pk__in=field.queryset.values("pk")) | Q(pk__in=ids)
    ).order_by("short_name")


def _apply_posted_owner_party(target, owner_rows, countries, product_id):
    if getattr(target, "asset_owner_matches_customer", False) or not owner_rows:
        return
    _write_owner_party(
        target,
        _owner_party_for_product(owner_rows, product_id) or _blank_owner_party(),
        countries,
    )


def _sync_posted_owner_parties(request, rows, fallback):
    if getattr(fallback, "asset_owner_matches_customer", False):
        return
    if not rows:
        _sync_to_legal_entity_record(
            fallback.asset_owner,
            fallback.asset_owner_country,
            fallback.asset_owner_identifier,
            fallback.asset_owner_registration_number,
            fallback.asset_owner_registration_date,
            request.user,
            business_entity_source="[Проекты / Владелец активов]",
            registration_region=fallback.asset_owner_region,
            **_sync_selection_kwargs(request, "asset_owner_autocomplete"),
        )
        return
    countries = _customer_country_map(rows)
    for row in rows:
        _sync_to_legal_entity_record(
            row.get("asset_owner") or "",
            countries.get(str(row.get("country_id") or "")),
            row.get("identifier") or "",
            row.get("registration_number") or "",
            _parse_project_form_date(row.get("registration_date")),
            request.user,
            selected_identifier_record_id=row.get("selected_identifier_record_id") or "",
            selected_from_autocomplete=bool(row.get("selected_from_autocomplete")),
            business_entity_source="[Проекты / Владелец активов]",
            registration_region=row.get("registration_region") or "",
        )


_CUSTOMER_PARTY_SAVE_FIELDS = [
    "customer",
    "country",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "asset_owner",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
]


def _sync_posted_customer_parties(request, rows, fallback):
    if not rows:
        _sync_to_legal_entity_record(
            fallback.customer,
            fallback.country,
            fallback.identifier,
            fallback.registration_number,
            fallback.registration_date,
            request.user,
            business_entity_source="[Проекты / Заказчик]",
            registration_region=fallback.registration_region,
            **_sync_selection_kwargs(request, "customer_autocomplete"),
        )
    else:
        countries = _customer_country_map(rows)
        for row in rows:
            _sync_to_legal_entity_record(
                row.get("customer") or "",
                countries.get(str(row.get("country_id") or "")),
                row.get("identifier") or "",
                row.get("registration_number") or "",
                _parse_project_form_date(row.get("registration_date")),
                request.user,
                selected_identifier_record_id=row.get("selected_identifier_record_id") or "",
                selected_from_autocomplete=bool(row.get("selected_from_autocomplete")),
                business_entity_source="[Проекты / Заказчик]",
                registration_region=row.get("registration_region") or "",
            )
    if rows and getattr(fallback, "asset_owner_matches_customer", False):
        countries = _customer_country_map(rows)
        for row in rows:
            country = countries.get(str(row.get("country_id") or ""))
            _sync_to_legal_entity_record(
                row.get("customer") or "",
                country,
                row.get("identifier") or "",
                row.get("registration_number") or "",
                _parse_project_form_date(row.get("registration_date")),
                request.user,
                business_entity_source="[Проекты / Владелец активов]",
                registration_region=row.get("registration_region") or "",
            )
        return
    _sync_to_legal_entity_record(
        fallback.asset_owner,
        fallback.asset_owner_country,
        fallback.asset_owner_identifier,
        fallback.asset_owner_registration_number,
        fallback.asset_owner_registration_date,
        request.user,
        business_entity_source="[Проекты / Владелец активов]",
        registration_region=fallback.asset_owner_region,
        **_sync_selection_kwargs(request, "asset_owner_autocomplete"),
    )


def _registration_contract_meta(form):
    from .stage_terms import contract_is_signed, slim_contract_stage

    payload = {}
    field = form.fields.get("contract_project_registration")
    if field is None:
        return payload
    for contract in field.queryset:
        stages = []
        for item in list(contract.stage_payloads_json or []):
            if isinstance(item, dict):
                stages.append(slim_contract_stage(item))
        payload[str(contract.pk)] = {
            "agreement_type": contract.agreement_type or "",
            "agreement_number": contract.agreement_number or "",
            "contract_date": contract.contract_date.isoformat() if contract.contract_date else "",
            "contract_end": contract.contract_end.isoformat() if contract.contract_end else "",
            "contract_end_enabled": bool(contract.contract_end_enabled),
            "customer": contract.customer or "",
            "country_id": str(contract.country_id or ""),
            "identifier": contract.identifier or "",
            "registration_number": contract.registration_number or "",
            "registration_region": contract.registration_region or "",
            "registration_date": contract.registration_date.isoformat() if contract.registration_date else "",
            "status": contract.status or "",
            "short_uid": contract.short_uid or "",
            "signed": contract_is_signed(contract.status),
            "stages": stages,
        }
    return payload


def _registration_contract_meta_json(form):
    return json.dumps(_registration_contract_meta(form), ensure_ascii=False).replace("<", "\\u003c")


def _group_summary_form_kwargs(block):
    parent = block[0].stage_project if block[0].stage_project_id else None
    deferred = block_is_deferred(block)
    state = registration_summary_state([item.status for item in block], deferred)
    return {
        "allow_multiple_products": True,
        "project_role_source": parent or block[0],
        "summary_status_choices": (("auto", state["auto_label"]), ("deferred", DEFERRED_STATUS)),
        "summary_status_mode": "deferred" if state["deferred"] else "auto",
    }


def _apply_group_summary_deadline(form, block):
    if form.is_bound or not block:
        return
    deadline = block[-1].deadline
    form.initial["deadline"] = deadline
    form.fields["deadline"].initial = deadline


def _project_start_source(block):
    if not block:
        return None
    parent = block[0].stage_project if block[0].stage_project_id else None
    return parent if parent is not None else block[0]


def _apply_shared_project_start_date(form, block):
    if form.is_bound or not block:
        return
    source = _project_start_source(block)
    value = source.project_start_date if source is not None else None
    form.initial["project_start_date"] = value
    form.fields["project_start_date"].initial = value


def _copy_project_start_date(block, project_start_date, *, skip_pk=None):
    if not block:
        return
    ids = [item.pk for item in block if item.pk and item.pk != skip_pk]
    parent = block[0].stage_project if block[0].stage_project_id else None
    if parent is not None and parent.pk and parent.pk != skip_pk:
        ids.append(parent.pk)
    if ids:
        ProjectRegistration.objects.filter(pk__in=ids).update(project_start_date=project_start_date)


def _stage_member_form_kwargs(registration):
    block, _group_label = summary_block_for_pk(registration.pk)
    if not block:
        return {"allow_multiple_products": False}, None
    parent = block[0].stage_project if block[0].stage_project_id else None
    return {
        "allow_multiple_products": False,
        "lock_project_roles": True,
        "project_role_source": parent or block[0],
    }, block


def _summary_person_targets(block):
    targets = []
    seen = set()
    parent = block[0].stage_project if block and block[0].stage_project_id else None
    rows = list(block)
    if parent is not None:
        rows.append(parent)
    for row in rows:
        if row.pk in seen:
            continue
        seen.add(row.pk)
        targets.append(row)
    return targets


def _registration_group_edit_context(form, block, number, group_label, ranked_products, source_ids):
    from .stage_terms import parse_posted_stages

    _limit_group_contract_choices(form, number)
    _prepare_group_contract_fields(form)
    if form.is_bound:
        stage_rows = parse_posted_stages(form.data) or _group_member_stage_rows(block)
        for index, stage in enumerate(stage_rows):
            if index >= len(ranked_products):
                break
            product_id = ranked_products[index].get("product_id") or ""
            if product_id:
                stage["product_id"] = product_id
    else:
        stage_rows = _group_member_stage_rows(block)
    return _registration_form_context(
        form,
        "group_edit",
        block[0],
        ranked_products=ranked_products,
        group_number=number,
        group_label=group_label,
        group_source_ids=source_ids,
        registration_contract_meta_json=_registration_contract_meta_json(form),
        registration_stage_rows=stage_rows,
        customer_source_block=block,
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_group_summary_edit(request):
    block, group_label, number = _registration_group_edit_target(request)
    if not block:
        return HttpResponse("Группа проектов не найдена.", status=404)
    form_kwargs = _group_summary_form_kwargs(block)
    if request.method == "GET":
        form = ProjectRegistrationForm(instance=block[0], **form_kwargs)
        _apply_group_summary_deadline(form, block)
        _apply_shared_project_start_date(form, block)
        return render(
            request,
            REG_FORM_TEMPLATE,
            _registration_group_edit_context(
                form,
                block,
                number,
                group_label,
                _group_edit_ranked_products(block),
                [item.pk for item in block],
            ),
        )
    form = ProjectRegistrationForm(request.POST, instance=block[0], **form_kwargs)
    ranked_products = _group_edit_ranked_products_from_data(request.POST)
    source_ids = _group_source_ids(request.POST)
    if form.is_valid():
        specs, spec_error = _registration_group_edit_specs(request.POST, form.cleaned_type_ids)
        block_ids = {item.pk for item in block}
        if spec_error:
            form.add_error("type_ids", spec_error)
        else:
            unknown = [
                spec["registration_id"]
                for spec in specs
                if spec["registration_id"] is not None and spec["registration_id"] not in block_ids
            ]
            if unknown or any(pk not in block_ids for pk in source_ids):
                form.add_error("type_ids", "Состав группы изменился. Обновите страницу и откройте группу снова.")
            else:
                save_error = _save_registration_group_edit(request, form, block, specs, source_ids)
                if save_error:
                    form.add_error("type_ids", save_error)
                else:
                    mode = (request.POST.get("summary_status_mode") or "").strip()
                    if mode in {"auto", "deferred"}:
                        _store_summary_deferred(block, group_label, mode == "deferred")
                    return _render_projects_updated(request)
    return render(
        request,
        REG_FORM_TEMPLATE,
        _registration_group_edit_context(
            form,
            block,
            number,
            group_label,
            ranked_products,
            source_ids,
        ),
    )


# Редактирование регистрации
@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    form_kwargs, block = _stage_member_form_kwargs(reg)
    if request.method == "GET":
        form = ProjectRegistrationForm(instance=reg, **form_kwargs)
        _apply_shared_project_start_date(form, block)
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "edit", reg))
    form = ProjectRegistrationForm(request.POST, instance=reg, **form_kwargs)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "edit", reg))
    obj = form.save()
    if "stage_contract_id" in request.POST:
        stage_contract_id = _request_list(request.POST, "stage_contract_id")
        contract_id = stage_contract_id[0] if stage_contract_id else ""
        _assign_stage_contract(obj, contract_id, _contracts_by_pk([contract_id]))
        if "contract_group_id" in request.POST:
            _apply_posted_contract_end(
                obj,
                contract_id,
                _posted_contract_group_ends(request.POST),
                _posted_contract_group_end_flags(request.POST),
            )
        obj.save()
    _save_ranked_registration_products(obj, getattr(form, "cleaned_type_ids", []))
    if block is None:
        block, _group_label = summary_block_for_pk(obj.pk)
    if obj.stage_project_id:
        parent = obj.stage_project
        exclude = set(STAGE_TO_PARENT_ROLE_EXCLUDE)
        if not block or block[-1].pk != obj.pk:
            exclude.add("deadline")
        _apply_shared_registration_fields(parent, obj, include_contract_subject=True, exclude=exclude)
        parent.save()
    if block:
        _copy_project_start_date(block, obj.project_start_date, skip_pk=obj.pk)
    for work_item in obj.work_items.select_related("project").all():
        _ensure_performer_rows_for_work_item(work_item)
    _sync_to_legal_entity_record(
        obj.customer, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
        business_entity_source="[Проекты / Заказчик]",
        registration_region=obj.registration_region,
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    _sync_to_legal_entity_record(
        obj.asset_owner, obj.asset_owner_country, obj.asset_owner_identifier,
        obj.asset_owner_registration_number, obj.asset_owner_registration_date, request.user,
        business_entity_source="[Проекты / Владелец активов]",
        registration_region=obj.asset_owner_region,
        **_sync_selection_kwargs(request, "asset_owner_autocomplete"),
    )
    return _render_projects_updated(request)

class RegistrationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = getattr(obj, "type_short_display", "") or ""
        name_label = obj.name or ""
        parts = [obj.short_uid]
        if type_label:
            parts.append(str(type_label))
        if name_label:
            parts.append(name_label)
        return " ".join(parts)


def _employee_full_name(employee):
    parts = [
        employee.user.last_name.strip(),
        employee.user.first_name.strip(),
        employee.patronymic.strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _ordered_registration_sections(registration):
    product_rank_map = getattr(registration, "product_rank_map", {})
    product_ids = list(product_rank_map.keys())
    if not product_ids and getattr(registration, "type_id", None):
        product_ids = [registration.type_id]
        product_rank_map = {registration.type_id: 1}
    if not product_ids:
        return []
    sections = list(
        TypicalSection.objects
        .filter(product_id__in=product_ids)
        .exclude(Q(is_system=True) | Q(code__iexact=SYSTEM_DSC_SECTION_CODE))
        .select_related("product", "service_block", "service_block__expertise_dir")
        .prefetch_related(
            "service_block__ranked_specialties",
            "service_block__ranked_specialties__specialty",
        )
        .order_by("position", "id")
    )
    sections.sort(
        key=lambda section: (
            product_rank_map.get(section.product_id, 999999),
            section.position,
            section.id,
        )
    )
    return sections


def _executor_choices(current_value=""):
    choices = [("", "— Не выбрано —")]
    current_value = (current_value or "").strip()
    current_in_choices = False

    employees = (
        Employee.objects
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )
    for employee in employees:
        full_name = _employee_full_name(employee)
        if not full_name:
            continue
        choices.append((full_name, full_name))
        if full_name == current_value:
            current_in_choices = True

    if current_value and not current_in_choices:
        choices.insert(1, (current_value, current_value))

    return choices


def _typical_section_option_label(section):
    product = getattr(section.product, "short_name", "") if getattr(section, "product_id", None) else ""
    code = section.code or ""
    short_name_ru = section.short_name_ru or ""
    head = f"{product}:{code}" if product else code
    return " ".join(part for part in (head, short_name_ru) if part).strip()


# Редактирование записи "Объем работ"
def _work_form_context(form, action, work=None):
    asset_code = ""
    if work is not None and getattr(work, "pk", None):
        target_id = getattr(form, "service_target_id", None) or work.project_id
        if target_id:
            work.service_target_id = target_id
            asset_code = work_volume_asset_code(work)
    elif action == "create":
        project = None
        if getattr(form, "is_bound", False):
            raw_project = form.data.get("project")
            if raw_project:
                project = ProjectRegistration.objects.filter(pk=raw_project).first()
        if project is not None:
            asset_code = next_work_volume_asset_code(project)
    return {"form": form, "action": action, "work": work, "asset_code": asset_code}


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_edit(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    if request.method == "GET":
        form = WorkVolumeForm(instance=item)
        return render(request, WORK_FORM_TEMPLATE, _work_form_context(form, "edit", item))
    form = WorkVolumeForm(request.POST, instance=item)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request, WORK_FORM_TEMPLATE, _work_form_context(form, "edit", item)
        )
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.asset_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
        business_entity_source="[Проекты / Наименование актива]",
        **_sync_selection_kwargs(request, "asset_autocomplete"),
    )
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def work_delete(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    project_ids = delete_work_scope(item)
    if project_ids is None:
        return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))
    for pid in project_ids:
        _normalize_work_positions(pid)
        _normalize_legal_positions(pid)
    _normalize_performer_positions()
    response = _render_projects_updated(request)
    response[HX_TRIGGER_HEADER] = json.dumps({
        HX_PROJECTS_UPDATED_EVENT: True,
        HX_PERFORMERS_UPDATED_EVENT: True,
    })
    return response

def _normalize_work_positions(product_id: int | None = None):
    qs = WorkVolume.objects.select_related("project").only("id", "position", "project_id")
    if product_id:
        items = list(qs.filter(project_id=product_id).order_by("position", "id"))
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                WorkVolume.objects.filter(pk=it.pk).update(position=idx)
    else:
        # Группами по проекту
        cur_pid = None
        buf = []
        for it in qs.order_by("project_id", "position", "id"):
            if cur_pid is None:
                cur_pid = it.project_id
            if it.project_id != cur_pid:
                for idx, b in enumerate(buf, start=1):
                    if b.position != idx:
                        WorkVolume.objects.filter(pk=b.pk).update(position=idx)
                cur_pid, buf = it.project_id, [it]
            else:
                buf.append(it)
        for idx, b in enumerate(buf, start=1):
            if b.position != idx:
                WorkVolume.objects.filter(pk=b.pk).update(position=idx)

def _normalize_legal_positions(project_id: int | None = None):
    qs = LegalEntity.objects.select_related("project").only("id", "position", "project_id")
    if project_id:
        items = list(qs.filter(project_id=project_id).order_by("position", "id"))
        for idx, it in enumerate(items, start=1):
            if it.position != idx:
                LegalEntity.objects.filter(pk=it.pk).update(position=idx)
        return

    cur_pid = None
    buf = []
    for it in qs.order_by("project_id", "position", "id"):
        if cur_pid is None:
            cur_pid = it.project_id
        if it.project_id != cur_pid:
            for idx, b in enumerate(buf, start=1):
                if b.position != idx:
                    LegalEntity.objects.filter(pk=b.pk).update(position=idx)
            cur_pid, buf = it.project_id, [it]
        else:
            buf.append(it)
    for idx, b in enumerate(buf, start=1):
        if b.position != idx:
            LegalEntity.objects.filter(pk=b.pk).update(position=idx)

def _swap_work_volumes_if_unlocked(first: WorkVolume, second: WorkVolume) -> bool:
    if work_scope_order_lock_reason([first, second]):
        return False
    WorkVolume.objects.filter(pk=first.pk).update(position=second.position)
    WorkVolume.objects.filter(pk=second.pk).update(position=first.position)
    return True


@require_http_methods(["POST", "GET"])
@login_required
def work_move_up(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id

    _normalize_work_positions(pid)
    items = list(
        WorkVolume.objects
        .filter(project_id=pid)
        .order_by("position", "id")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        if _swap_work_volumes_if_unlocked(items[idx], items[idx - 1]):
            _normalize_work_positions(pid)
            mirror_work_positions(pid)

    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ БЕЗ HX-Trigger — чтобы не было двойной перерисовки
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))

@require_http_methods(["POST", "GET"])
@login_required
def work_move_down(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id

    _normalize_work_positions(pid)
    items = list(
        WorkVolume.objects
        .filter(project_id=pid)
        .order_by("position", "id")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        if _swap_work_volumes_if_unlocked(items[idx], items[idx + 1]):
            _normalize_work_positions(pid)
            mirror_work_positions(pid)

    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ БЕЗ HX-Trigger — чтобы не было двойной перерисовки
    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def legal_entity_form_create(request):
    if request.method == "GET":
        form = LegalEntityForm()
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = LegalEntityForm(request.POST)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "create"}
        )
    entity = form.save()
    _sync_to_legal_entity_record(
        entity.legal_name, entity.country, entity.identifier,
        entity.registration_number, entity.registration_date, request.user,
        business_entity_source="[Проекты / Наименование юридического лица]",
        **_sync_selection_kwargs(request, "legal_autocomplete"),
    )
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def legal_entity_form_edit(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    if request.method == "GET":
        form = LegalEntityForm(instance=entity)
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "edit", "legal_entity": entity})
    form = LegalEntityForm(request.POST, instance=entity)
    if not form.is_valid():
        return _render_projects_modal_form_error(
            request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "edit", "legal_entity": entity}
        )
    obj = form.save()
    _sync_to_legal_entity_record(
        obj.legal_name, obj.country, obj.identifier,
        obj.registration_number, obj.registration_date, request.user,
        business_entity_source="[Проекты / Наименование юридического лица]",
        **_sync_selection_kwargs(request, "legal_autocomplete"),
    )
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def legal_entity_delete(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    copies = legal_scope_copies(entity)
    project_ids = {copy.project_id for copy in copies if copy.project_id}
    for copy in copies:
        copy.delete()
    for pid in project_ids:
        _normalize_legal_positions(pid)
    return _render_projects_updated(request)


@require_http_methods(["POST", "GET"])
@login_required
def legal_entity_move_up(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    pid = entity.project_id

    _normalize_legal_positions(pid)
    items = list(
        LegalEntity.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        LegalEntity.objects.filter(pk=cur.id).update(position=prev.position)
        LegalEntity.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_legal_positions(pid)
        mirror_legal_positions(pid)

    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))

@require_http_methods(["POST", "GET"])
@login_required
def legal_entity_move_down(request, pk: int):
    entity = get_object_or_404(LegalEntity, pk=pk)
    pid = entity.project_id

    _normalize_legal_positions(pid)
    items = list(
        LegalEntity.objects
        .filter(project_id=pid)
        .order_by("position", "id")
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        LegalEntity.objects.filter(pk=cur.id).update(position=nxt.position)
        LegalEntity.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_legal_positions(pid)
        mirror_legal_positions(pid)

    return render(request, PROJECTS_PARTIAL_TEMPLATE, _projects_context(request.user))

def _bind_dynamic_performer_fields(form, *, data=None, instance=None):
    """
    Привязать серверные зависимости формы:
      - typical_section.queryset по продукту выбранной регистрации
      - choices для asset_name по WorkVolume выбранной регистрации
    """
    reg_id = None
    current_asset = ""
    if data and data.get("registration"):
        reg_id = data.get("registration")
    elif instance is not None:
        reg_id = getattr(instance, "registration_id", None)
    if data and data.get("asset_name"):
        current_asset = data.get("asset_name", "")
    elif instance is not None:
        current_asset = getattr(instance, "asset_name", "") or ""

    # Привязываем queryset для Типовых разделов
    if "typical_section" in form.fields:
        qs = TypicalSection.objects.none()
        if reg_id:
            reg = ProjectRegistration.objects.select_related("type").filter(pk=reg_id).first()
            if reg:
                section_ids = [section.pk for section in _ordered_registration_sections(reg)]
                if section_ids:
                    ordering = models.Case(
                        *[
                            models.When(pk=section_id, then=position)
                            for position, section_id in enumerate(section_ids)
                        ],
                        default=len(section_ids),
                        output_field=models.IntegerField(),
                    )
                    qs = (
                        TypicalSection.objects
                        .filter(pk__in=section_ids)
                        .select_related("product")
                        .order_by(ordering, "id")
                    )
        form.fields["typical_section"].queryset = qs
        form.fields["typical_section"].label_from_instance = _typical_section_option_label

    # Привязываем choices для Активов (если поле отрисовано как select)
    if "asset_name" in form.fields:
        assets = []
        if reg_id:
            assets = list(
                WorkVolume.objects
                .filter(project_id=reg_id)
                .values_list("asset_name", flat=True)
                .distinct()
            )
        if current_asset and current_asset not in assets:
            assets.append(current_asset)
        choices = [("", "— Не выбрано —")] + [(a, a) for a in assets if a]
        # Если поле CharField с Select-виджетом — просто зададим choices на виджете
        try:
            form.fields["asset_name"].widget.choices = choices
        except Exception:
            pass
        # Если вдруг это ChoiceField — зададим и на самом поле
        try:
            form.fields["asset_name"].choices = choices
        except Exception:
            pass

def _payment_request_context(user=None, *, payment_request_performers_qs=None, project_products_prefetch=None):
    from contracts_app.views import (
        _attach_contract_batch_display_fields,
        _contract_representative_key,
        _contract_representative_rows,
    )

    if payment_request_performers_qs is None:
        payment_request_performers_qs = (
            Performer.objects
            .select_related(
                "registration",
                "registration__type",
                "typical_section",
                "employee",
                "employee__user",
                "employee__person_record",
                "currency",
                "contract_group_member",
            )
            .filter(contract_batch_id__isnull=False)
            .order_by("contract_batch_id", "position", "id")
        )
    if project_products_prefetch is None:
        project_products_prefetch = models.Prefetch(
            "product_links",
            queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
        )

    is_expert = False
    has_active_smtp_connection = False
    if user and getattr(user, "is_authenticated", False):
        employee = getattr(user, "employee_profile", None)
        employee_role = getattr(employee, "role", "")
        is_expert = user.groups.filter(name=EXPERT_GROUP).exists() or employee_role == EXPERT_GROUP
        if is_expert:
            if employee:
                expert_filter = Q(employee_id=employee.pk)
                employee_full_name = Performer.employee_full_name(employee)
                if employee_full_name:
                    expert_filter |= Q(executor=employee_full_name)
                payment_request_performers_qs = payment_request_performers_qs.filter(expert_filter)
            else:
                payment_request_performers_qs = payment_request_performers_qs.none()
        has_active_smtp_connection = ExternalSMTPAccount.objects.filter(
            user=user,
            is_active=True,
            use_for_notifications=True,
        ).exists()

    payment_request_source = list(payment_request_performers_qs)
    payment_request_performers = _contract_representative_rows(payment_request_source)
    payment_request_price_map = {}
    for performer in payment_request_source:
        if performer.agreed_amount is None:
            continue
        key = _contract_representative_key(performer)
        payment_request_price_map[key] = (
            payment_request_price_map.get(key) or 0
        ) + performer.agreed_amount
    for performer in payment_request_performers:
        performer.total_price = payment_request_price_map.get(
            _contract_representative_key(performer)
        )
    payment_request_performers = _attach_contract_batch_display_fields(payment_request_performers)
    payment_request_project_ids = {p.registration_id for p in payment_request_performers}
    payment_request_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=payment_request_project_ids)
        .order_by("-number", "-id")
    )
    payment_request_sent_initial = timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

    return {
        "payment_request_performers": payment_request_performers,
        "payment_request_projects": payment_request_projects,
        "payment_request_sent_initial": payment_request_sent_initial,
        "is_expert": is_expert,
        "has_active_smtp_connection": has_active_smtp_connection,
    }

def _catalog_page_params(request, *, dedicated_url_name, page_param, page_size_param, default_size, options):
    page_size = default_size
    page_number = None
    if request is None:
        return page_size, page_number
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "")
    if url_name == dedicated_url_name:
        size_key, page_key = "page_size", "page"
    else:
        size_key, page_key = page_size_param, page_param
    try:
        page_size = int(request.GET.get(size_key, default_size))
    except (TypeError, ValueError):
        page_size = default_size
    if page_size not in options:
        page_size = default_size
    return page_size, request.GET.get(page_key)


def _catalog_pagination_urls(path, page_size, page_obj, paginator, extra_params):
    def page_url(number):
        query = [("page_size", page_size), ("page", number), *extra_params]
        return f"{path}?{urlencode(query)}"

    pagination_pages = []
    for number in paginator.get_elided_page_range(page_obj.number):
        if number == paginator.ELLIPSIS:
            pagination_pages.append({"ellipsis": True})
        else:
            pagination_pages.append(
                {
                    "number": number,
                    "url": page_url(number),
                    "current": number == page_obj.number,
                }
            )
    page_size_query = [("page", 1), *extra_params]
    return {
        "pages": pagination_pages,
        "previous_url": page_url(page_obj.previous_page_number()) if page_obj.has_previous() else "",
        "next_url": page_url(page_obj.next_page_number()) if page_obj.has_next() else "",
        "page_size_url": f"{path}?{urlencode(page_size_query)}",
    }


def _report_macros_table_context(request):
    page_size, page_number = _catalog_page_params(
        request,
        dedicated_url_name="report_macros_table",
        page_param="macros_page",
        page_size_param="macros_page_size",
        default_size=REPORT_MACRO_PAGE_SIZE,
        options=REPORT_MACRO_PAGE_SIZE_OPTIONS,
    )
    paginator = Paginator(ReportMacro.objects.order_by("position", "id"), page_size)
    page_obj = paginator.get_page(page_number)
    urls = _catalog_pagination_urls(reverse("report_macros_table"), page_size, page_obj, paginator, [])
    return {
        "report_macros": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "policy_pagination_pages": urls["pages"],
        "policy_pagination_previous_url": urls["previous_url"],
        "policy_pagination_next_url": urls["next_url"],
        "policy_pagination_start": page_obj.start_index(),
        "policy_pagination_end": page_obj.end_index(),
        "policy_page_size": page_size,
        "policy_page_size_options": REPORT_MACRO_PAGE_SIZE_OPTIONS,
        "policy_page_size_url": urls["page_size_url"],
    }


def _report_submission_slots(rows):
    """Group a current section row with the version rows hidden under its caret."""
    slots = []
    bucket = None
    for row in rows:
        if getattr(row, "is_current", True) or bucket is None:
            bucket = [row]
            slots.append(bucket)
        else:
            bucket.append(row)
    return slots


def _selected_report_project_ids(request):
    if request is None:
        return []
    raw_values = []
    for key in ("project", "reports_project"):
        for value in request.GET.getlist(key):
            raw_values.extend(part.strip() for part in str(value).split(",") if part.strip())
    project_ids = []
    seen = set()
    for value in raw_values:
        if value == "__all__":
            continue
        try:
            project_id = int(value)
        except (TypeError, ValueError):
            continue
        if project_id in seen:
            continue
        seen.add(project_id)
        project_ids.append(project_id)
    return project_ids


def _report_page_size_specified(request):
    if request is None:
        return False
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "")
    if url_name == "report_submission_table":
        return "page_size" in request.GET
    return "reports_page_size" in request.GET


def _report_submission_table_context(request, rows):
    page_size, page_number = _catalog_page_params(
        request,
        dedicated_url_name="report_submission_table",
        page_param="reports_page",
        page_size_param="reports_page_size",
        default_size=REPORT_TABLE_PAGE_SIZE,
        options=REPORT_TABLE_PAGE_SIZE_OPTIONS,
    )
    project_ids = _selected_report_project_ids(request)
    if project_ids and not _report_page_size_specified(request):
        page_size = REPORT_TABLE_PAGE_SIZE_OPTIONS[-1]
    if project_ids:
        allowed = set(project_ids)
        rows = [row for row in rows if getattr(row, "registration_id", None) in allowed]
    slots = _report_submission_slots(rows)
    paginator = Paginator(slots, page_size)
    page_obj = paginator.get_page(page_number)
    extra_params = [("project", project_id) for project_id in project_ids]
    urls = _catalog_pagination_urls(
        reverse("report_submission_table"),
        page_size,
        page_obj,
        paginator,
        extra_params,
    )
    flat_rows = [row for slot in page_obj.object_list for row in slot]
    return {
        "report_submission_rows": flat_rows,
        "reports_page_obj": page_obj,
        "reports_paginator": paginator,
        "reports_pagination_pages": urls["pages"],
        "reports_pagination_previous_url": urls["previous_url"],
        "reports_pagination_next_url": urls["next_url"],
        "reports_pagination_start": page_obj.start_index(),
        "reports_pagination_end": page_obj.end_index(),
        "reports_page_size": page_size,
        "reports_page_size_options": REPORT_TABLE_PAGE_SIZE_OPTIONS,
        "reports_page_size_url": urls["page_size_url"],
        "reports_project_ids": project_ids,
    }


def _performers_context(user=None, request=None):
    expert_project_ids = _confirmed_project_ids_for_expert(user)
    is_expert = expert_project_ids is not None
    is_admin = _is_admin_user(user)
    active_participation_statuses = ["Не начат", "В работе"]
    registration_products_prefetch = models.Prefetch(
        "registration__product_links",
        queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    project_products_prefetch = models.Prefetch(
        "product_links",
        queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    performers = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__product",
            "typical_section__service_block__expertise_direction",
            "employee",
            "employee__user",
            "currency",
        )
        .prefetch_related(registration_products_prefetch)
        .order_by(
            "-registration__number",
            "registration__short_uid",
            "registration_id",
            "asset_name",
            "position",
            "id",
        )
    )
    if expert_project_ids is not None:
        performers = performers.filter(registration_id__in=expert_project_ids)
    participation_performers = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__product",
            "typical_section__service_block__expertise_direction",
            "employee",
            "employee__user",
            "currency",
        )
        .prefetch_related(registration_products_prefetch)
        .annotate(executor_trim=Trim("executor"))
        .filter(registration__status__in=active_participation_statuses)
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    if expert_project_ids is not None:
        participation_performers = participation_performers.filter(registration_id__in=expert_project_ids)
    participation_project_ids = participation_performers.values_list("registration_id", flat=True).distinct()
    participation_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=_owning_project_ids(participation_project_ids))
        .order_by("-number", "-id")
    )
    info_request_performers = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__product",
            "employee",
            "employee__user",
        )
        .prefetch_related(registration_products_prefetch)
        .annotate(executor_trim=Trim("executor"))
        .filter(
            registration__status__in=active_participation_statuses,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            typical_section__service_block__accounting_type="Разделы",
        )
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    if expert_project_ids is not None:
        info_request_performers = info_request_performers.filter(registration_id__in=expert_project_ids)
    info_request_project_ids = info_request_performers.values_list("registration_id", flat=True).distinct()
    info_request_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=info_request_project_ids)
        .order_by("-number", "-id")
    )
    contract_performers = (
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
    if expert_project_ids is not None:
        contract_performers = contract_performers.filter(registration_id__in=expert_project_ids)
    contract_project_ids = contract_performers.values_list("registration_id", flat=True).distinct()
    contract_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=contract_project_ids)
        .order_by("-number", "-id")
    )
    payment_request_performers_qs = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
            "employee__person_record",
            "currency",
            "contract_group_member",
        )
        .filter(contract_batch_id__isnull=False)
        .order_by("contract_batch_id", "position", "id")
    )
    payment_request_context = _payment_request_context(
        user,
        payment_request_performers_qs=payment_request_performers_qs,
        project_products_prefetch=project_products_prefetch,
    )
    payment_request_performers = payment_request_context["payment_request_performers"]
    payment_request_projects = payment_request_context["payment_request_projects"]
    payment_request_sent_initial = payment_request_context["payment_request_sent_initial"]
    request_sent_initial = timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    performer_project_ids = performers.values_list("registration_id", flat=True).distinct()
    performer_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(id__in=_owning_project_ids(performer_project_ids))
        .order_by("-number", "-id")
    )
    user_is_direction_head = False
    has_active_smtp_connection = False
    if user:
        try:
            user_is_direction_head = getattr(user.employee_profile, "role", "") == DEPARTMENT_HEAD_GROUP
        except Exception:
            pass
        has_active_smtp_connection = ExternalSMTPAccount.objects.filter(
            user=user,
            is_active=True,
            use_for_notifications=True,
        ).exists()

    if user:
        performers = list(performers)
        annotate_performers_report_section_lock(performers)
        annotate_performers_section_codes(performers)
        performers.sort(
            key=lambda p: (
                -(getattr(p.registration, "number", None) or 0),
                getattr(p.registration, "short_uid", "") or "",
                p.registration_id or 0,
                *_performer_display_sort_key(p),
            )
        )
        for p in performers:
            p.executor_locked = _is_executor_locked(user, p)
            if is_expert:
                p.executor_locked = True

    if user_is_direction_head:
        from notifications_app.models import NotificationPerformerLink as NPL
        from django.db.models import F
        dh_notified_ids = set(
            NPL.objects
            .filter(
                notification__notification_type="project_participation_confirmation",
                notification__recipient_id=F("performer__employee__user_id"),
            )
            .values_list("performer_id", flat=True)
        )
        dh_department_id = getattr(user.employee_profile, "department_id", None)
        participation_performers = list(participation_performers)
        for p in participation_performers:
            ts_dir = _effective_direction_id(
                p.typical_section,
                getattr(getattr(p, "registration", None), "group_member", None),
            )
            in_dh_direction = bool(ts_dir and ts_dir == dh_department_id)
            p.dh_checkbox_locked = (
                not in_dh_direction
                or (p.employee_id and p.employee.user_id == user.id)
                or p.pk in dh_notified_ids
            )

    performer_order_signature = _performer_order_signature_for_items(
        [
            {"id": p.pk, "registration_id": p.registration_id}
            for p in performers
        ]
    )

    if not isinstance(participation_performers, list):
        participation_performers = list(participation_performers)
    from collections import defaultdict
    from types import SimpleNamespace
    snapshot_map = defaultdict(list)
    perf_ids = [p.pk for p in participation_performers]
    if perf_ids:
        for s in (
            PerformerParticipationSnapshot.objects
            .filter(performer_id__in=perf_ids)
            .select_related("employee", "employee__user")
            .order_by("request_sent_at", "id")
        ):
            snapshot_map[s.performer_id].append(s)

    participation_display_rows = []
    for p in participation_performers:
        p.is_snapshot = False
        for snap in snapshot_map.get(p.pk, []):
            row = SimpleNamespace(
                is_snapshot=True,
                registration_id=p.registration_id,
                registration=p.registration,
                executor=snap.executor_name,
                employee_id=snap.employee_id,
                participation_batch_id=None,
                asset_name=p.asset_name,
                typical_section=p.typical_section,
                request_sent_at=snap.request_sent_at,
                deadline_at=snap.deadline_at,
                response_display=snap.get_response_display(),
                response_at=snap.response_at,
                response_status=snap.response_status,
            )
            participation_display_rows.append(row)
        participation_display_rows.append(p)
    def _participation_sort_key(r):
        if r.is_snapshot:
            status_order = 3
        elif not getattr(r, "participation_request_sent_at", None):
            status_order = 0
        elif not getattr(r, "participation_response", ""):
            status_order = 1
        else:
            status_order = 2
        return (
            getattr(getattr(r, "registration", None), "number", 0) or 0,
            str(getattr(r, "participation_batch_id", "") or ""),
            getattr(r, "employee_id", None) or 0,
            r.registration_id or 0,
            r.executor or "",
            status_order,
            getattr(r, "asset_name", "") or "",
        )
    participation_display_rows.sort(key=_participation_sort_key)

    report_performers_qs = (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__product",
            "typical_section__service_block__expertise_direction",
            "employee",
            "employee__user",
            "employee__expert_profile",
            "employee__expert_profile__expertise_direction",
            "currency",
        )
        .prefetch_related(registration_products_prefetch)
        .annotate(executor_trim=Trim("executor"))
        .filter(registration__status__in=active_participation_statuses)
        .exclude(executor_trim="")
        .order_by("registration_id", "executor", "asset_name", "position", "id")
    )
    report_project_scope = report_visible_registration_ids(user)
    if report_project_scope is not None:
        report_performers_qs = report_performers_qs.filter(registration_id__in=report_project_scope)
    report_registration_ids = list(report_performers_qs.values_list("registration_id", flat=True).distinct())
    report_submission_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(project_products_prefetch)
        .filter(id__in=report_registration_ids)
        .order_by("-number", "-id")
    )
    report_uploads = list(
        PerformerReportUpload.objects.filter(
            registration_id__in=report_registration_ids,
        )
    )
    report_submission_rows = annotate_report_submission_rows(
        user,
        build_report_submission_rows(
            list(report_performers_qs),
            report_uploads,
        ),
    )
    report_submission_pagination = _report_submission_table_context(request, report_submission_rows)
    report_submission_rows = report_submission_pagination["report_submission_rows"]
    manage_report_checks = can_manage_report_checks(user)
    report_check_rules = []
    report_macros = []
    report_macros_pagination = {}
    if manage_report_checks:
        report_check_rules = list(
            ReportCheckRule.objects
            .select_related("product", "expertise_dir", "section", "section__product")
            .prefetch_related("lines__macro")
            .order_by("position", "id")
        )
        report_macros_pagination = _report_macros_table_context(request)
        report_macros = report_macros_pagination["report_macros"]

    context = {
        "performers": performers,
        "performer_projects": performer_projects,
        "performer_order_signature": performer_order_signature,
        "participation_performers": participation_performers,
        "participation_display_rows": participation_display_rows,
        "participation_projects": participation_projects,
        "report_submission_rows": report_submission_rows,
        "report_submission_projects": report_submission_projects,
        "allow_local_report_folder": local_report_folder_enabled() and not is_report_readonly_user(user),
        "local_report_folder_placeholder": local_report_folder_placeholder(),
        "report_check_rules": report_check_rules,
        "report_macros": report_macros,
        "can_manage_report_checks": manage_report_checks,
        "can_send_reports": can_send_reports(user),
        "is_report_readonly": is_report_readonly_user(user),
        "participation_request_sent_initial": request_sent_initial,
        "info_request_performers": info_request_performers,
        "info_request_projects": info_request_projects,
        "info_request_sent_initial": request_sent_initial,
        "contract_performers": contract_performers,
        "contract_projects": contract_projects,
        "payment_request_performers": payment_request_performers,
        "payment_request_projects": payment_request_projects,
        "payment_request_sent_initial": payment_request_sent_initial,
        "contract_request_sent_initial": request_sent_initial,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "user_is_direction_head": user_is_direction_head,
        "show_finding_adjustment_columns": show_finding_adjustment_columns(user),
        "is_expert": is_expert,
        "is_admin": is_admin,
        "has_active_smtp_connection": has_active_smtp_connection,
    }
    context.update(report_macros_pagination)
    context.update(report_submission_pagination)
    return context

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))

@login_required
@require_http_methods(["GET"])
def report_submission_table(request):
    return render(
        request,
        REPORT_SUBMISSION_TABLE_TEMPLATE,
        _performers_context(request.user, request),
    )


def _build_executor_grade_map():
    profiles = (
        ExpertProfile.objects
        .select_related("employee__user", "grade")
    )
    result = {}
    for p in profiles:
        u = p.employee.user
        parts = [u.last_name or "", u.first_name or "", p.employee.patronymic or ""]
        full_name = " ".join(part for part in parts if part)
        if not full_name:
            continue
        g = p.grade
        entry = {
            "country_id": p.country_id,
            "region_id": p.region_id,
        }
        if g:
            entry.update({
                "grade_name": g.grade_ru or g.grade_en,
                "qualification": g.qualification,
                "qualification_levels": g.qualification_levels,
                "base_rate_share": 0 if g.is_base_rate else g.base_rate_share,
            })
        result[full_name] = entry
    return result


def _build_executor_options_payload():
    employees = (
        Employee.objects
        .select_related("user", "expert_profile")
        .prefetch_related("expert_profile__specialties")
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )
    result = []
    for employee in employees:
        full_name = _employee_full_name(employee)
        if not full_name:
            continue
        try:
            profile = employee.expert_profile
        except ExpertProfile.DoesNotExist:
            profile = None
        result.append({
            "value": full_name,
            "label": full_name,
            "specialty_ids": [
                specialty.pk
                for specialty in profile.specialties.all()
                if specialty.pk
            ] if profile else [],
        })
    return result


def _build_living_wage_map():
    from classifiers_app.models import LivingWage
    today = timezone.now().date()
    wages = (
        LivingWage.objects
        .filter(
            Q(approval_date__lte=today),
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
        )
        .order_by("-approval_date")
    )
    result = {}
    for w in wages:
        key = f"{w.country_id}_{w.region_id}"
        if key not in result:
            result[key] = float(w.amount)
    return result


def _build_tariff_map():
    from policy_app.models import Tariff
    tariffs = Tariff.objects.select_related("product", "section").all()
    result = {}
    for t in tariffs:
        key = f"{t.product_id}_{t.section_id}"
        result[key] = float(t.base_rate_vpm)
    return result


def _build_tariff_hours_map():
    from policy_app.models import Tariff
    tariffs = Tariff.objects.select_related("product", "section").all()
    result = {}
    for t in tariffs:
        key = f"{t.product_id}_{t.section_id}"
        result[key] = t.service_hours or 0
    return result


def _build_direction_hourly_rate_map():
    """Base-rate hourly rate per OrgUnit (direction).

    Returns {str(org_unit_id): float(hourly_rate)} from Grades where
    is_base_rate=True, keyed by the grade creator's department.
    """
    from policy_app.models import Grade
    result = {}
    for g in (
        Grade.objects
        .filter(is_base_rate=True, hourly_rate__isnull=False)
        .select_related("created_by__employee_profile")
    ):
        emp = getattr(g.created_by, "employee_profile", None)
        if emp and emp.department_id:
            result[str(emp.department_id)] = float(g.hourly_rate)
    return result


def _performer_form_ctx(form, action: str, performer=None):
    regs = (
        ProjectRegistration.objects
        .select_related("type", "group_member")
        .prefetch_related(
            models.Prefetch(
                "product_links",
                queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
            )
        )
        .order_by("position", "id")
    )

    reg_map = {
        str(r.id): {
            "group": r.group_display,
            "type": r.type_short_display,
            "type_short": r.type_short_display,
            "type_id": r.type_id,
            "name": r.name,
        }
        for r in regs
    }
    assets_map = {
        str(r.id): [
            a for a in WorkVolume.objects
                     .filter(project=r)
                     .values_list("asset_name", flat=True)
                     .distinct()
            if a
        ]
        for r in regs
    }
    sections_map = {}
    for r in regs:
        ordered_sections = _ordered_registration_sections(r)
        if not ordered_sections:
            sections_map[str(r.id)] = []
            continue
        sections_map[str(r.id)] = [
            {
                "id": s.id,
                "label": _typical_section_option_label(s),
                "product_id": s.product_id,
                "pricing_method": (s.expertise_dir.pricing_method or "") if s.expertise_dir_id else "",
                "direction_id": _effective_direction_id(
                    s,
                    getattr(r, "group_member", None),
                ),
                "specialty_ids": [
                    link.specialty_id
                    for link in s.ranked_specialties.all()
                    if link.specialty_id
                ],
                "accounting_type": s.accounting_type or "",
            }
            for s in ordered_sections
        ]

    executor_grade_map = _build_executor_grade_map()
    executor_options = _build_executor_options_payload()
    living_wage_map = _build_living_wage_map()
    tariff_map = _build_tariff_map()
    tariff_hours_map = _build_tariff_hours_map()
    direction_hourly_rate_map = _build_direction_hourly_rate_map()
    section_code = ""
    if performer is not None:
        section_code = report_section_number(
            performer.registration,
            performer.asset_name or "",
            performer=performer,
        )

    return {
        "form": form,
        "action": action,
        "performer": performer,
        "section_code": section_code,
        "reg_map_json": json.dumps(reg_map, ensure_ascii=False),
        "assets_map_json": json.dumps(assets_map, ensure_ascii=False),
        "sections_map_json": json.dumps(sections_map, ensure_ascii=False),
        "section_codes_json": json.dumps(performer_section_code_ids_by_asset(), ensure_ascii=False),
        "executor_options_json": json.dumps(executor_options, ensure_ascii=False),
        "executor_grade_json": json.dumps(executor_grade_map, ensure_ascii=False),
        "living_wage_json": json.dumps(living_wage_map, ensure_ascii=False),
        "tariff_json": json.dumps(tariff_map, ensure_ascii=False),
        "tariff_hours_json": json.dumps(tariff_hours_map, ensure_ascii=False),
        "direction_hourly_rate_json": json.dumps(direction_hourly_rate_map, ensure_ascii=False),
    }

def _render_performers_updated(request):
    resp = render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp


def _performer_display_sort_key(performer):
    """Order of performer rows inside one registration, as rendered in the table."""
    return (
        performer.asset_name or "",
        getattr(performer, "section_code", "") or "",
        performer.position or 0,
        performer.pk or 0,
    )


def _performer_order_items_in_display_order(performers):
    """Rows for the order signature in the exact order the performers table renders them.

    The table groups rows by asset (and section code) rather than by raw ``position``,
    so the signature must be built from the same ordering on both the render and the
    save side; otherwise every bulk save of a multi-asset project would report a conflict.
    """
    items = annotate_performers_section_codes(list(performers))
    items.sort(key=lambda p: (p.registration_id or 0, *_performer_display_sort_key(p)))
    return [
        {
            "id": p.pk,
            "registration_id": p.registration_id,
            "position": p.position,
            "asset_name": p.asset_name or "",
        }
        for p in items
    ]


def _performer_order_signature_for_items(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item["registration_id"]].append(str(item["id"]))
    return "|".join(
        f"{registration_id}:{','.join(ids)}"
        for registration_id, ids in sorted(grouped.items(), key=lambda pair: pair[0] or 0)
    )


@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))

def _next_performer_position(registration_id: int | None = None):
    filters = {"registration_id": registration_id} if registration_id else None
    return _next_position(Performer, filters)


def _effective_direction_id(typical_section, group_member=None):
    """Подразделение руководителя по экспертизе раздела, режиму и организации проекта.

    Уровень 1 не даёт руководителя направления.
    """
    if not typical_section or not getattr(typical_section, "expertise_dir_id", None):
        return None
    from group_app.expertise_management import operation_unit

    unit = operation_unit(typical_section.expertise_dir_id, group_member)
    return unit.pk if unit else None


def _is_executor_locked(user, performer):
    """Исполнитель заблокирован:
    - проектный руководитель: если раздел привязан к (не-директорскому) направлению экспертизы.
    - «Руководитель направления»: если раздел НЕ относится к его направлению,
      или если запрос подтверждения отправлен и эксперт ещё не отклонил.
    Директорские направления (OrgUnit.level == 1) считаются отсутствующими.
    """
    try:
        emp = user.employee_profile
    except Exception:
        return False
    group_member = getattr(getattr(performer, "registration", None), "group_member", None)
    ts_direction_id = _effective_direction_id(performer.typical_section, group_member)
    if emp.role in (PROJECTS_HEAD_GROUP, PROJECTS_COORDINATOR_GROUP, DIRECTION_DIRECTOR_GROUP):
        if ts_direction_id:
            return True
        if (performer.participation_request_sent_at
                and performer.participation_response != Performer.ParticipationResponse.DECLINED):
            return True
        return False
    if emp.role == DEPARTMENT_HEAD_GROUP:
        if not ts_direction_id:
            return True
        if ts_direction_id != emp.department_id:
            return True
        dh_is_executor = performer.employee_id and performer.employee.user_id == user.id
        if dh_is_executor:
            return performer.participation_response == Performer.ParticipationResponse.CONFIRMED
        if (performer.participation_request_sent_at
                and performer.participation_response != Performer.ParticipationResponse.DECLINED):
            return True
        return False
    return False


def _parse_request_sent_at(raw_value: str):
    if not raw_value:
        return timezone.localtime().replace(second=0, microsecond=0)
    try:
        value = datetime.fromisoformat(raw_value)
    except ValueError:
        raise forms.ValidationError("Некорректная дата отправки запроса.")
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.replace(second=0, microsecond=0)


def _parse_performer_ids_from_request(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        raise ValueError("Не выбраны строки.")
    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError) as exc:
        raise ValueError("Передан некорректный список строк.") from exc
    if not performer_ids:
        raise ValueError("Не выбраны строки.")
    return performer_ids


def _participation_batch_queryset():
    return (
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "typical_section__service_block__expertise_direction",
            "employee",
            "employee__user",
            "currency",
        )
        .order_by("registration__number", "registration_id", "employee_id", "asset_name", "position", "id")
    )


def _load_participation_batch_performers(performer_ids, *, expand_existing_batches=False):
    performers = list(_participation_batch_queryset().filter(pk__in=performer_ids))
    if len(performers) != len(performer_ids):
        raise ValueError("Часть выбранных строк не найдена.")
    if expand_existing_batches:
        batch_ids = {p.participation_batch_id for p in performers if p.participation_batch_id}
        if batch_ids:
            expanded = list(_participation_batch_queryset().filter(participation_batch_id__in=batch_ids))
            by_id = {p.pk: p for p in performers}
            by_id.update({p.pk: p for p in expanded})
            performers = sorted(
                by_id.values(),
                key=lambda p: (
                    p.registration.number if p.registration_id else 0,
                    p.registration_id or 0,
                    p.employee_id or 0,
                    p.position or 0,
                    p.pk,
                ),
            )
    return performers


def _active_participation_notification_state(performer_ids, *, actor=None):
    if not performer_ids:
        return set(), set()
    from notifications_app.models import Notification, NotificationPerformerLink

    actor_id = getattr(actor, "pk", None)
    blocking_ids = set()
    actor_direction_ids = set()
    links = (
        NotificationPerformerLink.objects
        .select_related("notification")
        .filter(
            performer_id__in=performer_ids,
            notification__notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            notification__is_processed=False,
        )
    )
    for link in links:
        notification = link.notification
        payload = notification.payload if isinstance(notification.payload, dict) else {}
        is_actor_direction = (
            actor_id
            and notification.recipient_id == actor_id
            and payload.get("letter_template_type") == "direction_confirmation"
        )
        if is_actor_direction:
            actor_direction_ids.add(link.performer_id)
        else:
            blocking_ids.add(link.performer_id)
    return blocking_ids, actor_direction_ids


def _validate_participation_batch_rows(performers, *, require_unsent=True, actor=None):
    if not performers:
        raise ValueError("Не выбраны строки.")
    missing_employee = [p for p in performers if not p.employee_id]
    if missing_employee:
        names = ", ".join(sorted({(p.executor or f"#{p.pk}").strip() for p in missing_employee}))
        raise ValueError(f"Для части строк не найден сотрудник-получатель: {names}.")
    employee_ids = {p.employee_id for p in performers}
    if len(employee_ids) != 1:
        raise ValueError("Объединять можно только строки одного исполнителя или руководителя направления.")
    numbers = {p.registration.number for p in performers if p.registration_id}
    if len(numbers) != 1:
        raise ValueError("Объединять можно только строки внутри одного четырехзначного номера проекта.")
    if require_unsent:
        performer_ids = [p.pk for p in performers]
        blocking_active_ids, actor_direction_ids = _active_participation_notification_state(performer_ids, actor=actor)
        sent_rows = [
            p
            for p in performers
            if p.participation_request_sent_at and p.pk not in actor_direction_ids
        ]
        if sent_rows:
            raise ValueError("Нельзя объединять или разъединять строки, по которым уже отправлен запрос подтверждения.")
        if blocking_active_ids:
            raise ValueError("Нельзя менять батч, по которому уже есть активное уведомление.")


def _participation_base_batch_key(performer):
    if performer.participation_batch_id:
        return ("batch", str(performer.participation_batch_id))
    return ("registration", performer.registration_id, performer.employee_id)


def _round_up_to_hour(value):
    value = value.replace(second=0, microsecond=0)
    if value.minute == 0:
        return value
    return (value + timedelta(hours=1)).replace(minute=0)


def _share_contract_folder_for_nextcloud(performer, folder_path: str) -> list[str]:
    if not is_nextcloud_primary() or not folder_path:
        return []

    from django.contrib.auth import get_user_model

    from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
    from nextcloud_app.provisioning import ensure_nextcloud_account

    User = get_user_model()
    client = NextcloudApiClient()
    if not client.is_configured:
        return ["Nextcloud не настроен для выдачи доступа к папке проекта договора."]

    recipients = []
    seen_ids = set()

    executor_user = getattr(getattr(performer, "employee", None), "user", None)
    if executor_user and executor_user.is_active and executor_user.is_staff and executor_user.pk not in seen_ids:
        recipients.append((executor_user, 1))
        seen_ids.add(executor_user.pk)

    for lawyer in (
        User.objects
        .filter(groups__name=LAWYER_GROUP, is_active=True, is_staff=True)
        .order_by("pk")
        .distinct()
    ):
        if lawyer.pk in seen_ids:
            continue
        recipients.append((lawyer, 15))
        seen_ids.add(lawyer.pk)

    warnings = []
    for recipient, permissions in recipients:
        try:
            link = ensure_nextcloud_account(recipient, client=client)
            if not link or not link.nextcloud_user_id:
                warnings.append(
                    f"Не удалось выдать доступ к папке проекта договора пользователю {recipient.get_username()}."
                )
                continue
            client.ensure_user_share(
                client.username,
                folder_path,
                link.nextcloud_user_id,
                permissions=permissions,
            )
        except NextcloudApiError as exc:
            warnings.append(
                f"Не удалось выдать доступ к папке проекта договора пользователю {recipient.get_username()}: {exc}"
            )
    return warnings


def _normalize_nextcloud_contract_resource_path(path: str) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    if raw_path == "/":
        return "/"
    return f"/{raw_path.strip('/')}"


def _contract_resource_parent_path(path: str) -> str:
    normalized_path = _normalize_nextcloud_contract_resource_path(path)
    if not normalized_path or normalized_path == "/":
        return ""
    parent = normalized_path.rsplit("/", 1)[0]
    return parent or "/"


def _resolve_contract_project_nextcloud_file_id(path: str, *, attempts: int = 1, retry_delay: float = 0) -> str:
    if not is_nextcloud_primary() or not path:
        return ""

    from nextcloud_app.api import NextcloudApiClient, NextcloudApiError

    normalized_path = _normalize_nextcloud_contract_resource_path(path)
    parent_path = _contract_resource_parent_path(normalized_path)
    if not normalized_path or not parent_path:
        return ""

    client = NextcloudApiClient()
    if not client.is_configured:
        return ""

    safe_attempts = max(1, int(attempts or 1))
    for attempt in range(safe_attempts):
        try:
            items = client.list_resources(client.username, parent_path, limit=1000)
        except NextcloudApiError:
            items = []

        for item in items:
            item_path = _normalize_nextcloud_contract_resource_path(item.get("path") or "")
            if item_path == normalized_path:
                return str(item.get("file_id") or "").strip()

        if attempt < safe_attempts - 1 and retry_delay > 0:
            time.sleep(retry_delay)
    return ""


def _contract_docx_cloud_path(performer: Performer) -> str:
    folder = normalize_cloud_path(getattr(performer, "contract_project_disk_folder", "") or "")
    file_name = str(getattr(performer, "contract_file", "") or "").strip().strip("/")
    if not folder or not file_name:
        return ""
    return join_cloud_path(folder, file_name)


def _get_contract_cloud_user(user):
    if is_nextcloud_primary():
        return user or SimpleNamespace(username="nextcloud-system")
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    try:
        return get_any_connected_service_user()
    except CloudStorageNotReadyError as exc:
        raise RuntimeError(str(exc)) from exc


def _contract_group_member_for_performer(performer: Performer):
    return getattr(performer, "contract_group_member", None) or getattr(performer.registration, "group_member", None)


def _read_contract_image_file(file_field, *, label: str) -> bytes | None:
    file_name = str(getattr(file_field, "name", "") or "").strip()
    if not file_name:
        return None
    try:
        file_field.open("rb")
        try:
            data = file_field.read()
        finally:
            file_field.close()
    except Exception as exc:
        raise RuntimeError(f"Не удалось прочитать файл «{label}».") from exc
    return data or None


def _load_group_seal_bytes(group_member) -> bytes | None:
    if not group_member:
        return None
    return _read_contract_image_file(getattr(group_member, "seal_file", None), label="Печать")


def _load_director_facsimile_bytes(group_member) -> bytes | None:
    if not group_member:
        return None
    director_employee = (
        Employee.objects
        .select_related("user", "department", "department__company")
        .filter(role=DIRECTOR_GROUP, department__company_id=group_member.pk)
        .order_by("position", "id")
        .first()
    )
    if not director_employee:
        return None
    director_profile = (
        ExpertProfile.objects
        .prefetch_related("contract_details_records__citizenship_record")
        .filter(employee_id=director_employee.pk)
        .first()
    )
    if not director_profile:
        return None
    director_details = director_profile.default_contract_details(require_facsimile=True)
    if not director_details:
        return None
    return _read_contract_image_file(
        getattr(director_details, "facsimile_file", None),
        label="Факсимиле",
    )


def _load_performer_facsimile_bytes(performer: Performer) -> bytes | None:
    employee_id = getattr(performer, "employee_id", None)
    if not employee_id:
        employee = Performer.resolve_employee_from_executor(getattr(performer, "executor", "") or "")
        employee_id = getattr(employee, "pk", None)
    if not employee_id:
        return None

    expert_profile = (
        ExpertProfile.objects
        .prefetch_related("contract_details_records__citizenship_record")
        .filter(employee_id=employee_id)
        .first()
    )
    if not expert_profile:
        return None
    contract_details = expert_profile.default_contract_details(require_facsimile=True)
    if not contract_details:
        return None
    return _read_contract_image_file(
        getattr(contract_details, "facsimile_file", None),
        label="Факсимиле исполнителя",
    )


def _contract_performer_facsimile_missing_message(label: str, performer: Performer) -> str:
    executor_name = str(getattr(performer, "executor", "") or "").strip()
    details = f" ({executor_name})" if executor_name and executor_name != label else ""
    return f"Для {label}{details} не найдена факсимильная подпись исполнителя."


def _contract_image_bytes_for_placeholder(
    placeholder: str,
    group_member,
    *,
    performer: Performer | None = None,
) -> bytes | None:
    if placeholder == "[[seal]]":
        return _load_group_seal_bytes(group_member)
    if placeholder == "[[facsimile_imcm]]":
        return _load_director_facsimile_bytes(group_member)
    if placeholder == CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER and performer is not None:
        return _load_performer_facsimile_bytes(performer)
    return None


def _insert_contract_image_placeholders(
    file_data: bytes,
    performer: Performer,
    *,
    require_images: bool = False,
    include_performer_facsimile: bool = False,
) -> bytes:
    group_member = _contract_group_member_for_performer(performer)
    image_specs = CONTRACT_IMAGE_PLACEHOLDER_SPECS
    if include_performer_facsimile:
        image_specs = image_specs + (
            (CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER, "Подпись исполнителя"),
        )
    for placeholder, description in image_specs:
        if not document_contains_literal(file_data, placeholder):
            continue
        image_bytes = _contract_image_bytes_for_placeholder(
            placeholder,
            group_member,
            performer=performer,
        )
        if not image_bytes:
            if require_images:
                raise RuntimeError(f"{description} не найдена.")
            continue
        file_data = insert_floating_image_at_placeholder(
            file_data,
            image_bytes,
            placeholder=placeholder,
            x_relative_from=(
                "column"
                if placeholder in ("[[seal]]", CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER)
                else "page"
            ),
            x_align="center",
            relative_height=0 if placeholder == "[[seal]]" else 1,
        )
    return file_data


def _prepare_contract_docx_for_pdf(
    file_data: bytes,
    performer: Performer,
    *,
    include_performer_facsimile: bool = False,
) -> bytes:
    file_data = _insert_contract_image_placeholders(
        file_data,
        performer,
        require_images=True,
        include_performer_facsimile=include_performer_facsimile,
    )
    if not include_performer_facsimile:
        file_data = remove_literal_placeholders(
            file_data,
            (CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER,),
        )
    return clear_text_highlighting(file_data)


def _load_existing_contract_docx_bytes(user, performer: Performer) -> bytes:
    if not str(getattr(performer, "contract_file", "") or "").strip():
        raise RuntimeError("Для договора не указан DOCX-файл.")
    docx_path = _contract_docx_cloud_path(performer)
    if not docx_path:
        raise RuntimeError("Для договора не задан путь к DOCX-файлу.")

    cloud_user = _get_contract_cloud_user(user)
    if not cloud_user:
        raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для чтения DOCX.")

    _mime_type, docx_bytes = cloud_download_file(cloud_user, docx_path)
    if docx_bytes:
        return docx_bytes
    raise RuntimeError("Не удалось получить DOCX проекта договора.")


def _build_contract_docx_source_token(
    performer: Performer,
    *,
    include_performer_facsimile: bool = False,
) -> str:
    payload = {
        "performer_id": int(performer.pk),
        "contract_file": str(getattr(performer, "contract_file", "") or "").strip(),
        "contract_project_disk_folder": str(getattr(performer, "contract_project_disk_folder", "") or "").strip(),
        "include_performer_facsimile": bool(include_performer_facsimile),
    }
    return signing.dumps(payload, salt=CONTRACT_DOCX_SOURCE_TOKEN_SALT, compress=True)


def _get_contract_docx_source_token_payload(performer: Performer, token: str) -> dict[str, object] | None:
    try:
        payload = signing.loads(
            str(token or "").strip(),
            salt=CONTRACT_DOCX_SOURCE_TOKEN_SALT,
            max_age=300,
        )
    except signing.BadSignature:
        return None

    if not (
        payload.get("performer_id") == performer.pk
        and payload.get("contract_file") == str(getattr(performer, "contract_file", "") or "").strip()
        and payload.get("contract_project_disk_folder")
        == str(getattr(performer, "contract_project_disk_folder", "") or "").strip()
    ):
        return None
    return payload


def _build_contract_docx_source_url(
    request,
    performer: Performer,
    *,
    include_performer_facsimile: bool = False,
) -> str:
    token = _build_contract_docx_source_token(
        performer,
        include_performer_facsimile=include_performer_facsimile,
    )
    path = reverse("contract_onlyoffice_docx_source", args=[performer.pk])
    return request.build_absolute_uri(f"{path}?token={quote(token, safe='')}")


def _build_contract_pdf_paths(performer: Performer, *, signed: bool = False) -> dict[str, str]:
    folder = normalize_cloud_path(getattr(performer, "contract_project_disk_folder", "") or "")
    docx_name = str(getattr(performer, "contract_file", "") or "").strip()
    if not folder:
        raise RuntimeError("Для договора не задана папка в облачном хранилище.")
    if not docx_name:
        raise RuntimeError("Для договора не указан DOCX-файл.")
    pdf_stem = os.path.splitext(docx_name)[0] or "Договор"
    pdf_name = f"{pdf_stem}_п.pdf" if signed else f"{pdf_stem}.pdf"
    return {
        "pdf_name": pdf_name,
        "pdf_path": join_cloud_path(folder, pdf_name),
    }


def _store_generated_contract_pdf(
    user,
    performer: Performer,
    pdf_bytes: bytes,
    *,
    signed: bool = False,
) -> dict[str, str]:
    paths = _build_contract_pdf_paths(performer, signed=signed)
    cloud_user = _get_contract_cloud_user(user)
    if not cloud_user:
        raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для загрузки PDF.")
    if not cloud_upload_file(cloud_user, paths["pdf_path"], pdf_bytes):
        raise RuntimeError("Не удалось загрузить PDF в папку проекта договора.")

    public_url = ""
    try:
        public_url = cloud_publish_resource(cloud_user, paths["pdf_path"]) or ""
    except Exception:
        public_url = ""
    if not public_url:
        raise RuntimeError("Не удалось создать публичную ссылку на PDF договора.")

    return {
        "pdf_name": paths["pdf_name"],
        "pdf_path": paths["pdf_path"],
        "pdf_url": public_url,
        "pdf_file_id": _resolve_contract_project_nextcloud_file_id(paths["pdf_path"]),
    }


@require_GET
def contract_onlyoffice_docx_source(request, pk: int):
    performer = get_object_or_404(Performer, pk=pk)
    token = str(request.GET.get("token") or "").strip()
    token_payload = _get_contract_docx_source_token_payload(performer, token)
    if token_payload is None:
        return HttpResponseForbidden("Недействительная ссылка на DOCX-файл договора.")

    try:
        docx_bytes = _load_existing_contract_docx_bytes(
            request.user if getattr(request.user, "is_authenticated", False) else None,
            performer,
        )
        docx_bytes = _prepare_contract_docx_for_pdf(
            docx_bytes,
            performer,
            include_performer_facsimile=bool(token_payload.get("include_performer_facsimile")),
        )
    except RuntimeError as exc:
        raise Http404(str(exc))

    file_name = str(getattr(performer, "contract_file", "") or "").strip() or "contract.docx"
    response = HttpResponse(docx_bytes, content_type=DOCX_CONTENT_TYPE)
    response["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(file_name)}"
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def report_render_docx_source(request, key: str):
    """Отчёт, отданный ONLYOFFICE Document Server для отрисовки раскладки строк."""
    from .docx_render import load_render_source, render_source_token_matches

    token = str(request.GET.get("token") or "").strip()
    if not render_source_token_matches(key, token):
        return HttpResponseForbidden("Недействительная ссылка на DOCX-файл отчёта.")
    docx_bytes = load_render_source(key)
    if docx_bytes is None:
        raise Http404("DOCX-файл отчёта для отрисовки не найден.")
    response = HttpResponse(docx_bytes, content_type=DOCX_CONTENT_TYPE)
    response["Content-Disposition"] = "inline; filename=\"report.docx\""
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_http_methods(["GET", "POST"])
def performer_form_create(request):
    """
    GET:  вернуть форму в модалку (с JSON-картами и привязанными server-side зависимостями).
    POST: если форма невалидна — вернуть её обратно (200), если валидна — 204 + HX-Trigger.
    """
    if request.method == "GET":
        form = PerformerForm()
        _bind_dynamic_performer_fields(form)  # чтобы селекты были заполнены сразу
        return render(request, PERF_FORM_TEMPLATE, _performer_form_ctx(form, "create"))

    # POST
    form = PerformerForm(request.POST)
    _bind_dynamic_performer_fields(form, data=request.POST)  # ВАЖНО: привязать перед is_valid()

    if not form.is_valid():
        # Статус 200 — чтобы htmx спокойно перерисовал содержимое модалки шаблоном формы с ошибками
        return render(
            request,
            PERF_FORM_TEMPLATE,
            _performer_form_ctx(form, "create"),
            status=200,
        )

    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_performer_position(obj.registration_id)
    obj.save()

    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT  # "performers-updated"
    return resp

@login_required
@require_http_methods(["GET", "POST"])
def performer_form_edit(request, pk: int):
    """
    GET:  отдать форму редактирования в модалку (с картами и привязками).
    POST: если невалидно — вернуть форму (200); если ок — 204 + HX-Trigger.
    """
    p = get_object_or_404(Performer.objects.select_related("typical_section", "typical_section__service_block__expertise_direction", "employee", "employee__user"), pk=pk)
    executor_locked = _is_executor_locked(request.user, p)

    if request.method == "GET":
        form = PerformerForm(instance=p)
        _bind_dynamic_performer_fields(form, instance=p)
        if executor_locked:
            attrs = form.fields["executor"].widget.attrs
            attrs["readonly"] = True
            attrs["class"] = attrs.get("class", "") + " readonly-field"
        ctx = _performer_form_ctx(form, "edit", performer=p)
        ctx["executor_locked"] = executor_locked
        return render(request, PERF_FORM_TEMPLATE, ctx)

    # POST
    form = PerformerForm(request.POST, instance=p)
    _bind_dynamic_performer_fields(form, data=request.POST, instance=p)

    if not form.is_valid():
        if executor_locked:
            attrs = form.fields["executor"].widget.attrs
            attrs["readonly"] = True
            attrs["class"] = attrs.get("class", "") + " readonly-field"
        ctx = _performer_form_ctx(form, "edit", performer=p)
        ctx["executor_locked"] = executor_locked
        return render(request, PERF_FORM_TEMPLATE, ctx, status=200)

    form.save()
    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp


@login_required
@user_passes_test(staff_required)
@require_POST
def participation_batch_merge(request):
    try:
        performer_ids = _parse_performer_ids_from_request(request)
        performers = _load_participation_batch_performers(performer_ids, expand_existing_batches=True)
        _validate_participation_batch_rows(performers, require_unsent=True, actor=request.user)
        base_keys = {_participation_base_batch_key(p) for p in performers}
        if len(base_keys) <= 1:
            raise ValueError("Для объединения выберите несколько батчей одного получателя внутри одного номера проекта.")
        batch_id = uuid.uuid4()
        ids = [p.pk for p in performers]
        updated = Performer.objects.filter(pk__in=ids).update(participation_batch_id=batch_id)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "batch_id": str(batch_id),
            "performer_ids": ids,
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def participation_batch_split(request):
    try:
        performer_ids = _parse_performer_ids_from_request(request)
        selected = _load_participation_batch_performers(performer_ids)
        batch_ids = {p.participation_batch_id for p in selected if p.participation_batch_id}
        if len(batch_ids) != 1:
            raise ValueError("Для разъединения выберите один объединенный батч.")
        performers = list(_participation_batch_queryset().filter(participation_batch_id__in=batch_ids))
        _validate_participation_batch_rows(performers, require_unsent=True, actor=request.user)
        ids = [p.pk for p in performers]
        updated = Performer.objects.filter(pk__in=ids).update(participation_batch_id=None)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "performer_ids": ids,
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def participation_request(request):
    try:
        performer_ids = _parse_performer_ids_from_request(request)
    except ValueError as exc:
        message = str(exc)
        if message == "Не выбраны строки.":
            message = "Не выбраны строки для запроса."
        return JsonResponse({"ok": False, "error": message}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    try:
        selected_performers = _load_participation_batch_performers(
            performer_ids,
            expand_existing_batches=True,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    performer_ids = [performer.pk for performer in selected_performers]

    try:
        with transaction.atomic():
            notification_result = create_participation_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
                delivery_channels=delivery_channels,
            )
            updated = Performer.objects.filter(pk__in=performer_ids).update(
                participation_request_sent_at=request_sent_at,
                participation_deadline_at=deadline_at,
                participation_response="",
                participation_response_at=None,
            )
            from worktime_app.services import ensure_direction_head_request_assignments

            ensure_direction_head_request_assignments(selected_performers)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
            "delivery_channels": list(notification_result["delivery_channels"]),
            "email_delivery": notification_result["email_delivery"],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_request(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для отправки."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    selected_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
            "currency",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)
    selected_performers = _expand_contract_batch_performers(selected_performers)

    try:
        with transaction.atomic():
            notification_result = create_contract_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
                delivery_channels=delivery_channels,
            )
            all_ids = [p.pk for p in selected_performers]
            updated = Performer.objects.filter(pk__in=all_ids).update(
                contract_sent_at=request_sent_at,
                contract_deadline_at=deadline_at,
                contract_signing_note="Отправлен проект договора",
            )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
            "delivery_channels": list(notification_result["delivery_channels"]),
            "email_delivery": notification_result["email_delivery"],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def info_request_approval(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для запроса."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        duration_hours = int(request.POST.get("duration_hours") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Срок должен быть целым числом часов."}, status=400)
    if duration_hours <= 0:
        return JsonResponse({"ok": False, "error": "Срок должен быть больше нуля."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    deadline_at = _round_up_to_hour(request_sent_at + timedelta(hours=duration_hours))
    selected_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)
    if any(
        getattr(performer.typical_section, "accounting_type", None) != "Разделы"
        for performer in selected_performers
    ):
        return JsonResponse(
            {"ok": False, "error": "Запрос информации доступен только для строк с типом учета «Разделы»."},
            status=400,
        )

    try:
        with transaction.atomic():
            create_info_request_notifications(
                performers=selected_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                deadline_at=deadline_at,
                duration_hours=duration_hours,
            )
            updated = Performer.objects.filter(pk__in=performer_ids).update(
                info_request_sent_at=request_sent_at,
                info_request_deadline_at=deadline_at,
                info_approval_status="",
                info_approval_at=None,
            )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "deadline_at": timezone.localtime(deadline_at).strftime("%d.%m.%Y %H:%M"),
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def revoke_info_request_approval(request):
    if not _is_admin_user(request.user):
        return JsonResponse({"ok": False, "error": "Действие доступно только администратору."}, status=403)

    raw_ids = (
        request.POST.getlist("performer_ids[]")
        or request.POST.getlist("performer_ids")
        or [request.POST.get("performer_id")]
    )
    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value or "").strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)
    if not performer_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для отката."}, status=400)

    from checklists_app.models import InfoRequestSectionApproval
    from notifications_app.models import Notification

    with transaction.atomic():
        selected_performers = list(
            Performer.objects
            .select_for_update()
            .filter(pk__in=performer_ids)
        )
        if len(selected_performers) != len(performer_ids):
            return JsonResponse({"ok": False, "error": "Одна или несколько выбранных строк не найдены."}, status=404)
        if any(p.info_approval_status != Performer.InfoApprovalStatus.APPROVED for p in selected_performers):
            return JsonResponse({"ok": False, "error": "Откат доступен только для согласованных строк."}, status=400)

        project_ids = {p.registration_id for p in selected_performers}
        employee_ids = {p.employee_id for p in selected_performers}
        if len(project_ids) != 1:
            return JsonResponse({"ok": False, "error": "Выберите строки в рамках одного проекта."}, status=400)
        if len(employee_ids) != 1:
            return JsonResponse({"ok": False, "error": "Выберите строки одного исполнителя."}, status=400)

        performer = selected_performers[0]
        if not performer.employee_id or not getattr(performer.employee, "user_id", None):
            return JsonResponse({"ok": False, "error": "У выбранных строк не найден эксперт."}, status=400)

        expert_user = performer.employee.user
        project = performer.registration
        target_performers = list(
            Performer.objects
            .select_for_update()
            .filter(
                registration=project,
                employee=performer.employee,
                info_approval_status=Performer.InfoApprovalStatus.APPROVED,
            )
        )
        section_ids = {p.typical_section_id for p in target_performers if p.typical_section_id}
        if not section_ids:
            return JsonResponse({"ok": False, "error": "У выбранных строк не указаны типовые разделы."}, status=400)

        current_notification_ids = set()
        for target in target_performers:
            ids = (
                Notification.objects
                .filter(
                    notification_type=Notification.NotificationType.PROJECT_INFO_REQUEST_APPROVAL,
                    project=project,
                    recipient=expert_user,
                    sent_at=target.info_request_sent_at,
                    deadline_at=target.info_request_deadline_at,
                    performer_links__performer=target,
                )
                .values_list("pk", flat=True)
                .distinct()
            )
            current_notification_ids.update(ids)
        if not current_notification_ids:
            return JsonResponse({"ok": False, "error": "Не найден связанный запрос согласования."}, status=400)

        current_notifications = list(
            Notification.objects
            .select_for_update()
            .filter(pk__in=current_notification_ids)
        )
        notification_ids = [notification.pk for notification in current_notifications]
        approver_ids = {expert_user.pk}
        approver_ids.update(
            notification.action_by_id
            for notification in current_notifications
            if notification.action_by_id
        )
        InfoRequestSectionApproval.objects.filter(
            project=project,
            section_id__in=section_ids,
            approved_by_id__in=approver_ids,
        ).delete()
        performers_updated = (
            Performer.objects
            .select_for_update()
            .filter(pk__in=[p.pk for p in target_performers])
            .update(
                info_approval_status="",
                info_approval_at=None,
            )
        )
        notifications_updated = Notification.objects.filter(pk__in=notification_ids).update(
            is_processed=False,
            action_at=None,
            action_by=None,
            action_choice="",
            updated_at=timezone.now(),
        )

    return JsonResponse({
        "ok": True,
        "performers_updated": performers_updated,
        "notifications_updated": notifications_updated,
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def payment_request(request):
    if _confirmed_project_ids_for_expert(request.user) is not None:
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)

    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для отправки заявки."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    try:
        request_sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    from projects_app.services.payment_request import (
        allocate_payment_request_number,
        payment_request_sender_display,
        payment_request_stage,
    )

    letter_performers = list(
        Performer.objects
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
            "currency",
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(letter_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    advance_letter_performers = []
    final_letter_performers = []
    row_updates = []
    for performer in letter_performers:
        stage = payment_request_stage(performer)
        if stage is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Часть выбранных строк уже полностью обработана.",
                },
                status=400,
            )
        row_updates.append({"id": performer.pk, "stage": stage})
        if stage == "advance":
            advance_letter_performers.append(performer)
        else:
            final_letter_performers.append(performer)

    expanded_advance = (
        _expand_contract_batch_performers(advance_letter_performers)
        if advance_letter_performers
        else []
    )
    expanded_final = (
        _expand_contract_batch_performers(final_letter_performers)
        if final_letter_performers
        else []
    )
    selected_performers = []
    seen_performer_ids = set()
    for performer in expanded_advance + expanded_final:
        if performer.pk in seen_performer_ids:
            continue
        seen_performer_ids.add(performer.pk)
        selected_performers.append(performer)

    sender_display = payment_request_sender_display(request.user)

    try:
        with transaction.atomic():
            request_number = allocate_payment_request_number()
            notification_result = create_payment_request_notifications(
                performers=selected_performers,
                letter_performers=letter_performers,
                sender=request.user,
                request_sent_at=request_sent_at,
                request_number=request_number,
                delivery_channels=delivery_channels,
            )
            updated = 0
            if expanded_advance:
                advance_ids = [performer.pk for performer in expanded_advance]
                updated += Performer.objects.filter(pk__in=advance_ids).update(
                    advance_payment_request_sent_at=request_sent_at,
                    advance_payment_request_number=request_number,
                    advance_payment_request_sender=sender_display,
                )
            if expanded_final:
                final_ids = [performer.pk for performer in expanded_final]
                updated += Performer.objects.filter(pk__in=final_ids).update(
                    final_payment_request_sent_at=request_sent_at,
                    final_payment_request_number=request_number,
                    final_payment_request_sender=sender_display,
                )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "request_number": request_number,
            "row_updates": row_updates,
            "row_ids": performer_ids,
            "sender_display": sender_display,
            "request_sent_at": timezone.localtime(request_sent_at).strftime("%d.%m.%Y %H:%M"),
            "delivery_channels": list(notification_result["delivery_channels"]),
            "email_delivery": notification_result["email_delivery"],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def payment_paid_toggle(request):
    if _confirmed_project_ids_for_expert(request.user) is not None:
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)

    try:
        performer_id = int(str(request.POST.get("performer_id", "")).strip())
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный идентификатор строки."}, status=400)

    kind = str(request.POST.get("kind", "")).strip()
    if kind not in {"advance", "final"}:
        return JsonResponse({"ok": False, "error": "Некорректный тип оплаты."}, status=400)

    raw_paid = str(request.POST.get("paid", "")).strip()
    if raw_paid not in {"0", "1"}:
        return JsonResponse({"ok": False, "error": "Некорректное значение оплаты."}, status=400)
    paid = raw_paid == "1"

    performer = get_object_or_404(Performer, pk=performer_id)

    field_name = "advance_payment_paid" if kind == "advance" else "final_payment_paid"
    paid_at_field = "advance_payment_paid_at" if kind == "advance" else "final_payment_paid_at"
    paid_at = timezone.now() if paid else None
    payment_performers = _expand_contract_batch_performers([performer])
    performer_ids = [item.pk for item in payment_performers]
    with transaction.atomic():
        updated = Performer.objects.filter(pk__in=performer_ids).update(
            **{
                field_name: paid,
                paid_at_field: paid_at,
            }
        )
        notification_sync = sync_payment_request_notifications_for_performers(
            performer_ids=performer_ids,
            actor=request.user,
        )

    return JsonResponse({
        "ok": True,
        "id": performer.pk,
        "row_ids": performer_ids,
        "kind": kind,
        "paid": paid,
        "paid_at": (
            timezone.localtime(paid_at).strftime("%d.%m.%Y %H:%M")
            if paid_at
            else ""
        ),
        "updated": updated,
        "notifications_changed": notification_sync["changed"],
    })


def _performer_lock_order_items(registration_id=None, ordered_ids=None):
    qs = (
        Performer.objects
        .select_related("typical_section")
        .order_by("registration_id", "position", "id")
    )
    if registration_id:
        qs = qs.filter(registration_id=registration_id)
    rows = [
        {
            "id": item.pk,
            "registration_id": item.registration_id,
            "asset_name": item.asset_name or "",
            "accounting_type": getattr(item.typical_section, "accounting_type", "") or "",
        }
        for item in qs
    ]
    if ordered_ids is None:
        return rows
    by_id = {row["id"]: row for row in rows}
    return [by_id[item_id] for item_id in ordered_ids if item_id in by_id]


def _performer_locked_section_order_changed(registration_id, current_ids, desired_ids) -> bool:
    current = locked_report_section_sequences(
        _performer_lock_order_items(registration_id=registration_id, ordered_ids=current_ids)
    )
    desired = locked_report_section_sequences(
        _performer_lock_order_items(registration_id=registration_id, ordered_ids=desired_ids)
    )
    return current != desired


@login_required
@require_POST
def performer_delete(request, pk: int):
    p = get_object_or_404(Performer.objects.select_related("typical_section"), pk=pk)
    if not performer_report_section_locked(p) and not performer_has_report_uploads(p):
        p.delete()
    return _render_performers_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def performer_row_order(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Некорректный формат порядка исполнителей."}, status=400)

    raw_ids = payload.get("ordered_performer_ids") or []
    try:
        ordered_performer_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Порядок исполнителей содержит некорректные идентификаторы."}, status=400)
    if len(ordered_performer_ids) != len(set(ordered_performer_ids)):
        return JsonResponse({"ok": False, "error": "Порядок исполнителей содержит дубли."}, status=400)

    base_signature = str(payload.get("base_order_signature") or "")
    with transaction.atomic():
        current_items = _performer_order_items_in_display_order(
            Performer.objects
            .select_for_update(of=("self",))
            .select_related("typical_section")
            .order_by("registration_id", "position", "id")
        )
        current_ids = [item["id"] for item in current_items]
        current_signature = _performer_order_signature_for_items(current_items)
        current_registration_by_id = {
            item["id"]: item["registration_id"]
            for item in current_items
        }
        desired_items = [
            {"id": performer_id, "registration_id": current_registration_by_id.get(performer_id)}
            for performer_id in ordered_performer_ids
        ]
        desired_signature = _performer_order_signature_for_items(desired_items)

        conflict_payload = {
            "ok": False,
            "error": "Порядок исполнителей был изменен. Таблица будет обновлена.",
            "current_performer_ids": current_ids,
            "order_signature": current_signature,
        }
        if base_signature and base_signature != current_signature:
            if desired_signature == current_signature:
                return JsonResponse({"ok": True, "order_signature": current_signature})
            return JsonResponse(conflict_payload, status=409)
        if set(ordered_performer_ids) != set(current_ids):
            return JsonResponse(conflict_payload, status=409)

        current_lock_items = _performer_lock_order_items(ordered_ids=current_ids)
        desired_lock_items = _performer_lock_order_items(ordered_ids=ordered_performer_ids)
        if locked_report_section_sequences(current_lock_items) != locked_report_section_sequences(desired_lock_items):
            return JsonResponse({
                "ok": False,
                "error": "После создания рабочего пространства нельзя менять порядок разделов.",
                "current_performer_ids": current_ids,
                "order_signature": current_signature,
            }, status=409)

        grouped_ids = defaultdict(list)
        for performer_id in ordered_performer_ids:
            grouped_ids[current_registration_by_id[performer_id]].append(performer_id)
        for performer_ids in grouped_ids.values():
            for idx, performer_id in enumerate(performer_ids, start=1):
                Performer.objects.filter(pk=performer_id).update(position=idx)

    return JsonResponse({"ok": True, "order_signature": desired_signature})


def _normalize_performer_positions(registration_id: int | None = None):
    qs = Performer.objects.values("id", "position", "registration_id")
    if registration_id:
        items = list(qs.filter(registration_id=registration_id).order_by("position", "id"))
        for i, it in enumerate(items, start=1):
            if it["position"] != i:
                Performer.objects.filter(pk=it["id"]).update(position=i)
        return

    cur_registration_id = None
    buf = []
    for it in qs.order_by("registration_id", "position", "id"):
        if cur_registration_id is None:
            cur_registration_id = it["registration_id"]
        if it["registration_id"] != cur_registration_id:
            for i, b in enumerate(buf, start=1):
                if b["position"] != i:
                    Performer.objects.filter(pk=b["id"]).update(position=i)
            cur_registration_id, buf = it["registration_id"], [it]
        else:
            buf.append(it)
    for i, b in enumerate(buf, start=1):
        if b["position"] != i:
            Performer.objects.filter(pk=b["id"]).update(position=i)

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_up(request, pk: int):
    performer = Performer.objects.filter(pk=pk).values("registration_id").first()
    if not performer:
        raise Http404
    registration_id = performer["registration_id"]
    _normalize_performer_positions(registration_id)
    items = list(
        Performer.objects
        .filter(registration_id=registration_id)
        .order_by("position", "id")
        .values("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it["id"] == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx-1]
        desired_ids = [item["id"] for item in items]
        desired_ids[idx], desired_ids[idx - 1] = desired_ids[idx - 1], desired_ids[idx]
        current_ids = [item["id"] for item in items]
        if not _performer_locked_section_order_changed(registration_id, current_ids, desired_ids):
            Performer.objects.filter(pk=cur["id"]).update(position=prev["position"])
            Performer.objects.filter(pk=prev["id"]).update(position=cur["position"])
            _normalize_performer_positions(registration_id)
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_down(request, pk: int):
    performer = Performer.objects.filter(pk=pk).values("registration_id").first()
    if not performer:
        raise Http404
    registration_id = performer["registration_id"]
    _normalize_performer_positions(registration_id)
    items = list(
        Performer.objects
        .filter(registration_id=registration_id)
        .order_by("position", "id")
        .values("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it["id"] == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx+1]
        desired_ids = [item["id"] for item in items]
        desired_ids[idx], desired_ids[idx + 1] = desired_ids[idx + 1], desired_ids[idx]
        current_ids = [item["id"] for item in items]
        if not _performer_locked_section_order_changed(registration_id, current_ids, desired_ids):
            Performer.objects.filter(pk=cur["id"]).update(position=nxt["position"])
            Performer.objects.filter(pk=nxt["id"]).update(position=cur["position"])
            _normalize_performer_positions(registration_id)
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))

@login_required
@require_GET
def legal_entity_work_deps(request):
    wid = request.GET.get("work_item")
    try:
        wid = int(wid)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False})

    work = (
        WorkVolume.objects
        .select_related("project")
        .filter(pk=wid)
        .first()
    )
    if not work:
        return JsonResponse({"ok": False})

    return JsonResponse({
        "ok": True,
        "project": getattr(work.project, "short_uid", ""),
        "type": getattr(work.project, "type_short_display", "") or work.type or "",
        "name": work.name or "",
        "country_id": work.country_id or "",
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def create_workspace(request):
    project_id = request.POST.get("project_id")
    if not project_id:
        return JsonResponse({"ok": False, "error": "Не выбран проект."}, status=400)

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный ID проекта."}, status=400)

    project = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(pk=project_id)
        .first()
    )
    if not project:
        return JsonResponse({"ok": False, "error": "Проект не найден."}, status=404)

    try:
        result = routed_create_project_workspace(request.user, project)
    except CloudStorageNotReadyError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    if not result.ok:
        return JsonResponse({"ok": False, "error": result.message}, status=400)

    return JsonResponse({"ok": True, "message": result.message})


@login_required
@user_passes_test(staff_required)
@require_POST
def create_registration_workspace(request):
    project_id = request.POST.get("project_id")
    if not project_id:
        return JsonResponse({"ok": False, "error": "Не выбран проект."}, status=400)

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный ID проекта."}, status=400)

    project = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(pk=project_id)
        .first()
    )
    if not project:
        return JsonResponse({"ok": False, "error": "Проект не найден."}, status=404)

    workspace_result_class = get_workspace_result_class()

    MIN_CHUNK = 256

    def _padded(line):
        """Pad each line to MIN_CHUNK bytes so proxies flush immediately."""
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        try:
            iterator = routed_create_basic_project_workspace_stream(request.user, project)
            for item in iterator:
                if isinstance(item, workspace_result_class):
                    if item.ok:
                        yield _padded(json.dumps({"ok": True, "message": item.message}) + "\n")
                    else:
                        yield _padded(json.dumps({"ok": False, "error": item.message}) + "\n")
                else:
                    yield _padded(json.dumps(item) + "\n")
        except CloudStorageNotReadyError as exc:
            yield _padded(json.dumps({"ok": False, "error": str(exc)}) + "\n")

    resp = StreamingHttpResponse(_stream(), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache, no-store"
    resp["X-Accel-Buffering"] = "no"
    return resp


def _get_effective_folders(user):
    """Return (queryset, is_custom) — user-specific if exists, else global (user=None)."""
    user_qs = RegistrationWorkspaceFolder.objects.filter(user=user)
    if user_qs.exists():
        return user_qs, True
    return RegistrationWorkspaceFolder.objects.filter(user__isnull=True), False


@login_required
@user_passes_test(staff_required)
@require_GET
def workspace_folders_list(request):
    qs, is_custom = _get_effective_folders(request.user)
    folders = list(qs.values("id", "level", "name", "position", "role"))
    return JsonResponse(
        {
            "folders": folders,
            "is_custom": is_custom,
            "storage_label": get_primary_cloud_storage_label(),
            "role_choices": [
                {"value": value, "label": label}
                for value, label in RegistrationWorkspaceFolder.ROLE_CHOICES
            ],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def workspace_folders_save(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    rows = data.get("folders", [])
    if not isinstance(rows, list):
        return JsonResponse({"ok": False, "error": "Некорректный формат."}, status=400)

    owner = None if request.user.is_superuser else request.user

    try:
        named_rows = [row for row in rows if (row.get("name") or "").strip()]
        validate_workspace_folder_roles(named_rows)
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    objects = []
    for i, row in enumerate(rows):
        level = row.get("level", 1)
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if level not in (1, 2, 3):
            level = 1
        role = (row.get("role") or "").strip()
        objects.append(
            RegistrationWorkspaceFolder(
                user=owner,
                level=level,
                name=name,
                position=i,
                role=role,
            )
        )

    with transaction.atomic():
        RegistrationWorkspaceFolder.objects.filter(user=owner).delete()
        RegistrationWorkspaceFolder.objects.bulk_create(objects)

    return JsonResponse({"ok": True, "is_custom": owner is not None and len(objects) > 0})


@login_required
@user_passes_test(staff_required)
@require_POST
def workspace_folders_reset(request):
    RegistrationWorkspaceFolder.objects.filter(user=request.user).delete()
    qs, is_custom = _get_effective_folders(request.user)
    folders = list(qs.values("id", "level", "name", "position", "role"))
    return JsonResponse({"ok": True, "folders": folders, "is_custom": is_custom})


def _render_report_submission_row(request, row):
    annotate_report_submission_rows(request.user, [row])
    return str(
        render_to_string(
            "projects_app/report_submission_row.html",
            {
                "row": row,
                "is_expert": is_expert_user(request.user),
                "is_report_readonly": is_report_readonly_user(request.user),
                "can_send_reports": can_send_reports(request.user),
                "is_admin": is_admin_user(request.user),
                "show_finding_adjustment_columns": show_finding_adjustment_columns(request.user),
            },
            request=request,
        )
    )


def _report_finding_groups_payload(upload, source="calculated"):
    groups = report_finding_groups(upload, source=source)
    groups["context"] = report_finding_context(
        getattr(upload, "registration", None),
        getattr(upload, "executor", ""),
        getattr(upload, "asset_name", ""),
        report_upload_section_label(upload),
        format_report_version(getattr(upload, "version", 0)),
    )
    return groups


def _report_public_finding_groups_payload(upload):
    from .report_submission import finding_correction_active

    source = "corrected" if finding_correction_active(upload) else "calculated"
    return _report_finding_groups_payload(upload, source)


def _report_finding_edit_groups_payload(upload):
    groups = _report_finding_groups_payload(upload)
    return report_finding_edit_payload(upload, groups)


def _report_upload_fallback_payload(upload, viewer=None, **extra):
    payload = {
        "ok": True,
        "file_name": getattr(upload, "file_name", "") or "",
        "download_url": reverse("report_file_download", args=[upload.pk]),
        "storage_label": "облачное хранилище",
        "local": False,
        "version": int(getattr(upload, "version", 0) or 0),
        "version_display": format_report_version(getattr(upload, "version", 0)),
        "has_history": False,
        "previous_row_html": "",
        "check_status": getattr(upload, "check_status", "") or "",
        "check_progress": getattr(upload, "check_progress_label", "") or "",
        "check_finding_count": getattr(upload, "check_finding_count", 0) or 0,
        "check_error": getattr(upload, "check_error", "") or "",
        "check_error_reason": report_check_error_reason(getattr(upload, "check_error", "") or ""),
        "check_file_name": getattr(upload, "check_file_name", "") or "",
        "check_download_url": "",
        "review_file_name": getattr(upload, "review_file_name", "") or "",
        "review_download_url": "",
        "sent_at": format_report_datetime(getattr(upload, "sent_at", None)),
        "checked_at": format_report_datetime(getattr(upload, "checked_at", None)),
        "uploaded_at": format_report_datetime(getattr(upload, "uploaded_at", None)),
        "upload_id": getattr(upload, "pk", None) or "",
        "finding_threshold": report_acceptance_threshold(upload),
        "finding_count_display": format_report_public_finding_count(upload),
        "calculated_count_display": format_report_finding_count(upload),
        "corrected_count_display": format_report_public_finding_count(upload),
        "finding_groups": _report_public_finding_groups_payload(upload),
        "calculated_groups": _report_finding_groups_payload(upload),
        "edit_groups": _report_finding_edit_groups_payload(upload),
    }
    payload["workflow_status"] = mark_corrected_workflow_status(
        upload,
        report_workflow_status(upload, threshold=payload["finding_threshold"]),
    )
    payload["workflow_status_class"] = report_workflow_status_class(payload["workflow_status"])
    payload["status_date"] = format_report_status_date(upload, payload["workflow_status"])
    if not (viewer and can_adjust_report_findings(viewer, upload)):
        payload.pop("calculated_groups", None)
        payload.pop("edit_groups", None)
        payload.pop("calculated_count_display", None)
        payload.pop("corrected_count_display", None)
    payload.update(extra)
    return payload


def _review_step_row_html(request, upload):
    """HTML новой строки шага, если автопроверка уже «Сдан» и шаг открыт."""
    from .models import ReportReviewEntry

    status = report_workflow_status(upload) or ""
    if status.startswith("Сдан"):
        phase = "review"
    elif status == "Проверен ИИ":
        phase = "rework"
    else:
        return ""
    entries = ReportReviewEntry.objects.filter(upload=upload, phase=phase, settled=False)
    if phase == "rework":
        entries = entries.filter(step="ai")
    entry = (
        entries
        .select_related("upload", "upload__registration", "upload__registration__type", "upload__performer", "upload__performer__typical_section", "basis_entry")
        .order_by("-created_at", "-id")
        .first()
    )
    if entry is None:
        return ""
    return _render_report_submission_row(request, build_report_review_current_row(entry))


def _review_file_upload_payload(request, upload):
    """Ответ загрузки файла шага: число примечаний на строке файла и новая строка сверху."""
    from .models import ReportReviewEntry
    from .report_review import entry_status

    payload = _report_upload_fallback_payload(upload)
    payload["show_finding_info"] = False
    payload["can_review_upload"] = False
    newest = (
        ReportReviewEntry.objects
        .filter(upload=upload)
        .select_related("upload", "upload__registration", "upload__performer", "upload__performer__typical_section", "basis_entry")
        .order_by("-created_at", "-id")
        .first()
    )
    if newest is None:
        return payload
    file_entry = (
        ReportReviewEntry.objects
        .filter(upload=upload)
        .exclude(review_file_name="", review_cloud_path="")
        .order_by("-id")
        .first()
    )
    if file_entry is not None:
        payload["review_file_name"] = file_entry.review_file_name
        payload["review_download_url"] = reverse("report_review_entry_download", args=[file_entry.pk])
        payload["review_entry_id"] = file_entry.pk
        payload["remarks_notice_pending"] = bool(file_entry.remarks_notice_pending)
        payload["finding_count_display"] = format_grouped_count(int(file_entry.comment_count or 0))
        payload["workflow_status"] = entry_status(file_entry)
        payload["workflow_status_class"] = report_workflow_status_class(payload["workflow_status"])
        payload["status_date"] = format_report_datetime(file_entry.created_at)
        payload["comment_on_submitted_row"] = file_entry.pk != newest.pk
        payload["check_file_name"] = ""
        payload["check_download_url"] = ""
        payload["check_status"] = ""
    else:
        payload["comment_on_submitted_row"] = False
        payload["finding_count_display"] = "—"
    if (
        file_entry is not None
        and newest.pk != file_entry.pk
        and not file_entry.remarks_notice_pending
    ):
        payload["review_row_html"] = _render_report_submission_row(
            request,
            build_report_review_current_row(newest),
        )
    return payload


def _review_accept_payload(request, upload, closed_entry):
    """Ответ «Принять без замечаний»: статус той же строки и следующая, если она есть."""
    from .models import ReportReviewEntry
    from .report_review import entry_status

    payload = _report_upload_fallback_payload(upload)
    payload["show_finding_info"] = False
    payload["can_review_upload"] = False
    payload["check_file_name"] = ""
    payload["check_download_url"] = ""
    payload["check_status"] = ""
    payload["review_file_name"] = ""
    payload["review_download_url"] = ""
    payload["finding_count_display"] = format_grouped_count(0)
    payload["workflow_status"] = entry_status(closed_entry)
    payload["workflow_status_class"] = report_workflow_status_class(payload["workflow_status"])
    payload["status_date"] = format_report_datetime(closed_entry.created_at)
    payload["comment_on_submitted_row"] = True
    newest = (
        ReportReviewEntry.objects
        .filter(upload=upload)
        .select_related("upload", "upload__registration", "upload__performer", "upload__performer__typical_section", "basis_entry")
        .order_by("-created_at", "-id")
        .first()
    )
    if newest is not None and newest.pk != closed_entry.pk:
        payload["review_row_html"] = _render_report_submission_row(
            request,
            build_report_review_current_row(newest),
        )
    return payload


def _report_upload_response(request, upload):
    try:
        payload = _report_upload_fallback_payload(upload)
        try:
            is_local = is_local_report_path(upload.cloud_path) or is_local_report_path(upload.check_cloud_path)
            payload["local"] = is_local
            payload["storage_label"] = (
                "локальную папку" if is_local else get_primary_cloud_storage_label()
            )
        except Exception:
            logger.exception("Failed to resolve report upload storage label for upload %s", upload.pk)
        if upload.check_file_name:
            try:
                payload["check_download_url"] = reverse("report_check_file_download", args=[upload.pk])
            except Exception:
                logger.exception("Failed to build check download URL for upload %s", upload.pk)
        if getattr(upload, "review_file_name", ""):
            try:
                payload["review_download_url"] = reverse("report_review_file_download", args=[upload.pk])
            except Exception:
                logger.exception("Failed to build review download URL for upload %s", upload.pk)
        previous = None
        try:
            previous = previous_report_upload(upload)
        except Exception:
            logger.exception("Failed to load previous report version for upload %s", upload.pk)
        if previous is not None:
            payload["has_history"] = True
            try:
                history_row = build_report_history_row(upload, previous)
                payload["previous_row_html"] = _render_report_submission_row(request, history_row)
            except Exception:
                logger.exception("Failed to render previous report version row for upload %s", upload.pk)
                payload["previous_row_html"] = ""
        return JsonResponse(payload)
    except Exception:
        logger.exception("Failed to build report upload JSON for upload %s", getattr(upload, "pk", None))
        try:
            return JsonResponse(_report_upload_fallback_payload(upload, has_history=True))
        except Exception:
            logger.exception("Failed to build fallback report upload JSON")
            return JsonResponse({"ok": True, "file_name": "", "download_url": "", "previous_row_html": ""})


@login_required
@user_passes_test(staff_required)
@require_POST
def report_file_upload(request):
    performer_id = (request.POST.get("performer_id") or "").strip()
    is_all_sections = (request.POST.get("is_all_sections") or "") in {"1", "true", "True"}
    is_full_report = (request.POST.get("is_full_report") or "") in {"1", "true", "True"}
    active_statuses = ["Не начат", "В работе"]

    try:
        uploaded_file, local_folder_path = resolve_report_upload_source(request)
        if is_full_report:
            try:
                registration_id = int(request.POST.get("registration_id") or "")
            except (TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "Некорректный проект."}, status=400)
            asset_name = (request.POST.get("asset_name") or "").strip()
            project = get_object_or_404(
                ProjectRegistration.objects.filter(status__in=active_statuses),
                pk=registration_id,
            )
            has_asset_rows = (
                Performer.objects.annotate(executor_trim=Trim("executor"))
                .filter(registration_id=registration_id, asset_name=asset_name)
                .exclude(executor_trim="")
                .exists()
            )
            if not has_asset_rows:
                return JsonResponse(
                    {"ok": False, "error": "Для этого актива нет строк исполнителей."},
                    status=400,
                )
            if not can_mutate_report_slot(
                request.user,
                project=project,
                is_full_report=True,
            ):
                return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
            upload = upload_report_file(
                user=request.user,
                project=project,
                executor=(project.project_manager or "").strip(),
                asset_name=asset_name,
                performer=None,
                is_all_sections=False,
                is_full_report=True,
                uploaded_file=uploaded_file,
                local_folder_path=local_folder_path,
            )
        elif is_all_sections:
            try:
                registration_id = int(request.POST.get("registration_id") or "")
            except (TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "Некорректный проект."}, status=400)
            executor = (request.POST.get("executor") or "").strip()
            asset_name = (request.POST.get("asset_name") or "").strip()
            group = list(
                Performer.objects.select_related("registration", "typical_section")
                .annotate(executor_trim=Trim("executor"))
                .filter(
                    registration_id=registration_id,
                    executor=executor,
                    asset_name=asset_name,
                    registration__status__in=active_statuses,
                )
                .exclude(executor_trim="")
            )
            if len(group) < 2:
                return JsonResponse(
                    {"ok": False, "error": "Для загрузки всех разделов нужно не меньше двух разделов."},
                    status=400,
                )
            project = group[0].registration
            if not can_mutate_report_slot(
                request.user,
                project=project,
                performers=group,
                is_all_sections=True,
            ):
                return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
            upload = upload_report_file(
                user=request.user,
                project=project,
                executor=executor,
                asset_name=asset_name,
                performer=None,
                is_all_sections=True,
                uploaded_file=uploaded_file,
                local_folder_path=local_folder_path,
            )
        else:
            try:
                performer_id = int(performer_id)
            except (TypeError, ValueError):
                return JsonResponse({"ok": False, "error": "Некорректная строка исполнителя."}, status=400)
            performer = get_object_or_404(
                Performer.objects.select_related(
                    "registration",
                    "typical_section",
                    "employee",
                    "employee__user",
                    "employee__expert_profile",
                    "employee__expert_profile__expertise_direction",
                )
                .annotate(executor_trim=Trim("executor"))
                .filter(registration__status__in=active_statuses)
                .exclude(executor_trim=""),
                pk=performer_id,
            )
            if not can_mutate_report_slot(
                request.user,
                project=performer.registration,
                performer=performer,
            ):
                return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
            upload = upload_report_file(
                user=request.user,
                project=performer.registration,
                executor=performer.executor,
                asset_name=performer.asset_name,
                performer=performer,
                is_all_sections=False,
                uploaded_file=uploaded_file,
                local_folder_path=local_folder_path,
            )
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    try:
        complete_report_remarks_for_upload(upload=upload, actor=request.user)
    except Exception:
        logger.exception("Failed to complete report remarks notification for upload %s", upload.pk)

    try:
        return _report_upload_response(request, upload)
    except Exception:
        logger.exception("Failed to return report upload JSON for upload %s", getattr(upload, "pk", None))
        return JsonResponse(
            {
                "ok": True,
                "file_name": getattr(upload, "file_name", "") or "",
                "download_url": reverse("report_file_download", args=[upload.pk]),
                "previous_row_html": "",
            }
        )


@login_required
@user_passes_test(staff_required)
@require_POST
def report_file_send(request):
    try:
        upload_id = int(request.POST.get("upload_id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Выберите одну строку с загруженным файлом."}, status=400)
    upload = get_object_or_404(PerformerReportUpload, pk=upload_id)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if not can_mutate_report_upload(request.user, upload):
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    try:
        upload = send_report_upload(user=request.user, upload=upload)
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    payload = _report_upload_fallback_payload(upload, viewer=request.user)
    if upload.check_file_name:
        payload["check_download_url"] = reverse("report_check_file_download", args=[upload.pk])
    if upload.check_status == PerformerReportUpload.CheckStatus.DONE:
        payload["review_row_html"] = _review_step_row_html(request, upload)
    if (upload.review_step or "") and (upload.review_phase or "") == "review":
        from .report_review import user_matches_review_step

        payload["can_review_upload"] = user_matches_review_step(request.user, upload, upload.review_step)
    return JsonResponse(payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_review_file_upload(request):
    try:
        upload_id = int(request.POST.get("upload_id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный отчёт."}, status=400)
    upload = get_object_or_404(
        PerformerReportUpload.objects.select_related(
            "registration",
            "performer",
            "performer__typical_section",
        ),
        pk=upload_id,
    )
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if (request.POST.get("accept_without_remarks") or "") == "1":
        from .report_review import latest_open_entry

        closed = latest_open_entry(upload)
        if closed is None:
            return JsonResponse({"ok": False, "error": "Нет шага, который можно принять."}, status=400)
        try:
            upload = accept_report_review_without_remarks(user=request.user, upload=upload)
        except ReportUploadError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        closed.refresh_from_db()
        return JsonResponse(_review_accept_payload(request, upload, closed))
    try:
        uploaded_file, local_folder_path = resolve_report_upload_source(request)
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        upload = submit_report_review_file(
            user=request.user,
            upload=upload,
            file_bytes=file_bytes,
            original_name=getattr(uploaded_file, "name", "") or "",
            local_folder_path=local_folder_path,
        )
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    payload = _review_file_upload_payload(request, upload)
    return JsonResponse(payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_remarks_send(request):
    if not can_send_reports(request.user):
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    raw_ids = request.POST.getlist("entry_ids[]") or request.POST.getlist("entry_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Выберите строки с загруженными замечаниями."}, status=400)
    try:
        entry_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)
    if not entry_ids:
        return JsonResponse({"ok": False, "error": "Выберите строки с загруженными замечаниями."}, status=400)
    try:
        sent_at = _parse_request_sent_at(request.POST.get("request_sent_at", "").strip())
    except forms.ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)
    raw_channels = request.POST.getlist("delivery_channels[]") or request.POST.getlist("delivery_channels")
    try:
        delivery_channels = normalize_delivery_channels(raw_channels)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    entries = list(
        ReportReviewEntry.objects
        .select_related(
            "upload",
            "upload__registration",
            "upload__registration__type",
            "upload__performer",
            "upload__performer__employee",
            "upload__performer__employee__user",
            "upload__performer__typical_section",
        )
        .filter(pk__in=entry_ids, remarks_notice_pending=True)
        .exclude(review_file_name="")
    )
    if len(entries) != len(entry_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных замечаний уже отправлена или не найдена."}, status=400)
    for entry in entries:
        forbidden = _forbid_report_file_access(request, entry.upload)
        if forbidden:
            return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)

    try:
        result = send_report_remarks_notices(
            entries=entries,
            sender=request.user,
            sent_at=sent_at,
            delivery_channels=delivery_channels,
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    sent_ids = set(result["sent_entry_ids"])
    rows = []
    for entry in entries:
        if entry.pk not in sent_ids:
            continue
        row_payload = {
            "review_entry_id": entry.pk,
            "review_file_name": entry.review_file_name,
            "review_download_url": reverse("report_review_entry_download", args=[entry.pk]),
        }
        rework = (
            ReportReviewEntry.objects
            .select_related(
                "upload",
                "upload__registration",
                "upload__registration__type",
                "upload__performer",
                "upload__performer__typical_section",
            )
            .filter(
                upload_id=entry.upload_id,
                step=entry.step,
                phase="rework",
                pk__gt=entry.pk,
            )
            .order_by("pk")
            .first()
        )
        if rework is not None:
            row_payload["review_row_html"] = _render_report_submission_row(
                request,
                build_report_review_current_row(rework),
            )
        rows.append(row_payload)
    payload = {
        "ok": True,
        "rows": rows,
        "email_delivery": result["email_delivery"],
    }
    if result["errors"]:
        payload["warning"] = "\n".join(result["errors"])
    return JsonResponse(payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_remarks_discard(request):
    try:
        entry_id = int(request.POST.get("entry_id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректная строка."}, status=400)
    entry = get_object_or_404(
        ReportReviewEntry.objects.select_related(
            "upload",
            "upload__registration",
            "upload__registration__type",
            "upload__performer",
            "upload__performer__typical_section",
        ),
        pk=entry_id,
    )
    forbidden = _forbid_report_file_access(request, entry.upload)
    if forbidden:
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    try:
        entry = withdraw_pending_report_remarks(user=request.user, entry=entry)
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    current = next(
        (
            row for row in build_report_slot_rows(entry.upload)
            if row.is_current and row.review_entry and row.review_entry.pk == entry.pk
        ),
        None,
    )
    if current is None:
        return JsonResponse({"ok": False, "error": "Не удалось вернуть строку."}, status=400)
    return JsonResponse({
        "ok": True,
        "review_entry_id": entry.pk,
        "row_html": _render_report_submission_row(request, current),
    })


@login_required
@user_passes_test(staff_required)
@require_GET
def report_check_status(request, pk):
    upload = get_object_or_404(PerformerReportUpload, pk=pk)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if upload.check_status == PerformerReportUpload.CheckStatus.RUNNING:
        recover_abandoned_report_checks(upload_id=upload.pk)
        upload.refresh_from_db()
    payload = _report_upload_fallback_payload(upload, viewer=request.user)
    pending_result = pending_report_check_payload(upload)
    if pending_result:
        payload.update(pending_result)
        return JsonResponse(payload)
    if upload.check_file_name:
        payload["check_download_url"] = reverse(
            "report_check_file_download",
            args=[upload.pk],
        )
    if upload.check_status == PerformerReportUpload.CheckStatus.DONE:
        payload["review_row_html"] = _review_step_row_html(request, upload)
    return JsonResponse(payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_check_resume(request, pk):
    upload = get_object_or_404(PerformerReportUpload, pk=pk)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if not can_mutate_report_upload(request.user, upload):
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    try:
        upload = resume_report_check(user=request.user, upload=upload)
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    payload = _report_upload_fallback_payload(upload, viewer=request.user)
    if upload.check_file_name:
        payload["check_download_url"] = reverse("report_check_file_download", args=[upload.pk])
    return JsonResponse(payload)


@login_required
@user_passes_test(staff_required)
@require_POST
def report_finding_correction(request, pk):
    upload = get_object_or_404(
        PerformerReportUpload.objects.select_related(
            "registration",
            "registration__type",
            "performer",
            "performer__typical_section",
        ),
        pk=pk,
    )
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if not can_adjust_report_findings(request.user, upload):
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    if (upload.check_status or "") != PerformerReportUpload.CheckStatus.DONE:
        return JsonResponse({"ok": False, "error": "Проверка ещё не завершена."}, status=400)
    try:
        body = json.loads(request.body.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)
    counts = body.get("counts") if isinstance(body, dict) else None
    if not isinstance(counts, dict):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)
    try:
        apply_finding_correction(upload, counts)
    except FindingCorrectionError as exc:
        return JsonResponse(
            {"ok": False, "error": str(exc), "invalid_labels": exc.labels},
            status=400,
        )
    upload.refresh_from_db()
    rows = annotate_report_submission_rows(request.user, build_report_slot_rows(upload))
    html = "".join(_render_report_submission_row(request, row) for row in rows)
    return JsonResponse({
        "ok": True,
        "slot_rows_html": html,
        "version_group": report_slot_row_id(upload),
    })


@login_required
@user_passes_test(staff_required)
@require_POST
def report_file_delete(request, pk):
    if not is_admin_user(request.user):
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)
    upload = get_object_or_404(
        PerformerReportUpload.objects.select_related(
            "registration",
            "registration__type",
            "performer",
            "performer__typical_section",
        ),
        pk=pk,
    )
    kind = (request.POST.get("kind") or "").strip()
    if kind not in {"upload", "check"}:
        return JsonResponse({"ok": False, "error": "Некорректный тип удаления."}, status=400)
    try:
        if kind == "check":
            upload = clear_report_check_result(request.user, upload)
            payload = _report_upload_fallback_payload(upload)
            payload["kind"] = "check"
            return JsonResponse(payload)
        was_latest, remaining = delete_report_upload(request.user, upload)
    except ReportUploadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    slot_row_id = report_slot_row_id(upload)
    current = remaining[0] if remaining else None
    payload = {
        "ok": True,
        "kind": "upload",
        "deleted_upload_id": pk,
        "slot_row_id": slot_row_id,
        "replaced_current": was_latest,
        "has_history": len(remaining) > 1,
        "current_row_html": "",
        "remove_row_id": "",
    }
    if was_latest:
        row = build_report_slot_current_row(
            upload,
            current,
            has_history=len(remaining) > 1,
        )
        payload["current_row_html"] = _render_report_submission_row(request, row)
        if current is not None:
            payload["remove_row_id"] = (
                f"{slot_row_id}-v{format_report_version(current.version)}"
            )
    return JsonResponse(payload)


@login_required
@require_GET
def report_file_download(request, pk):
    upload = get_object_or_404(PerformerReportUpload, pk=pk)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    return _serve_report_stored_file(
        upload,
        file_name=upload.file_name,
        cloud_path=upload.cloud_path,
        file_link=upload.file_link,
        user=request.user,
    )


@login_required
@require_GET
def report_check_file_download(request, pk):
    upload = get_object_or_404(PerformerReportUpload, pk=pk)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if not (upload.check_file_name or upload.check_cloud_path or upload.check_file_link):
        raise Http404("Файл не найден.")
    return _serve_report_stored_file(
        upload,
        file_name=upload.check_file_name,
        cloud_path=upload.check_cloud_path,
        file_link=upload.check_file_link,
        user=request.user,
    )


@login_required
@user_passes_test(staff_required)
@require_GET
@login_required
@user_passes_test(staff_required)
@require_GET
def report_review_entry_download(request, pk):
    entry = get_object_or_404(ReportReviewEntry.objects.select_related("upload"), pk=pk)
    forbidden = _forbid_report_file_access(request, entry.upload)
    if forbidden:
        return forbidden
    if not (entry.review_file_name or entry.review_cloud_path or entry.review_file_link):
        raise Http404("Файл не найден.")
    return _serve_report_stored_file(
        entry.upload,
        file_name=entry.review_file_name,
        cloud_path=entry.review_cloud_path,
        file_link=entry.review_file_link,
        user=request.user,
    )


def report_review_file_download(request, pk):
    upload = get_object_or_404(PerformerReportUpload, pk=pk)
    forbidden = _forbid_report_file_access(request, upload)
    if forbidden:
        return forbidden
    if not (upload.review_file_name or upload.review_cloud_path or upload.review_file_link):
        raise Http404("Файл не найден.")
    return _serve_report_stored_file(
        upload,
        file_name=upload.review_file_name,
        cloud_path=upload.review_cloud_path,
        file_link=upload.review_file_link,
        user=request.user,
    )


def _forbid_report_file_access(request, upload):
    if not can_view_report_upload(request.user, upload):
        return HttpResponseForbidden("Недостаточно прав.")
    return None


def _forbid_report_check_manage(request):
    if not can_manage_report_checks(request.user):
        return HttpResponseForbidden("Недостаточно прав.")
    return None


def _serve_report_stored_file(upload, *, file_name, cloud_path, file_link, user):
    if is_local_report_path(cloud_path):
        file_bytes = read_local_report_bytes(cloud_path)
        if not file_bytes:
            raise Http404("Файл не найден.")
        filename = file_name or os.path.basename(parse_local_report_path(cloud_path) or "")
        return FileResponse(BytesIO(file_bytes), as_attachment=True, filename=filename)

    if cloud_path:
        try:
            cloud_user = user if is_nextcloud_primary() else get_any_connected_service_user()
        except CloudStorageNotReadyError:
            cloud_user = None
        if cloud_user:
            _mime, file_bytes = cloud_download_file(cloud_user, cloud_path)
            if file_bytes:
                filename = file_name or os.path.basename(cloud_path)
                return FileResponse(BytesIO(file_bytes), as_attachment=True, filename=filename)

    if file_link:
        return redirect(file_link)
    raise Http404("Файл не найден.")


def _report_check_form_response(request, form, action, item=None, status=200):
    return render(
        request,
        REPORT_CHECK_FORM_TEMPLATE,
        {
            "form": form,
            "action": action,
            "rule": item,
            "sections_payload": getattr(form, "sections_payload", []),
            "catalog": getattr(form, "catalog", []),
            "line_rows": getattr(form, "line_rows", []),
            "review_order_rows": getattr(form, "review_order_rows", []),
        },
        status=status,
    )


def _normalize_report_check_positions():
    items = list(ReportCheckRule.objects.order_by("position", "id").only("id", "position"))
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ReportCheckRule.objects.filter(pk=item.pk).update(position=idx)


def _render_report_check_saved():
    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_check_form_create(request):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    if request.method == "GET":
        return _report_check_form_response(request, ReportCheckRuleForm(), "create")
    form = ReportCheckRuleForm(request.POST)
    if not form.is_valid():
        return _report_check_form_response(request, form, "create")
    if not getattr(form.instance, "position", 0):
        form.instance.position = _next_position(ReportCheckRule)
    form.save()
    return _render_report_check_saved()


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_check_form_edit(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    item = get_object_or_404(
        ReportCheckRule.objects.select_related("product", "expertise_dir", "section", "section__product").prefetch_related("lines__macro"),
        pk=pk,
    )
    if request.method == "GET":
        return _report_check_form_response(request, ReportCheckRuleForm(instance=item), "edit", item)
    form = ReportCheckRuleForm(request.POST, instance=item)
    if not form.is_valid():
        return _report_check_form_response(request, form, "edit", item)
    form.save()
    return _render_report_check_saved()


@login_required
@user_passes_test(staff_required)
@require_POST
def report_check_delete(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    item = get_object_or_404(ReportCheckRule, pk=pk)
    item.delete()
    _normalize_report_check_positions()
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


def _swap_report_check_positions(pk: int, direction: str):
    _normalize_report_check_positions()
    items = list(ReportCheckRule.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is None:
        return
    if direction == "up" and idx > 0:
        current, other = items[idx], items[idx - 1]
    elif direction == "down" and idx < len(items) - 1:
        current, other = items[idx], items[idx + 1]
    else:
        return
    ReportCheckRule.objects.filter(pk=current.id).update(position=other.position)
    ReportCheckRule.objects.filter(pk=other.id).update(position=current.position)
    _normalize_report_check_positions()


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def report_check_move_up(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    get_object_or_404(ReportCheckRule, pk=pk)
    _swap_report_check_positions(pk, "up")
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def report_check_move_down(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    get_object_or_404(ReportCheckRule, pk=pk)
    _swap_report_check_positions(pk, "down")
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


def _report_macro_form_response(request, form, action, item=None, status=200):
    return render(
        request,
        REPORT_MACRO_FORM_TEMPLATE,
        {"form": form, "action": action, "macro": item},
        status=status,
    )


def _normalize_report_macro_positions():
    items = list(ReportMacro.objects.order_by("position", "id").only("id"))
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ReportMacro.objects.filter(pk=item.pk).update(position=idx)


def _render_report_macro_saved():
    resp = HttpResponse(status=204)
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp


def _parse_processing_mode(raw: str) -> str:
    value = (raw or "").strip()
    folded = value.casefold().rstrip(".")
    labels = {
        "chunks": ReportMacro.ProcessingMode.CHUNKS,
        "фрагменты": ReportMacro.ProcessingMode.CHUNKS,
        "agent": ReportMacro.ProcessingMode.AGENT,
        "агент": ReportMacro.ProcessingMode.AGENT,
    }
    if not value:
        return ReportMacro.ProcessingMode.CHUNKS
    return labels.get(folded, value)


def _disable_tools_label(enabled: bool) -> str:
    return "да" if enabled else "нет"


def _parse_disable_tools(raw: str) -> bool:
    return (raw or "").strip().casefold() in {"1", "да", "yes", "true", "on", "+"}


def _temperature_label(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "По умолчанию"
    return value


def _canonical_temperature(raw: str) -> str:
    value = (raw or "").strip().replace(",", ".")
    if value.casefold() in {"", "по умолчанию", "default"}:
        return ""
    allowed = {code for code, _label in ReportMacro.TEMPERATURE_CHOICES if code}
    if value in allowed:
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    if number == int(number) and str(int(number)) in allowed:
        return str(int(number))
    text = f"{number:.1f}"
    if text in allowed:
        return text
    return value


def _reasoning_level_label(raw: str) -> str:
    from core.dsh_catalog import REASONING_LEVEL_LABELS

    value = (raw or "").strip()
    return REASONING_LEVEL_LABELS.get(value, value)


def _parse_report_macro_kind(raw: str) -> str:
    value = (raw or "").strip()
    lowered = value.casefold()
    if lowered in {"macro", "макрос"}:
        return ReportMacro.CheckKind.MACRO
    if lowered in {"skill", "навык"}:
        return ReportMacro.CheckKind.SKILL
    return value


def _report_macro_csv_error_text(form) -> str:
    parts = []
    for field, errors in form.errors.items():
        if field == "__all__":
            prefix = ""
        else:
            bound = form.fields.get(field)
            prefix = f"{bound.label}: " if bound and bound.label else f"{field}: "
        for err in errors:
            parts.append(f"{prefix}{err}")
    return "; ".join(parts)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def report_macro_csv_download(request):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(REPORT_MACRO_CSV_HEADERS)
    for macro in ReportMacro.objects.order_by("position", "id"):
        writer.writerow(
            [
                macro.course,
                macro.section,
                macro.part,
                macro.number,
                macro.name,
                macro.description,
                macro.code,
                macro.get_check_kind_display(),
                macro.skill_name,
                macro.model_id,
                _reasoning_level_label(macro.reasoning_effort),
                _disable_tools_label(macro.disable_tools),
                macro.get_processing_mode_display(),
                _temperature_label(macro.temperature),
                macro.validation_model_id,
                _reasoning_level_label(macro.validation_reasoning_effort),
                _temperature_label(macro.validation_temperature),
            ]
        )
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="report_macros.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def report_macro_csv_upload(request):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"ok": False, "error": "Файл не выбран."}, status=400)
    if not csv_file.name.lower().endswith(".csv"):
        return JsonResponse({"ok": False, "error": "Допустимы только файлы CSV."}, status=400)

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251)."},
                status=400,
            )

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return JsonResponse({"ok": False, "error": "Файл пуст."}, status=400)
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return JsonResponse(
            {"ok": False, "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла."},
            status=400,
        )

    if len(rows) < 2:
        return JsonResponse(
            {"ok": False, "error": "Файл должен содержать заголовок и хотя бы одну строку данных."},
            status=400,
        )

    created = 0
    warnings = []
    expected_cols = len(REPORT_MACRO_CSV_HEADERS)

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < REPORT_MACRO_CSV_MIN_COLUMNS or (
            REPORT_MACRO_CSV_MIN_COLUMNS < len(row) < REPORT_MACRO_CSV_SKILL_COLUMNS
        ):
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается {expected_cols}: "
                f"{', '.join(REPORT_MACRO_CSV_HEADERS)})."
            )
            continue
        payload = {
            "course": row[0],
            "section": row[1],
            "part": row[2],
            "number": row[3],
            "name": row[4],
            "description": row[5],
            "code": row[6],
            "check_kind": ReportMacro.CheckKind.MACRO,
            "skill_name": "",
            "model_id": "",
            "reasoning_effort": "",
            "temperature": "",
            "disable_tools": False,
            "processing_mode": ReportMacro.ProcessingMode.CHUNKS,
            "validation_model_id": "",
            "validation_reasoning_effort": "",
            "validation_temperature": "",
        }
        if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS:
            from core.dsh_catalog import parse_reasoning_level

            payload["check_kind"] = _parse_report_macro_kind(row[7])
            payload["skill_name"] = row[8]
            payload["model_id"] = row[9]
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 1:
                payload["reasoning_effort"] = parse_reasoning_level(row[10])
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 2:
                payload["disable_tools"] = _parse_disable_tools(row[11])
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 3:
                payload["processing_mode"] = _parse_processing_mode(row[12])
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 4:
                payload["temperature"] = _canonical_temperature(row[13])
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 5:
                payload["validation_model_id"] = row[14]
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 6:
                payload["validation_reasoning_effort"] = parse_reasoning_level(row[15])
            if len(row) >= REPORT_MACRO_CSV_SKILL_COLUMNS + 7:
                payload["validation_temperature"] = _canonical_temperature(row[16])
        form = ReportMacroForm(payload)
        if not form.is_valid():
            warnings.append(f"Строка {i}: {_report_macro_csv_error_text(form)}")
            continue
        obj = form.save(commit=False)
        if not getattr(obj, "position", 0):
            obj.position = _next_position(ReportMacro)
        obj.save()
        created += 1

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def report_macros_table(request):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    context = _report_macros_table_context(request)
    context["is_expert"] = is_expert_user(request.user)
    return render(request, REPORT_MACROS_SECTION_TEMPLATE, context)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_macro_form_create(request):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    if request.method == "GET":
        return _report_macro_form_response(request, ReportMacroForm(), "create")
    form = ReportMacroForm(request.POST)
    if not form.is_valid():
        return _report_macro_form_response(request, form, "create")
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ReportMacro)
    obj.save()
    return _render_report_macro_saved()


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def report_macro_form_edit(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    item = get_object_or_404(ReportMacro, pk=pk)
    if request.method == "GET":
        return _report_macro_form_response(request, ReportMacroForm(instance=item), "edit", item)
    form = ReportMacroForm(request.POST, instance=item)
    if not form.is_valid():
        return _report_macro_form_response(request, form, "edit", item)
    form.save()
    return _render_report_macro_saved()


@login_required
@user_passes_test(staff_required)
@require_POST
def report_macro_delete(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    item = get_object_or_404(ReportMacro, pk=pk)
    item.delete()
    _normalize_report_macro_positions()
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


def _swap_report_macro_positions(pk: int, direction: str):
    _normalize_report_macro_positions()
    items = list(ReportMacro.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is None:
        return
    if direction == "up" and idx > 0:
        current, other = items[idx], items[idx - 1]
    elif direction == "down" and idx < len(items) - 1:
        current, other = items[idx], items[idx + 1]
    else:
        return
    ReportMacro.objects.filter(pk=current.id).update(position=other.position)
    ReportMacro.objects.filter(pk=other.id).update(position=current.position)
    _normalize_report_macro_positions()


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def report_macro_move_up(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    get_object_or_404(ReportMacro, pk=pk)
    _swap_report_macro_positions(pk, "up")
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def report_macro_move_down(request, pk: int):
    forbidden = _forbid_report_check_manage(request)
    if forbidden:
        return forbidden
    get_object_or_404(ReportMacro, pk=pk)
    _swap_report_macro_positions(pk, "down")
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user, request))


@login_required
@user_passes_test(staff_required)
@require_POST
def create_source_data_workspace(request):
    project_id = request.POST.get("project_id")
    if not project_id:
        return JsonResponse({"ok": False, "error": "Не выбран проект."}, status=400)

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректный ID проекта."}, status=400)

    project = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(pk=project_id)
        .first()
    )
    if not project:
        return JsonResponse({"ok": False, "error": "Проект не найден."}, status=404)

    workspace_result_class = get_workspace_result_class()

    MIN_CHUNK = 256

    def _padded(line):
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        try:
            iterator = routed_create_source_data_workspace_stream(request.user, project)
            for item in iterator:
                if isinstance(item, workspace_result_class):
                    if item.ok:
                        yield _padded(json.dumps({"ok": True, "message": item.message}) + "\n")
                    else:
                        yield _padded(json.dumps({"ok": False, "error": item.message}) + "\n")
                else:
                    yield _padded(json.dumps(item) + "\n")
        except CloudStorageNotReadyError as exc:
            yield _padded(json.dumps({"ok": False, "error": str(exc)}) + "\n")

    resp = StreamingHttpResponse(_stream(), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache, no-store"
    resp["X-Accel-Buffering"] = "no"
    return resp


@login_required
@user_passes_test(staff_required)
@require_GET
def source_data_target_folder_load(request):
    from .models import SourceDataTargetFolder

    qs, _ = _get_effective_folders(request.user)
    rows = list(
        qs.order_by("position")
        .values_list("level", "name")
    )
    options = [
        path
        for path in build_workspace_folder_tree(rows)
        if path.count("/") <= 1 and not contains_workspace_project_variable(path)
    ] if rows else []
    if not options:
        options = list(get_registration_standard_folders())

    target = SourceDataTargetFolder.objects.filter(user=request.user).first()
    folder_name = target.folder_name if target else ""

    return JsonResponse({"folder_name": folder_name, "options": options})


@login_required
@user_passes_test(staff_required)
@require_POST
def source_data_target_folder_save(request):
    from .models import SourceDataTargetFolder

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    folder_name = (data.get("folder_name") or "").strip()
    if not folder_name:
        return JsonResponse({"ok": False, "error": "Не указано имя папки."}, status=400)
    if contains_workspace_project_variable(folder_name):
        return JsonResponse(
            {"ok": False, "error": "Шаблонные папки проекта нельзя использовать как целевую папку."},
            status=400,
        )

    SourceDataTargetFolder.objects.update_or_create(
        user=request.user,
        defaults={"folder_name": folder_name},
    )
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(staff_required)
@require_GET
def contract_project_target_folder_load(request):
    from .models import ContractProjectTargetFolder

    qs, _ = _get_effective_folders(request.user)
    options = list(
        qs.filter(level=1)
        .order_by("position")
        .values_list("name", flat=True)
    )
    if not options:
        options = list(get_registration_standard_folders())

    target = ContractProjectTargetFolder.objects.filter(user=request.user).first()
    folder_name = target.folder_name if target else ""

    return JsonResponse({"folder_name": folder_name, "options": options})


@login_required
@user_passes_test(staff_required)
@require_POST
def contract_project_target_folder_save(request):
    from .models import ContractProjectTargetFolder

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные данные."}, status=400)

    folder_name = (data.get("folder_name") or "").strip()
    if not folder_name:
        return JsonResponse({"ok": False, "error": "Не указано имя папки."}, status=400)

    ContractProjectTargetFolder.objects.update_or_create(
        user=request.user,
        defaults={"folder_name": folder_name},
    )
    return JsonResponse({"ok": True})


def _expand_contract_batch_performers(performers):
    performer_list = list(performers)
    group_filter = Q()
    selected_without_group = []
    has_group = False
    for performer in performer_list:
        if performer.participation_batch_id:
            addendum_number = getattr(performer, "contract_addendum_number", None) or 0
            number_filter = Q(contract_addendum_number=addendum_number)
            if not addendum_number:
                number_filter |= Q(contract_addendum_number__isnull=True)
            group_filter |= Q(
                participation_batch_id=performer.participation_batch_id,
                executor=_normalize_contract_person_name(getattr(performer, "executor", "")),
                contract_batch_id__isnull=False,
                contract_is_addendum=bool(getattr(performer, "contract_is_addendum", False)),
            ) & number_filter
            has_group = True
        elif performer.contract_batch_id:
            group_filter |= Q(contract_batch_id=performer.contract_batch_id)
            has_group = True
        else:
            selected_without_group.append(performer.pk)
    if not has_group:
        return performer_list

    expanded = list(
        Performer.objects
        .filter(group_filter)
        .select_related(
            "registration",
            "registration__type",
            "typical_section",
            "employee",
            "employee__user",
            "currency",
        )
        .order_by("registration_id", "executor", "position", "id")
    )
    if selected_without_group:
        expanded.extend(
            Performer.objects
            .filter(pk__in=selected_without_group)
            .select_related(
                "registration",
                "registration__type",
                "typical_section",
                "employee",
                "employee__user",
                "currency",
            )
            .order_by("registration_id", "executor", "position", "id")
        )
    return expanded


@login_required
@user_passes_test(staff_required)
@require_POST
def sign_contract_documents(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки для подписи договора."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    performers = list(
        Performer.objects
        .filter(pk__in=performer_ids)
        .select_related("registration")
        .order_by("registration_id", "executor", "position", "id")
    )
    if len(performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)
    performers = _expand_contract_batch_performers(performers)

    if not is_onlyoffice_conversion_configured():
        return JsonResponse(
            {"ok": False, "error": "Не настроен ONLYOFFICE Document Server для генерации PDF."},
            status=400,
        )

    grouped: dict[tuple[object, str, str, str], list[Performer]] = {}
    errors = []
    for performer in performers:
        docx_name = str(getattr(performer, "contract_file", "") or "").strip()
        folder = str(getattr(performer, "contract_project_disk_folder", "") or "").strip()
        label = getattr(getattr(performer, "registration", None), "short_uid", "") or f"#{performer.pk}"
        if not docx_name:
            errors.append(f"Для {label} сначала создайте DOCX-файл договора.")
            continue
        if not folder:
            errors.append(f"Для {label} не задана папка проекта договора.")
            continue
        key = (
            performer.participation_batch_id or performer.contract_batch_id or performer.registration_id,
            bool(getattr(performer, "contract_is_addendum", False)),
            getattr(performer, "contract_addendum_number", None) or 0,
            performer.executor,
            normalize_cloud_path(folder),
            docx_name,
        )
        grouped.setdefault(key, []).append(performer)

    updated_ids: set[int] = set()
    generated_groups = 0
    for group_performers in grouped.values():
        performer = group_performers[0]
        label = getattr(getattr(performer, "registration", None), "short_uid", "") or f"#{performer.pk}"
        try:
            pdf_bytes = convert_docx_source_to_pdf(
                source_url=_build_contract_docx_source_url(request, performer),
                source_name=str(getattr(performer, "contract_file", "") or "").strip() or "contract.docx",
            )
            stored_pdf = _store_generated_contract_pdf(request.user, performer, pdf_bytes)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            continue

        group_ids = [item.pk for item in group_performers]
        update_kwargs = {
            "contract_pdf_file": stored_pdf["pdf_name"],
            "contract_pdf_link": stored_pdf["pdf_url"],
        }
        if stored_pdf.get("pdf_file_id"):
            update_kwargs["contract_pdf_file_id"] = stored_pdf["pdf_file_id"]
        Performer.objects.filter(pk__in=group_ids).update(**update_kwargs)
        updated_ids.update(group_ids)
        generated_groups += 1

    if errors and not updated_ids:
        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(errors),
                "generated": 0,
                "warnings": [],
            },
            status=400,
        )

    updates = list(
        Performer.objects
        .filter(pk__in=updated_ids)
        .order_by("registration_id", "executor", "position", "id")
        .values("id", "contract_pdf_file", "contract_pdf_link")
    )
    return JsonResponse(
        {
            "ok": True,
            "message": "PDF для договора успешно сформирован.",
            "generated": generated_groups,
            "warnings": errors,
            "updates": [
                {
                    "id": item["id"],
                    "contract_pdf_file": item["contract_pdf_file"],
                    "contract_project_pdf_file_url": item["contract_pdf_link"],
                }
                for item in updates
            ],
        }
    )


@login_required
@user_passes_test(performer_contract_signing_required)
@require_POST
def sign_performer_contract_documents(request):
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбрана строка для подписания договора."}, status=400)

    try:
        performer_ids = sorted({int(value) for value in raw_ids if str(value).strip()})
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Передан некорректный список строк."}, status=400)

    performers = list(
        Performer.objects
        .filter(pk__in=performer_ids)
        .select_related("registration", "employee")
        .order_by("registration_id", "executor", "position", "id")
    )
    if len(performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)
    performers = _expand_contract_batch_performers(performers)

    if not is_onlyoffice_conversion_configured():
        return JsonResponse(
            {"ok": False, "error": "Не настроен ONLYOFFICE Document Server для генерации PDF."},
            status=400,
        )

    grouped: dict[tuple[object, str, str, str], list[Performer]] = {}
    errors = []
    for performer in performers:
        docx_name = str(getattr(performer, "contract_file", "") or "").strip()
        folder = str(getattr(performer, "contract_project_disk_folder", "") or "").strip()
        label = getattr(getattr(performer, "registration", None), "short_uid", "") or f"#{performer.pk}"
        if not docx_name:
            errors.append(f"Для {label} сначала создайте DOCX-файл договора.")
            continue
        if not folder:
            errors.append(f"Для {label} не задана папка проекта договора.")
            continue
        try:
            has_performer_facsimile = bool(_load_performer_facsimile_bytes(performer))
        except RuntimeError as exc:
            errors.append(f"{label}: {exc}")
            continue
        if not has_performer_facsimile:
            errors.append(_contract_performer_facsimile_missing_message(label, performer))
            continue
        key = (
            performer.participation_batch_id or performer.contract_batch_id or performer.registration_id,
            bool(getattr(performer, "contract_is_addendum", False)),
            getattr(performer, "contract_addendum_number", None) or 0,
            performer.executor,
            normalize_cloud_path(folder),
            docx_name,
        )
        grouped.setdefault(key, []).append(performer)

    updated_ids: set[int] = set()
    generated_groups = 0
    for group_performers in grouped.values():
        performer = group_performers[0]
        label = getattr(getattr(performer, "registration", None), "short_uid", "") or f"#{performer.pk}"
        try:
            pdf_bytes = convert_docx_source_to_pdf(
                source_url=_build_contract_docx_source_url(
                    request,
                    performer,
                    include_performer_facsimile=True,
                ),
                source_name=str(getattr(performer, "contract_file", "") or "").strip() or "contract.docx",
            )
            stored_pdf = _store_generated_contract_pdf(request.user, performer, pdf_bytes, signed=True)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            continue

        signed_at = timezone.now()
        group_ids = [item.pk for item in group_performers]
        update_kwargs = {
            "contract_signed_pdf_file": stored_pdf["pdf_name"],
            "contract_signed_pdf_link": stored_pdf["pdf_url"],
            "contract_signing_date": signed_at,
        }
        if stored_pdf.get("pdf_file_id"):
            update_kwargs["contract_signed_pdf_file_id"] = stored_pdf["pdf_file_id"]
        for item in group_performers:
            item.contract_signing_date = signed_at
            item.contract_conclusion_status = item.contract_response_status
            Performer.objects.filter(pk=item.pk).update(
                **update_kwargs,
                contract_conclusion_status=item.contract_conclusion_status,
                contract_signing_note="Договор подписан факсимиле",
            )
        updated_ids.update(group_ids)
        generated_groups += 1

    if errors and not updated_ids:
        return JsonResponse(
            {
                "ok": False,
                "error": "; ".join(errors),
                "generated": 0,
                "warnings": [],
            },
            status=400,
        )

    updates = list(
        Performer.objects
        .filter(pk__in=updated_ids)
        .order_by("registration_id", "executor", "position", "id")
        .values("id", "contract_signed_pdf_file", "contract_signed_pdf_link")
    )
    completed_notifications = complete_contract_notifications_for_performers(
        performer_ids=updated_ids,
        actor=request.user,
    )
    return JsonResponse(
        {
            "ok": True,
            "message": "Подписанный договор успешно сформирован.",
            "generated": generated_groups,
            "completed_notifications": completed_notifications,
            "warnings": errors,
            "updates": [
                {
                    "id": item["id"],
                    "contract_signed_pdf_file": item["contract_signed_pdf_file"],
                    "contract_signed_pdf_file_url": item["contract_signed_pdf_link"],
                }
                for item in updates
            ],
        }
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def create_contract_project(request):
    """Create folders on Yandex.Disk for selected contract performers and
    populate them with .docx files from matching contract templates.

    One folder per unique executor within each project (deduplicated across
    assets / typical sections).  Returns an NDJSON streaming response with
    progress updates.
    """
    import re
    from contracts_app.models import ContractTemplate, ContractVariable
    from contracts_app.variable_resolver import resolve_variables
    from contracts_app.docx_processor import process_template
    from experts_app.models import ExpertProfile
    raw_ids = request.POST.getlist("performer_ids[]") or request.POST.getlist("performer_ids")
    if not raw_ids:
        return JsonResponse({"ok": False, "error": "Не выбраны строки."}, status=400)

    try:
        ids = [int(i) for i in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Некорректные ID."}, status=400)

    base_performer_qs = (
        Performer.objects
        .select_related(
            "registration", "registration__type", "registration__country",
            "registration__contract_project_registration",
            "typical_section", "employee", "contract_group_member",
        )
    )
    performers = list(
        base_performer_qs
        .filter(pk__in=ids, contract_sent_at__isnull=True)
        .order_by("position", "id")
    )
    if not performers:
        return JsonResponse({"ok": False, "error": "Нет доступных строк для создания проекта договора."}, status=400)
    participation_batch_ids = {p.participation_batch_id for p in performers if p.participation_batch_id}
    if participation_batch_ids:
        by_id = {p.pk: p for p in performers}
        expanded = list(
            base_performer_qs
            .filter(
                participation_batch_id__in=participation_batch_ids,
                contract_sent_at__isnull=True,
                participation_response=Performer.ParticipationResponse.CONFIRMED,
                employee__employment=FREELANCER_LABEL,
            )
            .exclude(executor="")
            .order_by("registration__agreement_sequence", "registration_id", "position", "id")
        )
        by_id.update({p.pk: p for p in expanded})
        performers = sorted(
            by_id.values(),
            key=lambda p: (
                str(p.participation_batch_id or ""),
                p.registration.number if p.registration_id else 0,
                p.registration.agreement_sequence if p.registration_id else 0,
                p.registration_id or 0,
                p.position or 0,
                p.pk,
            ),
        )

    source_kind = (request.POST.get("source_kind") or "cloud").strip() or "cloud"
    if source_kind not in {"cloud", "local"}:
        source_kind = "cloud"
    local_cloud = None
    if source_kind == "local":
        try:
            local_root = resolve_local_contract_folder(request.POST.get("local_folder_path") or "")
        except LocalContractFolderError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        local_cloud = LocalContractCloud(local_root, "/")
        disk_root = local_cloud.root_path
    else:
        try:
            disk_root = get_selected_root_path(request.user)
        except CloudStorageNotReadyError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        if not disk_root:
            return JsonResponse({"ok": False, "error": "Не выбрана папка в основном облачном хранилище."}, status=400)

    def _reusable_cloud_folder(stored):
        stored = (stored or "").strip()
        if not stored:
            return ""
        if local_cloud is not None:
            return local_contract_cloud_path(stored, local_cloud.output_dir)
        if is_local_contract_path(stored):
            return ""
        return normalize_cloud_path(stored)

    def _create_contract_folder(path):
        if local_cloud is not None:
            return local_cloud.create_folder(request.user, path)
        return cloud_create_folder(request.user, path)

    def _list_contract_folder(path):
        if local_cloud is not None:
            return local_cloud.list_resources(request.user, path, limit=1000)
        return list_folder_resources(request.user, path, limit=1000)

    def _upload_contract_file(user, path, data):
        if local_cloud is not None:
            return local_cloud.upload_file(user, path, data)
        return cloud_upload_file(user, path, data)

    all_templates = list(
        ContractTemplate.objects
        .select_related("product", "group_member")
        .prefetch_related("group_members", "products")
        .filter(file__gt="")
    )
    for template in all_templates:
        template._contract_group_member_ids = {group.pk for group in template.group_members.all()}
        template._contract_product_ids = {product.pk for product in template.products.all()}

    all_variables = list(
        ContractVariable.objects.filter(
            models.Q(is_computed=True)
            | (
                ~models.Q(source_section="")
                & ~models.Q(source_table="")
                & ~models.Q(source_column="")
            )
        )
    )

    expert_cache = {}
    employee_ids = {p.employee_id for p in performers if p.employee_id}
    if employee_ids:
        for ep in (
            ExpertProfile.objects
            .select_related("country")
            .prefetch_related("contract_details_records__citizenship_record")
            .filter(employee_id__in=employee_ids)
        ):
            expert_cache[ep.employee_id] = ep

    def _contract_project_file_name(perf, original_name, batch_performers=None):
        ext = os.path.splitext(original_name or "")[1] or ".docx"
        return build_contract_file_name(perf, extension=ext, batch_performers=batch_performers)

    def _ensure_cloud_folder_path(path):
        normalized = normalize_cloud_path(path)
        if normalized == "/":
            return True
        current = ""
        for part in normalized.strip("/").split("/"):
            current = f"{current}/{part}" if current else f"/{part}"
            if not _create_contract_folder(current):
                return False
        return True

    def _country_values(country):
        if not country:
            return set()
        return {
            (getattr(country, "short_name", "") or "").strip(),
            (getattr(country, "full_name", "") or "").strip(),
            (getattr(country, "code", "") or "").strip(),
            (getattr(country, "alpha2", "") or "").strip(),
            (getattr(country, "alpha3", "") or "").strip(),
        }

    def _country_values_match_template(values, template):
        template_country_name = (getattr(template, "country_name", "") or "").strip()
        template_country_code = (getattr(template, "country_code", "") or "").strip()
        if not template_country_name and not template_country_code:
            return True
        normalized_values = {" ".join(value.split()).casefold() for value in values if value}
        return (
            " ".join(template_country_name.split()).casefold() in normalized_values
            or template_country_code.casefold() in normalized_values
        )

    def _profile_matches_template_country(expert, template):
        return _country_values_match_template(_country_values(getattr(expert, "country", None)), template)

    def _contract_detail_matches_template_country(details, template):
        template_country_name = (getattr(template, "country_name", "") or "").strip()
        template_country_code = (getattr(template, "country_code", "") or "").strip()
        if not template_country_name and not template_country_code:
            return True
        if not details:
            return False

        citizenship = getattr(details, "citizenship_record", None)
        country = getattr(citizenship, "country", None) if citizenship else None
        values = _country_values(country) | {
            (getattr(details, "citizenship_country", "") or "").strip(),
        }
        return _country_values_match_template(values, template)

    def _find_template(perf):
        """Find the best matching ContractTemplate for a Performer row."""
        project = perf.registration
        product = getattr(getattr(perf, "typical_section", None), "product", None) or getattr(project, "primary_product", None) or project.type
        if not product:
            return None

        contract_group_id = perf.contract_group_member_id or project.group_member_id

        expert = expert_cache.get(perf.employee_id) if perf.employee_id else None
        contract_details_options = expert.ordered_contract_details() if expert else []
        use_profile_country_fallback = bool(expert) and not contract_details_options
        if not contract_details_options:
            contract_details_options = [None]

        expected_party = "individual"

        section_code = ""
        if perf.typical_section:
            section_code = perf.typical_section.code or ""

        candidates = []
        for t in all_templates:
            template_group_ids = set(getattr(t, "_contract_group_member_ids", set()))
            if not template_group_ids and t.group_member_id:
                template_group_ids = {t.group_member_id}
            group_specific = bool(template_group_ids)
            if group_specific and contract_group_id not in template_group_ids:
                continue
            template_product_ids = set(getattr(t, "_contract_product_ids", set()))
            if not template_product_ids and t.product_id:
                template_product_ids = {t.product_id}
            product_specific = bool(template_product_ids)
            if product_specific and product.pk not in template_product_ids:
                continue
            if t.party != expected_party:
                continue

            matching_details = [
                details for details in contract_details_options
                if _contract_detail_matches_template_country(details, t)
            ]
            if not matching_details and use_profile_country_fallback:
                matching_details = [None] if _profile_matches_template_country(expert, t) else []
            if not matching_details:
                continue

            section_match_exact = False
            if t.is_all_sections:
                section_match = True
            else:
                codes_in_template = {
                    entry.get("code", "") for entry in (t.typical_sections_json or [])
                }
                if section_code and section_code in codes_in_template:
                    section_match = True
                    section_match_exact = True
                else:
                    section_match = False

            if not section_match:
                continue

            for details in matching_details:
                expected_contract_type = "smz" if bool(details and details.self_employed) else "gph"
                if t.contract_type == expected_contract_type:
                    candidates.append(
                        (
                            t,
                            section_match_exact,
                            details,
                            group_specific,
                            product_specific,
                            bool((t.country_name or "").strip() or (t.country_code or "").strip()),
                        )
                    )

        if not candidates:
            return None

        exact = [item for item in candidates if item[1]]
        if exact:
            candidates = exact

        def _version_key(item):
            t = item[0]
            try:
                version = int(t.version)
            except (ValueError, TypeError):
                version = 0
            return (1 if item[3] else 0, 1 if item[4] else 0, 1 if item[5] else 0, version)

        candidates.sort(key=_version_key, reverse=True)
        return candidates[0][0], candidates[0][2]

    seen_executors = set()
    unique_entries = []
    executor_to_ids = {}
    executor_to_perfs = {}
    def _contract_creation_group_key(perf):
        if perf.participation_batch_id:
            return ("participation_batch", str(perf.participation_batch_id), perf.executor)
        return ("registration", perf.registration_id, perf.executor)

    for perf in performers:
        key = _contract_creation_group_key(perf)
        executor_to_ids.setdefault(key, []).append(perf.pk)
        executor_to_perfs.setdefault(key, []).append(perf)
        if key in seen_executors:
            continue
        seen_executors.add(key)
        unique_entries.append(perf)

    total = len(unique_entries)

    MIN_CHUNK = 256

    def _padded(line):
        encoded = line.encode()
        if len(encoded) < MIN_CHUNK:
            encoded += b" " * (MIN_CHUNK - len(encoded))
        return encoded

    def _stream():
        try:
            errors = []
            warnings = []
            created_ids = []
            current = 0

            for perf in unique_entries:
                project = perf.registration
                key = _contract_creation_group_key(perf)
                all_perfs_for_executor = executor_to_perfs[key]
                selected_folder_performer = next(
                    (
                        item for item in all_perfs_for_executor
                        if (item.contract_project_disk_folder or "").strip()
                    ),
                    None,
                )
                folder_candidates = [
                    item for item in all_perfs_for_executor
                    if (item.contract_project_disk_folder or "").strip()
                ]
                if not folder_candidates:
                    sibling = (
                        Performer.objects
                        .filter(
                            registration_id=perf.registration_id,
                            executor=perf.executor,
                        )
                        .exclude(contract_project_disk_folder="")
                        .order_by("contract_sent_at", "contract_project_created_at", "id")
                        .first()
                    )
                    if sibling is not None:
                        folder_candidates.append(sibling)
                existing_folder_performer = None
                reused_folder_path = ""
                for candidate in folder_candidates:
                    candidate_path = _reusable_cloud_folder(candidate.contract_project_disk_folder)
                    if candidate_path:
                        existing_folder_performer = candidate
                        reused_folder_path = candidate_path
                        break
                reuse_existing_folder = existing_folder_performer is not None
                selected_batch_id = next((item.contract_batch_id for item in all_perfs_for_executor if item.contract_batch_id), None)
                year_str = sanitize_folder_name(str(project.year) if project.year else "Без года")
                project_folder = contract_project_folder_name(project, all_perfs_for_executor)
                contract_folder = contract_registration_folder_name(project, all_perfs_for_executor)
                base_path = join_cloud_path(
                    disk_root,
                    CONTRACTS_SECTION_FOLDER,
                    year_str,
                    project_folder,
                    contract_folder,
                    CONTRACTS_PERFORMERS_FOLDER,
                )

                executor_name = contract_executor_short_name(perf.executor)
                if reuse_existing_folder:
                    folder_path = normalize_cloud_path(reused_folder_path)
                    folder_name = os.path.basename(folder_path.rstrip("/")) or executor_name
                    if not _ensure_cloud_folder_path(folder_path):
                        errors.append(folder_path)
                        current += 1
                        yield _padded(json.dumps({"current": current, "total": total}) + "\n")
                        continue
                else:
                    if not _ensure_cloud_folder_path(base_path):
                        errors.append(base_path)
                        current += 1
                        yield _padded(json.dumps({"current": current, "total": total}) + "\n")
                        continue

                    existing = _list_contract_folder(base_path)
                    contract_display_id = contract_project_registration_display_id(project) or "Unknown"
                    next_number = 1
                    for item in existing:
                        match = re.match(
                            rf"^{re.escape(contract_display_id)}\s+(\d{{3}})\s",
                            item.get("name", ""),
                        )
                        if match:
                            next_number = max(next_number, int(match.group(1)) + 1)

                    folder_name = sanitize_folder_name(f"{contract_display_id} {next_number:03d} {executor_name}")
                    folder_path = f"{base_path}/{folder_name}"

                    if not _create_contract_folder(folder_path):
                        errors.append(folder_name)
                        current += 1
                        yield _padded(json.dumps({"current": current, "total": total}) + "\n")
                        continue

                if local_cloud is None:
                    warnings.extend(_share_contract_folder_for_nextcloud(perf, folder_path))
                existing_folder_file_id = ""
                existing_folder_public_url = ""
                if existing_folder_performer and local_cloud is None:
                    existing_folder_file_id = existing_folder_performer.contract_project_folder_file_id or ""
                    existing_folder_public_url = existing_folder_performer.contract_project_folder_link or ""
                folder_file_id = existing_folder_file_id or (
                    "" if local_cloud is not None else _resolve_contract_project_nextcloud_file_id(folder_path)
                )
                folder_public_url = existing_folder_public_url
                if local_cloud is None and not folder_public_url:
                    try:
                        published_folder_url = cloud_publish_resource(request.user, folder_path)
                        if published_folder_url:
                            folder_public_url = published_folder_url
                    except Exception:
                        pass

                created_ids.extend(executor_to_ids[key])

                now_dt = timezone.now()
                _group_kind, group_value, executor_val = key
                if selected_folder_performer is not None:
                    is_addendum = bool(existing_folder_performer.contract_is_addendum)
                    addendum_number = existing_folder_performer.contract_addendum_number
                else:
                    existing_batch_filter = Q(executor=executor_val)
                    if perf.participation_batch_id:
                        existing_batch_filter &= Q(participation_batch_id=perf.participation_batch_id)
                    else:
                        existing_batch_filter &= Q(registration_id=group_value)
                    existing_batch_count = (
                        Performer.objects
                        .filter(existing_batch_filter, contract_batch_id__isnull=False)
                        .filter(Q(contract_project_created=True) | ~Q(contract_project_disk_folder=""))
                        .values("contract_batch_id")
                        .distinct()
                        .count()
                    )
                    is_addendum = existing_batch_count > 0
                    addendum_number = existing_batch_count if is_addendum else None

                if is_addendum:
                    first_performer_filter = Q(executor=executor_val)
                    if perf.participation_batch_id:
                        first_performer_filter &= Q(participation_batch_id=perf.participation_batch_id)
                    else:
                        first_performer_filter &= Q(registration_id=group_value)
                    first_performer = (
                        Performer.objects
                        .filter(first_performer_filter, contract_batch_id__isnull=False, contract_is_addendum=False)
                        .filter(Q(contract_project_created=True) | ~Q(contract_project_disk_folder=""))
                        .order_by("contract_sent_at", "id")
                        .first()
                    )
                    base_date = (
                        first_performer.contract_sent_at
                        if first_performer and first_performer.contract_sent_at
                        else now_dt
                    )
                else:
                    base_date = now_dt

                perf.contract_is_addendum = is_addendum
                perf.contract_addendum_number = addendum_number
                existing_contract_number = (perf.contract_number or "").strip()
                generated_contract_number = build_contract_number(perf, base_date, addendum_number)
                if is_addendum and existing_contract_number:
                    generated_base_number = build_contract_number(perf, base_date)
                    pre_contract_number = (
                        existing_contract_number
                        if existing_contract_number != generated_base_number
                        else generated_contract_number
                    )
                else:
                    pre_contract_number = existing_contract_number or generated_contract_number
                perf.contract_number = pre_contract_number

                seen_templates = set()
                unique_section_perfs = {}
                for p in all_perfs_for_executor:
                    sec_id = p.typical_section_id
                    if sec_id not in unique_section_perfs:
                        unique_section_perfs[sec_id] = p

                for p in unique_section_perfs.values():
                    template_match = _find_template(p)
                    if not template_match:
                        warnings.append(
                            f"Образец шаблона не найден: {executor_name}"
                            + (f" ({p.typical_section.code})" if p.typical_section else "")
                        )
                        continue
                    tmpl, contract_details = template_match

                    if tmpl.pk in seen_templates:
                        continue
                    seen_templates.add(tmpl.pk)
                    upload_name = ""

                    try:
                        tmpl.file.open("rb")
                        try:
                            file_data = tmpl.file.read()
                        finally:
                            tmpl.file.close()

                        if all_variables:
                            scalars, lists = resolve_variables(
                                perf, all_variables,
                                all_performers=all_perfs_for_executor,
                                contract_details=contract_details,
                            )
                            if scalars or lists:
                                file_data = process_template(
                                    file_data, scalars,
                                    list_replacements=lists or None,
                                    default_language_code="ru-RU",
                                    fresh_multilevel_list_keys={"[[chapters_name]]"},
                                )

                        original_name = tmpl.file.name.split("/")[-1]
                        upload_name = _contract_project_file_name(
                            perf,
                            original_name,
                            batch_performers=all_perfs_for_executor,
                        )
                        upload_path = f"{folder_path}/{upload_name}"
                        if not _upload_contract_file(request.user, upload_path, file_data):
                            errors.append(f"Загрузка файла: {upload_name} → {folder_name}")
                        else:
                            file_update_kwargs = {
                                "contract_file": upload_name,
                                "contract_project_file_id": "",
                                "contract_pdf_file": "",
                                "contract_pdf_link": "",
                                "contract_pdf_file_id": "",
                                "contract_signed_pdf_file": "",
                                "contract_signed_pdf_link": "",
                                "contract_signed_pdf_file_id": "",
                            }
                            if local_cloud is None:
                                file_id = _resolve_contract_project_nextcloud_file_id(
                                    upload_path,
                                    attempts=3,
                                    retry_delay=0.2,
                                )
                                if file_id:
                                    file_update_kwargs["contract_project_file_id"] = file_id
                                try:
                                    public_url = cloud_publish_resource(request.user, upload_path)
                                    if public_url:
                                        file_update_kwargs["contract_project_link"] = public_url
                                except Exception:
                                    pass
                            Performer.objects.filter(
                                pk__in=executor_to_ids[key],
                            ).update(**file_update_kwargs)
                    except Exception as exc:
                        logger.exception("Не удалось собрать проект договора из образца %s", tmpl.sample_name)
                        errors.append(f"Чтение файла: {tmpl.sample_name}: {exc}")

                batch_id = (
                    selected_batch_id
                    or perf.contract_batch_id
                    or uuid.uuid4()
                )
                stored_folder_path = folder_path
                if local_cloud is not None:
                    stored_folder_path = encode_local_contract_path(local_cloud.local_path(folder_path))
                update_kwargs = dict(
                    contract_batch_id=batch_id,
                    contract_is_addendum=is_addendum,
                    contract_addendum_number=addendum_number,
                    contract_project_disk_folder=stored_folder_path,
                    contract_project_folder_link=folder_public_url,
                )
                if local_cloud is not None:
                    update_kwargs["contract_project_folder_file_id"] = ""
                    update_kwargs["contract_project_link"] = ""
                    update_kwargs["contract_project_file_id"] = ""
                elif folder_file_id:
                    update_kwargs["contract_project_folder_file_id"] = folder_file_id
                if pre_contract_number:
                    update_kwargs["contract_number"] = pre_contract_number
                Performer.objects.filter(pk__in=executor_to_ids[key]).update(**update_kwargs)

                current += 1
                yield _padded(json.dumps({"current": current, "total": total}) + "\n")

            if created_ids:
                created_set = set(created_ids)
                created_qs = Performer.objects.filter(pk__in=created_set)
                created_qs.update(
                    contract_project_created=True,
                    contract_project_created_at=timezone.now(),
                )
                created_qs.filter(contract_date__isnull=True).update(
                    contract_date=timezone.now().date(),
                )

            if errors:
                msg = f"Ошибки: {'; '.join(errors)}"
                if warnings:
                    msg += f"\nПредупреждения: {'; '.join(warnings)}"
                yield _padded(json.dumps({"ok": False, "error": msg}) + "\n")
            elif warnings:
                yield _padded(json.dumps({
                    "ok": True,
                    "message": "Проекты договоров созданы.",
                    "warnings": warnings,
                }) + "\n")
            else:
                yield _padded(json.dumps({
                    "ok": True,
                    "message": "Проекты договоров успешно созданы.",
                }) + "\n")
        except CloudStorageNotReadyError as exc:
            yield _padded(json.dumps({"ok": False, "error": str(exc)}) + "\n")

    resp = StreamingHttpResponse(_stream(), content_type="application/x-ndjson")
    resp["Cache-Control"] = "no-cache, no-store"
    resp["X-Accel-Buffering"] = "no"
    return resp


@login_required
@user_passes_test(staff_required)
@require_GET
def contract_project_local_download(request, pk):
    performer = get_object_or_404(Performer, pk=pk)
    payload = read_local_contract_docx(
        performer.contract_project_disk_folder,
        performer.contract_file,
    )
    if not payload:
        raise Http404("Файл не найден.")
    path, file_bytes = payload
    filename = os.path.basename(performer.contract_file or "") or path.name
    return FileResponse(BytesIO(file_bytes), as_attachment=True, filename=filename)


@login_required
@require_GET
def identifier_for_country(request):
    country_id = request.GET.get("country_id")
    if not country_id:
        return JsonResponse({"identifier": ""})
    lei = (
        LegalEntityIdentifier.objects
        .filter(country_id=country_id)
        .values_list("identifier", flat=True)
        .first()
    )
    return JsonResponse({"identifier": lei or ""})