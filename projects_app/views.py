from django.contrib.auth.decorators import login_required, user_passes_test
from django.core import signing
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.db import models, transaction
from django.db.models import Max, Q
from django.db.models.functions import Trim
from django import forms
from django.utils import timezone
from classifiers_app.models import LegalEntityIdentifier, LegalEntityRecord
from .models import (
    LegalEntity,
    Performer,
    PerformerParticipationSnapshot,
    ProjectRegistration,
    ProjectRegistrationProduct,
    RegistrationWorkspaceFolder,
    WorkVolume,
    WorkVolumeItem,
    _ensure_performer_rows_for_work_item,
    _sync_project_registration_primary_product,
)
from .forms import (
    ProjectRegistrationForm,
    ContractConditionsForm,
    WorkVolumeForm,
    PerformerForm,
    BootstrapMixin,
    LegalEntityForm,
    _project_manager_choices,
    _resolve_project_manager_choice,
)

import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import quote

from experts_app.models import ExpertProfile
from core.cloud_storage import (
    CloudStorageNotReadyError,
    build_project_folder_name,
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
    PROJECTS_HEAD_GROUP,
    TypicalSection,
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
    normalize_delivery_channels,
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
from contracts_app.services import build_contract_file_name, contract_executor_short_name

PROJECTS_PARTIAL_TEMPLATE = "projects_app/projects_partial.html"
REG_FORM_TEMPLATE       = "projects_app/registration_form.html"
CONTRACT_FORM_TEMPLATE  = "projects_app/contract_form.html"
WORK_FORM_TEMPLATE      = "projects_app/work_form.html"
LEGAL_FORM_TEMPLATE     = "projects_app/legal_entity_form.html"

PERF_FORM_TEMPLATE    = "projects_app/performer_form.html"
PERFORMERS_PARTIAL_TEMPLATE = "projects_app/performers_partial.html"

HX_TRIGGER_HEADER = "HX-Trigger"
HX_PERFORMERS_UPDATED_EVENT = "performers-updated"
HX_PROJECTS_UPDATED_EVENT = "projects-updated"
CONTRACT_DOCX_SOURCE_TOKEN_SALT = "projects_app.contract_docx_source"
CONTRACT_PERFORMER_FACSIMILE_PLACEHOLDER = "[[facsimile_prfrm]]"
CONTRACT_IMAGE_PLACEHOLDER_SPECS = (
    ("[[seal]]", "Печать организации"),
    ("[[facsimile_imcm]]", "Подпись руководителя организации"),
)

def staff_required(user):
    return user.is_authenticated and user.is_staff


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


def _annotate_registration_number_groups(registrations):
    items = list(registrations)
    start = 0
    while start < len(items):
        current_number = items[start].number
        end = start + 1
        while end < len(items) and items[end].number == current_number:
            end += 1
        group_size = end - start
        for offset, registration in enumerate(items[start:end], start=1):
            registration.is_first_for_number = offset == 1
            registration.is_continuation = offset > 1
            registration.has_next_for_number = offset < group_size
        start = end
    return items


def _projects_context(user=None):
    expert_project_ids = _confirmed_project_ids_for_expert(user)
    is_expert = expert_project_ids is not None
    product_prefetch = models.Prefetch(
        "product_links",
        queryset=ProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    registrations = (
        ProjectRegistration.objects
        .select_related("country", "asset_owner_country", "group_member", "type")
        .prefetch_related(product_prefetch)
        .all()
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
    legal_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(product_prefetch)
        .filter(legal_entities__isnull=False)
        .distinct()
        .order_by("-number", "-id")
    )
    if expert_project_ids is not None:
        legal_projects = legal_projects.filter(id__in=expert_project_ids)
    work_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(product_prefetch)
        .filter(work_items__isnull=False)
        .distinct()
        .order_by("-number", "-id")
    )
    if expert_project_ids is not None:
        work_projects = work_projects.filter(id__in=expert_project_ids)
    reg_filter_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .prefetch_related(product_prefetch)
        .order_by("-number", "-id")
    )
    if expert_project_ids is not None:
        reg_filter_projects = reg_filter_projects.filter(id__in=expert_project_ids)
    return {
        "registrations": _annotate_registration_number_groups(registrations),
        "reg_filter_projects": reg_filter_projects,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "work_items": work_items,
        "work_projects": work_projects,
        "legal_entities": legal_entities,
        "legal_projects": legal_projects,
        "registration_status_choices": ProjectRegistration.STATUS_CHOICES,
        "registration_manager_choices": _project_manager_choices("", show_prs_label=False),
        "is_expert": is_expert,
    }


def _short_fio_label(value):
    parts = " ".join(str(value or "").split()).split(" ")
    if not parts or not parts[0]:
        return ""
    initials = "".join(f"{part[0]}." for part in parts[1:3] if part)
    return f"{parts[0]} {initials}".strip()


def _short_date_label(value):
    return value.strftime("%d.%m.%Y") if value else ""


def _product_option_label(product):
    return " ".join(
        part for part in ((product.short_name or "").strip(), (product.display_name or "").strip()) if part
    )


def _registration_product_catalog():
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


def _registration_selected_type_rows(form, registration=None):
    if form.is_bound:
        consulting_types = _request_list(form.data, "type_consulting")
        service_categories = _request_list(form.data, "type_service_category")
        service_subtypes = _request_list(form.data, "type_service_subtype")
        product_ids = _request_list(form.data, "type_id")
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
        }]
    if registration is None:
        registration = getattr(form, "instance", None)
    if registration and getattr(registration, "pk", None):
        return [
            {
                "rank": index,
                "consulting_type": (product.consulting_type_display or "").strip(),
                "service_category": (product.service_category_display or "").strip(),
                "service_subtype": (product.service_subtype_display or "").strip(),
                "product_id": str(product.pk),
            }
            for index, product in enumerate(registration.ordered_products(), start=1)
        ] or [{
            "rank": 1,
            "consulting_type": "",
            "service_category": "",
            "service_subtype": "",
            "product_id": "",
        }]
    return [{
        "rank": 1,
        "consulting_type": "",
        "service_category": "",
        "service_subtype": "",
        "product_id": "",
    }]


def _registration_form_context(form, action, registration=None):
    catalog = _registration_product_catalog()
    ranked_products = _registration_selected_type_rows(form, registration)
    return {
        "form": form,
        "action": action,
        "registration": registration,
        "allow_multiple_products": getattr(form, "allow_multiple_products", True),
        "product_options": catalog["options"],
        "registration_type_meta_json": json.dumps(catalog["meta"], ensure_ascii=False),
        "ranked_products": ranked_products,
    }


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
    "input_data",
    "stage1_weeks",
    "stage2_weeks",
    "stage3_weeks",
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
    product_ids = list(getattr(form, "cleaned_type_ids", []))
    with transaction.atomic():
        start_position = _next_position(ProjectRegistration)
        for offset, product_id in enumerate(product_ids):
            obj = base_obj if offset == 0 else _copy_registration_form_values(base_obj)
            obj.position = start_position + offset
            obj.save()
            _save_ranked_registration_products(obj, [product_id])
        ProjectRegistration.refresh_number_sequences([base_obj.number])
    _sync_to_legal_entity_record(
        base_obj.customer, base_obj.country, base_obj.identifier,
        base_obj.registration_number, base_obj.registration_date, request.user,
        business_entity_source="[Проекты / Заказчик]",
        registration_region=base_obj.registration_region,
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    _sync_to_legal_entity_record(
        base_obj.asset_owner, base_obj.asset_owner_country, base_obj.asset_owner_identifier,
        base_obj.asset_owner_registration_number, base_obj.asset_owner_registration_date, request.user,
        business_entity_source="[Проекты / Владелец активов]",
        registration_region=base_obj.asset_owner_region,
        **_sync_selection_kwargs(request, "asset_owner_autocomplete"),
    )
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_delete(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    number = reg.number
    reg.delete()
    ProjectRegistration.refresh_number_sequences([number])
    return _render_projects_updated(request)

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_launch(request, pk: int):
    updated = (
        ProjectRegistration.objects
        .filter(pk=pk, status="Не начат")
        .update(status="В работе")
    )
    if not updated:
        reg = get_object_or_404(ProjectRegistration.objects.only("id", "status"), pk=pk)
        return JsonResponse(
            {
                "ok": False,
                "error": "Запуск доступен только для проектов со статусом «Не начат».",
                "status": reg.status,
            },
            status=400,
        )

    return JsonResponse({"ok": True, "status": "В работе"})

@login_required
@user_passes_test(staff_required)
@require_POST
def registration_status_update(request, pk: int):
    status_value = (request.POST.get("status") or "").strip()
    valid_statuses = {value for value, _label in ProjectRegistration.STATUS_CHOICES}
    if status_value not in valid_statuses:
        return JsonResponse({"ok": False, "error": "Некорректный статус проекта."}, status=400)

    reg = get_object_or_404(ProjectRegistration.objects.only("id", "status"), pk=pk)
    if reg.status != status_value:
        reg.status = status_value
        reg.save(update_fields=["status"])

    return JsonResponse({"ok": True, "status": reg.status})

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

    return JsonResponse(
        {
            "ok": True,
            "deadline": reg.deadline.isoformat() if reg.deadline else "",
            "deadlineLabel": _short_date_label(reg.deadline),
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
        return render(request, CONTRACT_FORM_TEMPLATE, {
            "form": form, "action": "edit", "registration": reg,
        })
    form.save()
    return _render_projects_updated(request)


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

    reg = ProjectRegistration.objects.select_related("type", "country").filter(pk=pid).first()
    if not reg:
        return JsonResponse({"ok": False})

    return JsonResponse({
        "ok": True,
        "type": reg.type_short_display,
        "type_short": reg.type_short_display,
        "name": reg.name or "",
        "project_manager": reg.project_manager_prs_id or reg.project_manager or "",
        "country_id": reg.country_id or "",
    })


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_create(request):
    if request.method == "GET":
        form = WorkVolumeForm()
        return render(request, WORK_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = WorkVolumeForm(request.POST)
    if not form.is_valid():
        return render(request, WORK_FORM_TEMPLATE, {"form": form, "action": "create"})
    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(WorkVolume, {"project": obj.project})
    obj.save()
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

# Редактирование регистрации
@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def registration_form_edit(request, pk: int):
    reg = get_object_or_404(ProjectRegistration, pk=pk)
    if request.method == "GET":
        form = ProjectRegistrationForm(instance=reg, allow_multiple_products=False)
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "edit", reg))
    form = ProjectRegistrationForm(request.POST, instance=reg, allow_multiple_products=False)
    if not form.is_valid():
        return render(request, REG_FORM_TEMPLATE, _registration_form_context(form, "edit", reg))
    obj = form.save()
    _save_ranked_registration_products(obj, getattr(form, "cleaned_type_ids", []))
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
        .select_related("product", "expertise_dir")
        .prefetch_related("ranked_specialties", "ranked_specialties__specialty")
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
@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def work_form_edit(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    if request.method == "GET":
        form = WorkVolumeForm(instance=item)
        return render(request, WORK_FORM_TEMPLATE, {
            "form": form, "action": "edit", "work": item
        })
    form = WorkVolumeForm(request.POST, instance=item)
    if not form.is_valid():
        return render(request, WORK_FORM_TEMPLATE, {
            "form": form, "action": "edit", "work": item
        })
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


def _delete_related_performers_for_work_item(item: WorkVolume):
    """
    Удаляет связанные строки исполнителей:
      - новые строки, уже привязанные через work_item
      - старые строки без work_item, совпадающие по проекту/активу
    """
    asset_name = (item.asset_name or item.name or "").strip()
    filters = Q(work_item=item)
    if asset_name:
        filters |= Q(
            work_item__isnull=True,
            registration=item.project,
            asset_name=asset_name,
        )
    Performer.objects.filter(filters).delete()


@login_required
@user_passes_test(staff_required)
@require_POST
def work_delete(request, pk: int):
    item = get_object_or_404(WorkVolume, pk=pk)
    pid = item.project_id
    _delete_related_performers_for_work_item(item)
    item.delete()
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
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx - 1]
        WorkVolume.objects.filter(pk=cur.id).update(position=prev.position)
        WorkVolume.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_work_positions(pid)

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
        .only("id", "position")
    )
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx + 1]
        WorkVolume.objects.filter(pk=cur.id).update(position=nxt.position)
        WorkVolume.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_work_positions(pid)

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
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "create"})
    entity = form.save(commit=False)
    if not getattr(entity, "position", 0):
        entity.position = _next_position(LegalEntity, {"project": entity.project})
    entity.save()
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
        return render(request, LEGAL_FORM_TEMPLATE, {"form": form, "action": "edit", "legal_entity": entity})
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
    pid = entity.project_id
    entity.delete()
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

def _performers_context(user=None):
    expert_project_ids = _confirmed_project_ids_for_expert(user)
    is_expert = expert_project_ids is not None
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
            "typical_section__expertise_direction",
            "employee",
            "employee__user",
            "currency",
        )
        .prefetch_related(registration_products_prefetch)
        .order_by("position", "id")
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
            "typical_section__expertise_direction",
            "employee",
            "employee__user",
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
        .filter(id__in=participation_project_ids)
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
    request_sent_initial = timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    performer_project_ids = performers.values_list("registration_id", flat=True).distinct()
    performer_projects = (
        ProjectRegistration.objects
        .select_related("type")
        .filter(id__in=performer_project_ids)
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
            ts_dir = _effective_direction_id(p.typical_section)
            in_dh_direction = bool(ts_dir and ts_dir == dh_department_id)
            p.dh_checkbox_locked = (
                not in_dh_direction
                or (p.employee_id and p.employee.user_id == user.id)
                or p.pk in dh_notified_ids
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
            r.registration_id or 0,
            r.executor or "",
            status_order,
            getattr(r, "asset_name", "") or "",
        )
    participation_display_rows.sort(key=_participation_sort_key)

    return {
        "performers": performers,
        "performer_projects": performer_projects,
        "participation_performers": participation_performers,
        "participation_display_rows": participation_display_rows,
        "participation_projects": participation_projects,
        "participation_request_sent_initial": request_sent_initial,
        "info_request_performers": info_request_performers,
        "info_request_projects": info_request_projects,
        "info_request_sent_initial": request_sent_initial,
        "contract_performers": contract_performers,
        "contract_projects": contract_projects,
        "contract_request_sent_initial": request_sent_initial,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "user_is_direction_head": user_is_direction_head,
        "is_expert": is_expert,
        "has_active_smtp_connection": has_active_smtp_connection,
    }

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

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
                "direction_id": s.expertise_direction_id,
                "specialty_ids": [
                    link.specialty_id
                    for link in s.ranked_specialties.all()
                    if link.specialty_id
                ],
            }
            for s in ordered_sections
        ]

    executor_grade_map = _build_executor_grade_map()
    executor_options = _build_executor_options_payload()
    living_wage_map = _build_living_wage_map()
    tariff_map = _build_tariff_map()
    tariff_hours_map = _build_tariff_hours_map()
    direction_hourly_rate_map = _build_direction_hourly_rate_map()

    return {
        "form": form,
        "action": action,
        "performer": performer,
        "reg_map_json": json.dumps(reg_map, ensure_ascii=False),
        "assets_map_json": json.dumps(assets_map, ensure_ascii=False),
        "sections_map_json": json.dumps(sections_map, ensure_ascii=False),
        "executor_options_json": json.dumps(executor_options, ensure_ascii=False),
        "executor_grade_json": json.dumps(executor_grade_map, ensure_ascii=False),
        "living_wage_json": json.dumps(living_wage_map, ensure_ascii=False),
        "tariff_json": json.dumps(tariff_map, ensure_ascii=False),
        "tariff_hours_json": json.dumps(tariff_hours_map, ensure_ascii=False),
        "direction_hourly_rate_json": json.dumps(direction_hourly_rate_map, ensure_ascii=False),
    }

def _render_performers_updated(request):
    resp = render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))
    resp[HX_TRIGGER_HEADER] = HX_PERFORMERS_UPDATED_EVENT
    return resp

@login_required
@require_http_methods(["GET"])
def performers_partial(request):
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

def _next_performer_position():
    mx = Performer.objects.aggregate(Max("position")).get("position__max") or 0
    return mx + 1


def _effective_direction_id(typical_section):
    """Return the OrgUnit PK of the expertise direction, or None if absent or 'директорское' (level 1)."""
    if not typical_section:
        return None
    direction = getattr(typical_section, "expertise_direction", None)
    if not direction:
        return None
    if direction.level == 1:
        return None
    return direction.pk


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
    ts_direction_id = _effective_direction_id(performer.typical_section)
    if emp.role in (PROJECTS_HEAD_GROUP, DIRECTION_DIRECTOR_GROUP):
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


def _resolve_contract_project_nextcloud_file_id(path: str) -> str:
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

    try:
        items = client.list_resources(client.username, parent_path, limit=1000)
    except NextcloudApiError:
        return ""

    for item in items:
        item_path = _normalize_nextcloud_contract_resource_path(item.get("path") or "")
        if item_path == normalized_path:
            return str(item.get("file_id") or "").strip()
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
        obj.position = _next_performer_position()
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
    p = get_object_or_404(Performer.objects.select_related("typical_section", "typical_section__expertise_direction", "employee", "employee__user"), pk=pk)
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
def participation_request(request):
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
        )
        .filter(pk__in=performer_ids)
        .order_by("position", "id")
    )
    if len(selected_performers) != len(performer_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

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


def _build_contract_number(performer, sent_at, addendum_number=None):
    reg = getattr(performer, "registration", None)
    if not reg or getattr(reg, "group_alpha2", "") != "RU":
        return ""
    parts = (performer.executor or "").split()
    if len(parts) < 2:
        return ""
    initials = parts[0][0] + parts[1][0]
    local_dt = timezone.localtime(sent_at)
    base = f"IMCM/{reg.number}-{initials}/{local_dt:%m-%y}"
    if addendum_number is not None:
        base = f"{base} ДС{addendum_number}"
    return base


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
@require_POST
def performer_delete(request, pk: int):
    p = get_object_or_404(Performer, pk=pk)
    p.delete()
    return _render_performers_updated(request)

def _normalize_performer_positions():
    items = Performer.objects.order_by("position", "id").only("id", "position")
    for i, it in enumerate(items, start=1):
        if it.position != i:
            Performer.objects.filter(pk=it.pk).update(position=i)

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_up(request, pk: int):
    _normalize_performer_positions()
    items = list(Performer.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx > 0:
        cur, prev = items[idx], items[idx-1]
        Performer.objects.filter(pk=cur.id).update(position=prev.position)
        Performer.objects.filter(pk=prev.id).update(position=cur.position)
        _normalize_performer_positions()
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

@login_required
@require_http_methods(["POST", "GET"])
def performer_move_down(request, pk: int):
    _normalize_performer_positions()
    items = list(Performer.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, it in enumerate(items) if it.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        cur, nxt = items[idx], items[idx+1]
        Performer.objects.filter(pk=cur.id).update(position=nxt.position)
        Performer.objects.filter(pk=nxt.id).update(position=cur.position)
        _normalize_performer_positions()
    # ВОЗВРАЩАЕМ ТОЛЬКО ФРАГМЕНТ, БЕЗ HX-Trigger
    return render(request, PERFORMERS_PARTIAL_TEMPLATE, _performers_context(request.user))

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
    folders = list(qs.values("id", "level", "name", "position"))
    return JsonResponse(
        {
            "folders": folders,
            "is_custom": is_custom,
            "storage_label": get_primary_cloud_storage_label(),
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

    objects = []
    for i, row in enumerate(rows):
        level = row.get("level", 1)
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if level not in (1, 2, 3):
            level = 1
        objects.append(RegistrationWorkspaceFolder(user=owner, level=level, name=name, position=i))

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
    folders = list(qs.values("id", "level", "name", "position"))
    return JsonResponse({"ok": True, "folders": folders, "is_custom": is_custom})


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
        key = (performer.registration_id, performer.executor, normalize_cloud_path(folder), docx_name)
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
        key = (performer.registration_id, performer.executor, normalize_cloud_path(folder), docx_name)
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

    performers = list(
        Performer.objects
        .filter(pk__in=ids, contract_sent_at__isnull=True)
        .select_related(
            "registration", "registration__type", "registration__country",
            "typical_section", "employee", "contract_group_member",
        )
        .order_by("position", "id")
    )
    if not performers:
        return JsonResponse({"ok": False, "error": "Нет доступных строк для создания проекта договора."}, status=400)

    try:
        disk_root = get_selected_root_path(request.user)
    except CloudStorageNotReadyError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    if not disk_root:
        return JsonResponse({"ok": False, "error": "Не выбрана папка в основном облачном хранилище."}, status=400)

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

    def _contract_project_file_name(perf, original_name):
        ext = os.path.splitext(original_name or "")[1] or ".docx"
        return build_contract_file_name(perf, extension=ext)

    def _ensure_cloud_folder_path(path):
        normalized = normalize_cloud_path(path)
        if normalized == "/":
            return True
        current = ""
        for part in normalized.strip("/").split("/"):
            current = f"{current}/{part}" if current else f"/{part}"
            if not cloud_create_folder(request.user, current):
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
    for perf in performers:
        key = (perf.registration_id, perf.executor)
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
                key = (perf.registration_id, perf.executor)
                all_perfs_for_executor = executor_to_perfs[key]
                selected_folder_performer = next(
                    (
                        item for item in all_perfs_for_executor
                        if (item.contract_project_disk_folder or "").strip()
                    ),
                    None,
                )
                existing_folder_performer = selected_folder_performer
                if existing_folder_performer is None:
                    existing_folder_performer = (
                        Performer.objects
                        .filter(
                            registration_id=perf.registration_id,
                            executor=perf.executor,
                        )
                        .exclude(contract_project_disk_folder="")
                        .order_by("contract_sent_at", "contract_project_created_at", "id")
                        .first()
                    )
                reuse_existing_folder = existing_folder_performer is not None
                selected_batch_id = next((item.contract_batch_id for item in all_perfs_for_executor if item.contract_batch_id), None)
                year_str = sanitize_folder_name(str(project.year) if project.year else "Без года")
                project_folder = build_project_folder_name(project)
                base_path = join_cloud_path(
                    disk_root,
                    CONTRACTS_SECTION_FOLDER,
                    year_str,
                    project_folder,
                    CONTRACTS_PERFORMERS_FOLDER,
                )

                executor_name = contract_executor_short_name(perf.executor)
                if reuse_existing_folder:
                    folder_path = normalize_cloud_path(existing_folder_performer.contract_project_disk_folder)
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

                    existing = list_folder_resources(request.user, base_path, limit=1000)
                    next_number = 0
                    for item in existing:
                        match = re.match(r"^(\d{3})\s", item.get("name", ""))
                        if match:
                            next_number = max(next_number, int(match.group(1)) + 1)

                    folder_name = sanitize_folder_name(f"{next_number:03d} {executor_name}")
                    folder_path = f"{base_path}/{folder_name}"

                    if not cloud_create_folder(request.user, folder_path):
                        errors.append(folder_name)
                        current += 1
                        yield _padded(json.dumps({"current": current, "total": total}) + "\n")
                        continue

                warnings.extend(_share_contract_folder_for_nextcloud(perf, folder_path))
                existing_folder_file_id = ""
                existing_folder_public_url = ""
                if existing_folder_performer:
                    existing_folder_file_id = existing_folder_performer.contract_project_folder_file_id or ""
                    existing_folder_public_url = existing_folder_performer.contract_project_folder_link or ""
                folder_file_id = existing_folder_file_id or _resolve_contract_project_nextcloud_file_id(folder_path)
                folder_public_url = existing_folder_public_url
                if not folder_public_url:
                    try:
                        published_folder_url = cloud_publish_resource(request.user, folder_path)
                        if published_folder_url:
                            folder_public_url = published_folder_url
                    except Exception:
                        pass

                created_ids.extend(executor_to_ids[key])

                now_dt = timezone.now()
                reg_id, executor_val = key
                if selected_folder_performer is not None:
                    is_addendum = bool(existing_folder_performer.contract_is_addendum)
                    addendum_number = existing_folder_performer.contract_addendum_number
                else:
                    existing_batch_count = (
                        Performer.objects
                        .filter(
                            registration_id=reg_id,
                            executor=executor_val,
                            contract_batch_id__isnull=False,
                        )
                        .filter(Q(contract_project_created=True) | ~Q(contract_project_disk_folder=""))
                        .values("contract_batch_id")
                        .distinct()
                        .count()
                    )
                    is_addendum = existing_batch_count > 0
                    addendum_number = existing_batch_count if is_addendum else None

                if is_addendum:
                    first_performer = (
                        Performer.objects
                        .filter(
                            registration_id=reg_id,
                            executor=executor_val,
                            contract_batch_id__isnull=False,
                            contract_is_addendum=False,
                        )
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
                generated_contract_number = _build_contract_number(perf, base_date, addendum_number)
                if is_addendum and existing_contract_number:
                    generated_base_number = _build_contract_number(perf, base_date)
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
                                )

                        original_name = tmpl.file.name.split("/")[-1]
                        upload_name = _contract_project_file_name(perf, original_name)
                        upload_path = f"{folder_path}/{upload_name}"
                        if not cloud_upload_file(request.user, upload_path, file_data):
                            errors.append(f"Загрузка файла: {upload_name} → {folder_name}")
                        else:
                            file_update_kwargs = {
                                "contract_file": upload_name,
                                "contract_pdf_file": "",
                                "contract_pdf_link": "",
                                "contract_pdf_file_id": "",
                                "contract_signed_pdf_file": "",
                                "contract_signed_pdf_link": "",
                                "contract_signed_pdf_file_id": "",
                            }
                            file_id = _resolve_contract_project_nextcloud_file_id(upload_path)
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
                    except Exception:
                        errors.append(f"Чтение файла: {tmpl.sample_name}")

                batch_id = (
                    selected_batch_id
                    or perf.contract_batch_id
                    or uuid.uuid4()
                )
                update_kwargs = dict(
                    contract_batch_id=batch_id,
                    contract_is_addendum=is_addendum,
                    contract_addendum_number=addendum_number,
                    contract_project_disk_folder=folder_path,
                    contract_project_folder_link=folder_public_url,
                )
                if folder_file_id:
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