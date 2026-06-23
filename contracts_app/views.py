import logging
import os
import json
from datetime import date as dt_date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models, transaction
from django.db.models import Count, Max, Sum, Q
from django.db.models.functions import Trim
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.template.loader import render_to_string
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
from contacts_app.models import CitizenshipRecord
from group_app.models import GroupMember
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from nextcloud_app.models import NextcloudUserLink
from notifications_app.models import Notification, NotificationPerformerLink
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, EXPERT_GROUP, LAWYER_GROUP
from proposals_app.models import ProposalRegistration, ProposalRegistrationProduct
from projects_app.models import Performer, ProjectRegistration, ProjectRegistrationProduct
from smtp_app.models import ExternalSMTPAccount
from users_app.forms import FREELANCER_LABEL
from users_app.models import Employee
from .forms import (
    ContractEditForm,
    ContractProjectRegistrationForm,
    ContractSigningForm,
    ContractSubjectForm,
    ContractTemplateForm,
    ContractVariableForm,
    build_contract_project_form_from_proposal,
)
from .models import (
    ContractProjectRegistration,
    ContractProjectRegistrationProduct,
    ContractReturnComment,
    ContractSubject,
    ContractTemplate,
    ContractVariable,
    _sync_contract_project_registration_primary_product,
)
from .services import (
    contract_batch_type_display,
    contract_project_number_display,
    contract_stage_order,
)

logger = logging.getLogger(__name__)


CONTRACT_PAYMENT_SCHEDULE_UI_COLUMNS = [
    {"picker_value": "number", "data_col": "number", "source_column": "number", "label": "Номер"},
    {"picker_value": "tkp-id", "data_col": "tkp-id", "source_column": "tkp_id", "label": "ТКП ID"},
    {
        "picker_value": "agreement-type",
        "data_col": "agreement-type",
        "source_column": "agreement_type",
        "label": "Вид соглашения",
    },
    {"picker_value": "sub-number", "data_col": "sub-number", "source_column": "sub_number", "label": "№"},
    {"picker_value": "group", "data_col": "group", "source_column": "group", "label": "Группа"},
    {"picker_value": "project-id", "data_col": "project-id", "source_column": "project_id", "label": "Договор ID"},
    {
        "picker_value": "contract-number",
        "data_col": "contract-number",
        "source_column": "contract_number",
        "label": "Номер договора",
    },
    {"picker_value": "type", "data_col": "type", "source_column": "type", "label": "Тип"},
    {"picker_value": "name", "data_col": "name", "source_column": "name", "label": "Название"},
    {"picker_value": "stage", "data_col": "stage", "source_column": "stage", "label": "Этап"},
    {
        "picker_value": "evaluation-date",
        "data_col": "evaluation-date",
        "source_column": "evaluation_date",
        "label": "Дата оценки",
    },
    {"picker_value": "start-date", "data_col": "start-date", "source_column": "start_date", "label": "Дата начала"},
    {"picker_value": "term", "data_col": "term", "source_column": "term", "label": "Срок предв. отчёта"},
    {
        "picker_value": "preliminary-report-date",
        "data_col": "preliminary-report-date",
        "source_column": "preliminary_report_date",
        "label": "Дата предв. отчёта",
    },
    {
        "picker_value": "final-report-weeks",
        "data_col": "final-report-weeks",
        "source_column": "final_report_term_weeks",
        "label": "Срок итог. отчёта",
    },
    {
        "picker_value": "final-report-date",
        "data_col": "final-report-date",
        "source_column": "final_report_date",
        "label": "Дата итог. отчёта",
    },
    {
        "picker_value": "advance-percent",
        "data_col": "advance-percent",
        "source_column": "advance_percent",
        "label": "Предоплата, проц.",
        "default_hidden": True,
    },
    {
        "picker_value": "advance-term",
        "data_col": "advance-term",
        "source_column": "advance_term",
        "label": "Предоплата, срок дн.",
    },
    {
        "picker_value": "preliminary-report-percent",
        "data_col": "preliminary-report-percent",
        "source_column": "preliminary_report_percent",
        "label": "Предв. отчёт, проц.",
        "default_hidden": True,
    },
    {
        "picker_value": "preliminary-report-term",
        "data_col": "preliminary-report-term",
        "source_column": "preliminary_report_term",
        "label": "Предв. отчёт, срок дн.",
    },
    {
        "picker_value": "final-report-percent",
        "data_col": "final-report-percent",
        "source_column": "final_report_percent",
        "label": "Итог. отчёт, проц.",
        "default_hidden": True,
    },
    {
        "picker_value": "final-report-term",
        "data_col": "final-report-term",
        "source_column": "final_report_term",
        "label": "Итог. отчёт, срок дн.",
    },
]


def staff_required(user):
    return user.is_staff


def _has_contract_admin_role(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    employee = getattr(user, "employee_profile", None)
    employee_role = getattr(employee, "role", "")
    return (
        user.groups.filter(name=ADMIN_GROUP).exists()
        or employee_role == ADMIN_GROUP
    )


def contract_signing_manager_required(user):
    if _is_contract_lawyer(user) and not _has_contract_admin_role(user):
        return False
    return bool(getattr(user, "is_superuser", False) or _has_contract_admin_role(user))


def _user_has_role(user, group_name: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    employee = getattr(user, "employee_profile", None)
    employee_role = getattr(employee, "role", "")
    return user.groups.filter(name=group_name).exists() or employee_role == group_name


def _is_contract_expert(user) -> bool:
    return _user_has_role(user, EXPERT_GROUP)


def _is_contract_lawyer(user) -> bool:
    return _user_has_role(user, LAWYER_GROUP)


def _contract_return_author_role(user) -> str:
    if _is_contract_lawyer(user):
        return ContractReturnComment.AuthorRole.LAWYER
    if _is_contract_expert(user):
        return ContractReturnComment.AuthorRole.EXPERT
    return ContractReturnComment.AuthorRole.OTHER


def _user_can_access_contract_return(performer: Performer, user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _has_contract_admin_role(user) or _is_contract_lawyer(user):
        return True
    if not _is_contract_expert(user):
        return bool(getattr(user, "is_staff", False))
    employee = getattr(user, "employee_profile", None)
    if not employee:
        return False
    if performer.employee_id == employee.pk:
        return True
    employee_full_name = Performer.employee_full_name(employee)
    return bool(employee_full_name and performer.executor == employee_full_name)


def _contract_return_comment_filter(performer: Performer) -> Q:
    if performer.contract_batch_id:
        return Q(contract_batch_id=performer.contract_batch_id)
    return Q(performer=performer)


def _contract_return_counts(performer: Performer) -> dict:
    totals = ContractReturnComment.objects.filter(_contract_return_comment_filter(performer)).aggregate(
        lawyer_count=Count("id", filter=Q(author_role=ContractReturnComment.AuthorRole.LAWYER)),
        expert_count=Count("id", filter=Q(author_role=ContractReturnComment.AuthorRole.EXPERT)),
    )
    last_comment = (
        ContractReturnComment.objects
        .filter(_contract_return_comment_filter(performer))
        .order_by("-created_at", "-id")
        .first()
    )
    return {
        "lawyer_count": totals["lawyer_count"] or 0,
        "expert_count": totals["expert_count"] or 0,
        "last_role": last_comment.author_role if last_comment else "",
    }


def _attach_contract_return_comment_counts(contracts):
    contract_list = list(contracts)
    batch_ids = [p.contract_batch_id for p in contract_list if p.contract_batch_id]
    count_map = {}
    last_role_map = {}
    if batch_ids:
        for row in (
            ContractReturnComment.objects
            .filter(contract_batch_id__in=batch_ids)
            .values("contract_batch_id")
            .annotate(
                lawyer_count=Count("id", filter=Q(author_role=ContractReturnComment.AuthorRole.LAWYER)),
                expert_count=Count("id", filter=Q(author_role=ContractReturnComment.AuthorRole.EXPERT)),
            )
        ):
            count_map[row["contract_batch_id"]] = {
                "lawyer_count": row["lawyer_count"],
                "expert_count": row["expert_count"],
            }
        latest_ids = (
            ContractReturnComment.objects
            .filter(contract_batch_id__in=batch_ids)
            .values("contract_batch_id")
            .annotate(latest_id=Max("id"))
            .values_list("latest_id", flat=True)
        )
        for comment in ContractReturnComment.objects.filter(id__in=latest_ids):
            last_role_map[comment.contract_batch_id] = comment.author_role
    for performer in contract_list:
        counts = count_map.get(performer.contract_batch_id, {"lawyer_count": 0, "expert_count": 0})
        performer.return_lawyer_comment_count = counts["lawyer_count"]
        performer.return_expert_comment_count = counts["expert_count"]
        performer.return_last_comment_role = last_role_map.get(performer.contract_batch_id, "")


CONTRACTS_PARTIAL_TEMPLATE = "contracts_app/contracts_partial.html"
CONTRACTS_EXECUTION_PARTIAL_TEMPLATE = "contracts_app/execution_partial.html"
CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE = "contracts_app/contracts_development_partial.html"
CONTRACTS_PROJECT_REG_FORM_TEMPLATE = "contracts_app/contracts_project_registration_form.html"
CT_PARTIAL_TEMPLATE = "contracts_app/contract_templates_partial.html"
CT_FORM_TEMPLATE = "contracts_app/contract_template_form.html"
CT_HX_EVENT = "contract-templates-updated"


def _normalize_contract_person_name(value):
    return " ".join(str(value or "").split()).strip()


def _effective_contract_employee_ids(performers):
    performer_list = list(performers)

    executor_names_without_employee = {
        _normalize_contract_person_name(p.executor)
        for p in performer_list
        if not p.employee_id and _normalize_contract_person_name(p.executor)
    }
    employee_id_by_name = {}
    if executor_names_without_employee:
        for employee in Employee.objects.select_related("user", "person_record").all():
            full_name = _normalize_contract_person_name(Performer.employee_full_name(employee))
            if full_name in executor_names_without_employee and full_name not in employee_id_by_name:
                employee_id_by_name[full_name] = employee.pk

    performer_employee_ids = set()
    performer_effective_employee_id = {}
    for performer in performer_list:
        employee_id = performer.employee_id
        if not employee_id:
            employee_id = employee_id_by_name.get(_normalize_contract_person_name(performer.executor))
        performer_effective_employee_id[id(performer)] = employee_id
        if employee_id:
            performer_employee_ids.add(employee_id)
    return performer_effective_employee_id, performer_employee_ids


def _attach_contract_responsible_names(performers):
    performer_list = list(performers)
    if not performer_list:
        return performer_list

    performer_effective_employee_id, performer_employee_ids = _effective_contract_employee_ids(performer_list)

    profile_direction_by_employee = {}
    if performer_employee_ids:
        from experts_app.models import ExpertProfile

        profile_direction_by_employee = dict(
            ExpertProfile.objects
            .filter(
                employee_id__in=performer_employee_ids,
                expertise_direction_id__isnull=False,
            )
            .values_list("employee_id", "expertise_direction_id")
        )

    direction_head_by_department = {}
    direction_ids = set(profile_direction_by_employee.values())
    if direction_ids:
        heads = (
            Employee.objects
            .select_related("user")
            .filter(department_id__in=direction_ids, role=DEPARTMENT_HEAD_GROUP)
            .order_by("position", "id")
        )
        for head in heads:
            direction_head_by_department.setdefault(head.department_id, head)

    for performer in performer_list:
        employee_id = performer_effective_employee_id.get(id(performer))
        direction_id = profile_direction_by_employee.get(employee_id)
        if direction_id:
            head = direction_head_by_department.get(direction_id)
            performer.responsible_name = Performer.employee_full_name(head) if head else ""
        else:
            performer.responsible_name = getattr(performer.registration, "project_manager", "") or ""

    return performer_list


def _group_member_for_country(country):
    if not country:
        return None
    code = (getattr(country, "code", "") or "").strip()
    name = (getattr(country, "short_name", "") or "").strip()
    alpha2 = (getattr(country, "alpha2", "") or "").strip()
    filters = models.Q()
    if code:
        filters |= models.Q(country_code=code)
    if name:
        filters |= models.Q(country_name=name)
    if alpha2:
        filters |= models.Q(country_alpha2__iexact=alpha2)
    if not filters:
        return None
    return (
        GroupMember.objects
        .exclude(country_alpha2="")
        .filter(filters)
        .order_by("position", "id")
        .first()
    )


def _attach_contract_group_members(performers):
    performer_list = list(performers)
    if not performer_list:
        return performer_list

    performer_effective_employee_id, performer_employee_ids = _effective_contract_employee_ids(performer_list)
    employee_person_ids = {}
    if performer_employee_ids:
        employee_person_ids = dict(
            Employee.objects
            .filter(pk__in=performer_employee_ids, person_record_id__isnull=False)
            .values_list("pk", "person_record_id")
        )

    person_ids = set(employee_person_ids.values())
    country_by_person_id = {}
    if person_ids:
        citizenships = (
            CitizenshipRecord.objects
            .select_related("country")
            .filter(person_id__in=person_ids, is_active=True, country_id__isnull=False)
            .order_by("position", "id")
        )
        for citizenship in citizenships:
            country_by_person_id.setdefault(citizenship.person_id, citizenship.country)

    group_by_country_id = {}
    for country in country_by_person_id.values():
        if country and country.pk not in group_by_country_id:
            group_by_country_id[country.pk] = _group_member_for_country(country)

    for performer in performer_list:
        selected_group = getattr(performer, "contract_group_member", None)
        employee_id = performer_effective_employee_id.get(id(performer))
        person_id = employee_person_ids.get(employee_id)
        citizenship_country = country_by_person_id.get(person_id)
        default_group = group_by_country_id.get(getattr(citizenship_country, "pk", None))
        effective_group = selected_group or default_group
        performer.contract_group_member_default = default_group
        performer.contract_group_member_effective = effective_group
        performer.contract_group_display = (
            effective_group.group_code_label if effective_group else ""
        )

    return performer_list


def _contract_stage(project):
    return contract_stage_order(project)


def _contract_batch_type_display(performers):
    return contract_batch_type_display(performers)


def _contract_batch_deadline_display(performers):
    deadline = _contract_batch_deadline_date(performers)
    return deadline.strftime("%d.%m.%Y") if deadline else ""


def _contract_batch_deadline_date(performers):
    deadlines = [
        performer.registration.deadline
        for performer in performers
        if getattr(performer, "registration", None) and performer.registration.deadline
    ]
    if not deadlines:
        return None
    return max(deadlines)


def _contract_batch_deadline_iso(performers):
    deadline = _contract_batch_deadline_date(performers)
    return deadline.isoformat() if deadline else ""


def _contract_number_display(project):
    return contract_project_number_display(project)


def _contract_product_display(project):
    product_type = (getattr(project, "type_short_display", "") or "").strip()
    products = project.ordered_products() if project else []
    if products:
        product = products[0]
        short_name = (getattr(product, "short_name", "") or "").strip()
        display_name = (
            (getattr(product, "display_name", "") or "").strip()
            or (getattr(product, "name_ru", "") or "").strip()
            or (getattr(product, "name_en", "") or "").strip()
        )
        if short_name and display_name:
            return f"{short_name} {display_name}"
        return short_name or display_name or product_type
    return product_type


def _contract_batch_stage_rows(performers):
    items = []
    seen = set()
    for performer in performers:
        project = getattr(performer, "registration", None)
        if not project or project.pk in seen:
            continue
        seen.add(project.pk)
        items.append(
            {
                "sort_key": (_contract_stage(project), project.pk or 0),
                "stage": project.short_uid,
                "product": _contract_product_display(project),
            }
        )
    items.sort(key=lambda item: item["sort_key"])
    return [
        {"stage": item["stage"], "product": item["product"]}
        for item in items
    ]


def _contract_representative_key(performer):
    if performer.participation_batch_id:
        return (
            "participation_batch",
            performer.participation_batch_id,
            _normalize_contract_person_name(getattr(performer, "executor", "")),
            bool(getattr(performer, "contract_is_addendum", False)),
            getattr(performer, "contract_addendum_number", None) or 0,
        )
    if performer.contract_batch_id:
        return ("contract_batch", performer.contract_batch_id)
    return ("performer", performer.pk)


def _contract_representative_filter(performer):
    if performer.participation_batch_id:
        addendum_number = getattr(performer, "contract_addendum_number", None) or 0
        number_filter = Q(contract_addendum_number=addendum_number)
        if not addendum_number:
            number_filter |= Q(contract_addendum_number__isnull=True)
        return Q(
            participation_batch_id=performer.participation_batch_id,
            executor=_normalize_contract_person_name(getattr(performer, "executor", "")),
            contract_batch_id__isnull=False,
            contract_is_addendum=bool(getattr(performer, "contract_is_addendum", False)),
        ) & number_filter
    if performer.contract_batch_id:
        return Q(contract_batch_id=performer.contract_batch_id)
    return Q(pk=performer.pk)


def _contract_representative_rows(performers):
    representatives = []
    representatives_by_key = {}
    for performer in performers:
        key = _contract_representative_key(performer)
        representative = representatives_by_key.get(key)
        if representative is None:
            representatives_by_key[key] = performer
            representatives.append(performer)
            continue
        if (
            not (representative.contract_signing_note or "").strip()
            and (performer.contract_signing_note or "").strip()
        ):
            representative.contract_signing_note = performer.contract_signing_note
    return representatives


def _contract_conclusion_detail_sort_key(performer):
    project = getattr(performer, "registration", None)
    return (
        getattr(project, "number", 0) or 0,
        _contract_stage(project),
        getattr(project, "pk", 0) or 0,
        (getattr(performer, "asset_name", "") or "").casefold(),
        getattr(performer, "position", 0) or 0,
        getattr(performer, "pk", 0) or 0,
    )


def _contract_conclusion_order_key(performer, representative_order):
    representative_index = representative_order.get(_contract_representative_key(performer))
    detail_key = _contract_conclusion_detail_sort_key(performer)
    sent_order = 1 if getattr(performer, "contract_sent_at", None) else 0
    if representative_index is not None:
        return (sent_order, 0, representative_index, *detail_key)
    return (
        sent_order,
        1,
        (getattr(performer, "contract_number", "") or "").casefold(),
        (getattr(performer, "executor", "") or "").casefold(),
        1 if getattr(performer, "contract_is_addendum", False) else 0,
        getattr(performer, "contract_addendum_number", None) or 0,
        *detail_key,
    )


def _attach_contract_batch_display_fields(performers):
    performer_list = list(performers)
    contract_batch_ids = {performer.contract_batch_id for performer in performer_list if performer.contract_batch_id}
    participation_batch_ids = {
        performer.participation_batch_id
        for performer in performer_list
        if performer.participation_batch_id
    }
    batch_map = {}
    if contract_batch_ids:
        rows = (
            Performer.objects
            .select_related("registration", "registration__type")
            .filter(contract_batch_id__in=contract_batch_ids)
            .order_by("registration__agreement_sequence", "registration_id", "position", "id")
        )
        for performer in rows:
            batch_map.setdefault(("contract_batch", performer.contract_batch_id), []).append(performer)
    if participation_batch_ids:
        rows = (
            Performer.objects
            .select_related("registration", "registration__type")
            .filter(
                participation_batch_id__in=participation_batch_ids,
                participation_response=Performer.ParticipationResponse.CONFIRMED,
                employee__employment=FREELANCER_LABEL,
            )
            .order_by("registration__agreement_sequence", "registration_id", "position", "id")
        )
        for performer in rows:
            batch_map.setdefault(_contract_representative_key(performer), []).append(performer)

    for performer in performer_list:
        batch_performers = batch_map.get(_contract_representative_key(performer), [performer])
        stage_rows = _contract_batch_stage_rows(batch_performers)
        is_multi_stage = len(stage_rows) > 1
        first_project = getattr(performer, "registration", None)
        performer.contract_type_display = (
            _contract_batch_type_display(batch_performers)
            or getattr(getattr(performer, "registration", None), "type_short_display", "")
        )
        performer.contract_number_display = _contract_number_display(first_project)
        performer.contract_stage_display = "" if is_multi_stage else (first_project.short_uid if first_project else "")
        performer.contract_stage_rows = stage_rows
        deadline = _contract_batch_deadline_date(batch_performers)
        performer.contract_project_deadline_display = deadline.strftime("%d.%m.%Y") if deadline else ""
        performer.contract_project_deadline_iso = deadline.isoformat() if deadline else ""
        performer.contract_project_term_days = (
            (deadline - performer.contract_date).days
            if deadline and performer.contract_date
            else None
        )
    return performer_list


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
    contract_conclusion_performers_qs = (
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
        .annotate(
            executor_trim=Trim("executor"),
            contract_sent_order=models.Case(
                models.When(contract_sent_at__isnull=True, then=models.Value(0)),
                default=models.Value(1),
                output_field=models.IntegerField(),
            ),
        )
        .filter(
            registration__status__in=active_participation_statuses,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            employee__employment=FREELANCER_LABEL,
        )
        .exclude(executor_trim="")
        .order_by(
            "contract_sent_order",
            "contract_number",
            "executor",
            "contract_is_addendum",
            "contract_addendum_number",
            "contract_batch_id",
            "participation_batch_id",
            "registration__number",
            "registration__agreement_sequence",
            "registration_id",
            "asset_name",
            "position",
            "id",
        )
    )
    contract_conclusion_project_ids = (
        contract_conclusion_performers_qs
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
            "employee", "employee__user", "employee__person_record",
            "currency", "contract_group_member",
        )
        .filter(contract_batch_id__isnull=False)
        .order_by("contract_batch_id", "position", "id")
    )

    is_admin_role = False
    is_expert = False
    is_lawyer = False
    has_active_smtp_connection = False
    if user and getattr(user, "is_authenticated", False):
        from policy_app.models import EXPERT_GROUP, LAWYER_GROUP
        employee = getattr(user, "employee_profile", None)
        employee_role = getattr(employee, "role", "")
        is_expert = user.groups.filter(name=EXPERT_GROUP).exists() or employee_role == EXPERT_GROUP
        is_lawyer = user.groups.filter(name=LAWYER_GROUP).exists() or employee_role == LAWYER_GROUP
        is_admin_role = _has_contract_admin_role(user)
        has_active_smtp_connection = ExternalSMTPAccount.objects.filter(
            user=user,
            is_active=True,
            use_for_notifications=True,
        ).exists()
        if is_expert:
            if employee:
                expert_filter = Q(employee_id=employee.pk)
                employee_full_name = Performer.employee_full_name(employee)
                if employee_full_name:
                    expert_filter |= Q(executor=employee_full_name)
                all_performers = all_performers.filter(expert_filter)
            else:
                all_performers = all_performers.none()

    all_performers = list(all_performers)
    contracts = _contract_representative_rows(all_performers)
    contract_representative_order = {
        _contract_representative_key(performer): index
        for index, performer in enumerate(contracts)
    }

    price_map = {}
    for performer in all_performers:
        if performer.agreed_amount is None:
            continue
        key = _contract_representative_key(performer)
        price_map[key] = (price_map.get(key) or 0) + performer.agreed_amount
    for p in contracts:
        p.total_price = price_map.get(_contract_representative_key(p))
    _attach_contract_batch_display_fields(contracts)
    _attach_contract_group_members(contracts)
    _attach_contract_responsible_names(contracts)
    _attach_contract_return_comment_counts(contracts)
    has_contracts_sent_for_signing = any(p.contract_sent_at for p in contracts)

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

    contract_drafting_performers = _attach_contract_batch_display_fields(list(contract_conclusion_performers_qs))
    contract_drafting_performers.sort(
        key=lambda performer: _contract_conclusion_order_key(performer, contract_representative_order)
    )
    contract_dispatch_performers = _contract_representative_rows(contract_drafting_performers)
    contract_dispatch_performers = _attach_contract_batch_display_fields(contract_dispatch_performers)
    contract_dispatch_performers.sort(
        key=lambda performer: _contract_conclusion_order_key(performer, contract_representative_order)
    )
    _attach_contract_folder_urls([*contract_drafting_performers, *contract_dispatch_performers, *contracts], user)

    return {
        "contracts": contracts,
        "contract_projects": contract_projects,
        "contract_drafting_performers": contract_drafting_performers,
        "contract_dispatch_performers": contract_dispatch_performers,
        "contract_conclusion_projects": contract_conclusion_projects,
        "contract_request_sent_initial": contract_request_sent_initial,
        "batch_badge_map": batch_badge_map,
        "lawyer_badge_map": lawyer_badge_map,
        "can_sign_performer_contracts": is_admin_role or is_expert,
        "can_manage_contract_signing_actions": contract_signing_manager_required(user),
        "has_contracts_sent_for_signing": has_contracts_sent_for_signing,
        "is_expert": is_expert,
        "is_lawyer": is_lawyer,
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "has_active_smtp_connection": has_active_smtp_connection,
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


def _build_contract_file_redirect_url(client, file_id: str) -> str:
    clean_file_id = str(file_id or "").strip()
    base_url = str(getattr(client, "base_url", "") or "").strip().rstrip("/")
    if not clean_file_id or not base_url:
        return ""
    return f"{base_url}/f/{quote(clean_file_id, safe='')}"


def _attach_contract_folder_urls(contracts, user=None):
    nextcloud_primary = is_nextcloud_primary()
    folder_source_by_key = {}
    for performer in contracts:
        path = getattr(performer, "contract_project_disk_folder", "") or ""
        if not path:
            continue
        key = (
            getattr(performer, "registration_id", None),
            _normalize_contract_person_name(getattr(performer, "executor", "")),
        )
        folder_source_by_key.setdefault(key, performer)

    folder_cache = {}
    for performer in contracts:
        path = getattr(performer, "contract_project_disk_folder", "") or ""
        if not path:
            key = (
                getattr(performer, "registration_id", None),
                _normalize_contract_person_name(getattr(performer, "executor", "")),
            )
            source = folder_source_by_key.get(key)
            if source:
                performer.contract_project_disk_folder = getattr(source, "contract_project_disk_folder", "") or ""
                performer.contract_project_folder_link = getattr(source, "contract_project_folder_link", "") or ""
                performer.contract_project_folder_file_id = getattr(source, "contract_project_folder_file_id", "") or ""
        path = getattr(performer, "contract_project_disk_folder", "") or ""
        public_url = (getattr(performer, "contract_project_folder_link", "") or "").strip()
        performer.contract_project_folder_url = public_url or build_folder_url(path)
        performer.contract_project_docx_file_url = "" if nextcloud_primary else (
            getattr(performer, "contract_project_link", "") or ""
        ).strip()
        performer.contract_project_pdf_file_url = (
            getattr(performer, "contract_pdf_link", "") or ""
        ).strip()
        performer.contract_signed_pdf_file_url = (
            getattr(performer, "contract_signed_pdf_link", "") or ""
        ).strip()
        if path:
            folder_cache.setdefault(path, performer.contract_project_folder_url)

    if not contracts or not nextcloud_primary:
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
            if editor_url:
                performer.contract_project_docx_file_url = editor_url


def _contract_schedule_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _contract_schedule_month_end_day(year, month):
    if month == 12:
        next_month = dt_date(year + 1, 1, 1)
    else:
        next_month = dt_date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _add_contract_schedule_months(value, months):
    months = _contract_schedule_decimal(months)
    if not value or months is None:
        return value
    whole_months = int(months)
    fractional = months - Decimal(whole_months)
    year = value.year + ((value.month - 1 + whole_months) // 12)
    month = ((value.month - 1 + whole_months) % 12) + 1
    day = min(value.day, _contract_schedule_month_end_day(year, month))
    shifted = dt_date(year, month, day)
    if fractional:
        shifted += timedelta(days=int((fractional * Decimal("30")) + Decimal("0.5")))
    return shifted


def _subtract_contract_schedule_months(value, months):
    months = _contract_schedule_decimal(months)
    if not value or months is None:
        return value
    whole_months = int(months)
    fractional = months - Decimal(whole_months)
    if fractional:
        value = value - timedelta(days=int((fractional * Decimal("30")) + Decimal("0.5")))
    total_month = value.month - 1 - whole_months
    year = value.year + (total_month // 12)
    month = (total_month % 12) + 1
    day = min(value.day, _contract_schedule_month_end_day(year, month))
    return dt_date(year, month, day)


def _add_contract_schedule_weeks(value, weeks):
    weeks = _contract_schedule_decimal(weeks)
    if not value or weeks is None:
        return value
    safe_weeks = max(weeks, Decimal("0"))
    return value + timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _subtract_contract_schedule_weeks(value, weeks):
    weeks = _contract_schedule_decimal(weeks)
    if not value or weeks is None:
        return value
    safe_weeks = max(weeks, Decimal("0"))
    return value - timedelta(days=int((safe_weeks * Decimal("7")) + Decimal("0.5")))


def _contract_schedule_preliminary_term_unit(value):
    raw = str(value or "").strip()
    valid_units = {choice[0] for choice in ContractProjectRegistration.PreliminaryReportTermUnit.choices}
    if raw in valid_units:
        return raw
    return ContractProjectRegistration.PreliminaryReportTermUnit.MONTHS.value


def _add_contract_schedule_preliminary_term(value, term, unit):
    term = _contract_schedule_decimal(term)
    if not value or term is None:
        return value
    unit = _contract_schedule_preliminary_term_unit(unit)
    if unit == ContractProjectRegistration.PreliminaryReportTermUnit.DAYS:
        return value + timedelta(days=int(max(term, Decimal("0")) + Decimal("0.5")))
    if unit == ContractProjectRegistration.PreliminaryReportTermUnit.WEEKS:
        return _add_contract_schedule_weeks(value, term)
    return _add_contract_schedule_months(value, term)


def _subtract_contract_schedule_preliminary_term(value, term, unit):
    term = _contract_schedule_decimal(term)
    if not value or term is None:
        return value
    unit = _contract_schedule_preliminary_term_unit(unit)
    if unit == ContractProjectRegistration.PreliminaryReportTermUnit.DAYS:
        return value - timedelta(days=int(max(term, Decimal("0")) + Decimal("0.5")))
    if unit == ContractProjectRegistration.PreliminaryReportTermUnit.WEEKS:
        return _subtract_contract_schedule_weeks(value, term)
    return _subtract_contract_schedule_months(value, term)


def _contract_schedule_preliminary_term_display(value, unit):
    value = _contract_schedule_decimal(value)
    if value is None:
        return ""
    unit = _contract_schedule_preliminary_term_unit(unit)
    labels = dict(ContractProjectRegistration.PreliminaryReportTermUnit.choices)
    if unit == ContractProjectRegistration.PreliminaryReportTermUnit.DAYS:
        display_value = str(int(max(value, Decimal("0")) + Decimal("0.5")))
    else:
        display_value = f"{value:.1f}".replace(".", ",")
    return f"{display_value} {labels.get(unit, 'мес.')}"


def _contract_schedule_final_term_unit(value):
    raw = str(value or "").strip()
    valid_units = {choice[0] for choice in ContractProjectRegistration.FinalReportTermUnit.choices}
    if raw in valid_units:
        return raw
    return ContractProjectRegistration.FinalReportTermUnit.WEEKS.value


def _add_contract_schedule_final_term(value, term, unit):
    term = _contract_schedule_decimal(term)
    if not value or term is None:
        return value
    unit = _contract_schedule_final_term_unit(unit)
    if unit == ContractProjectRegistration.FinalReportTermUnit.DAYS:
        return value + timedelta(days=int(max(term, Decimal("0")) + Decimal("0.5")))
    if unit == ContractProjectRegistration.FinalReportTermUnit.MONTHS:
        return _add_contract_schedule_months(value, term)
    return _add_contract_schedule_weeks(value, term)


def _contract_schedule_final_term_display(value, unit):
    value = _contract_schedule_decimal(value)
    if value is None:
        return ""
    unit = _contract_schedule_final_term_unit(unit)
    labels = dict(ContractProjectRegistration.FinalReportTermUnit.choices)
    if unit == ContractProjectRegistration.FinalReportTermUnit.DAYS:
        display_value = str(int(max(value, Decimal("0")) + Decimal("0.5")))
    else:
        display_value = f"{value:.1f}".replace(".", ",")
    return f"{display_value} {labels.get(unit, 'нед.')}"


def _contract_schedule_base_start_date(today=None):
    current = (today or timezone.localdate()) + timedelta(days=14)
    previous_monday = current - timedelta(days=current.weekday())
    next_monday = previous_monday + timedelta(days=7)
    if abs((current - previous_monday).days) <= abs((next_monday - current).days):
        return previous_monday
    return next_monday


def _parse_contract_schedule_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, dt_date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _contract_registration_tkp_key(registration):
    if registration.proposal_registration_id and registration.proposal_registration:
        return registration.proposal_registration.short_uid
    return ""


def _annotate_contract_registration_number_groups(registrations):
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
            if offset < group_size:
                next_registration = items[start + offset]
                registration.has_next_for_different_contract_in_number_group = (
                    next_registration.short_uid != registration.short_uid
                )
                registration.has_next_for_different_tkp_in_number_group = (
                    _contract_registration_tkp_key(next_registration)
                    != _contract_registration_tkp_key(registration)
                )
            else:
                registration.has_next_for_different_contract_in_number_group = False
                registration.has_next_for_different_tkp_in_number_group = False
        start = end
    for index, registration in enumerate(items):
        previous = items[index - 1] if index > 0 else None
        registration.is_first_for_tkp = (
            previous is None
            or previous.number != registration.number
            or _contract_registration_tkp_key(previous) != _contract_registration_tkp_key(registration)
        )
    return items


def _annotate_contract_payment_schedule_number_groups(rows):
    items = list(rows)
    start = 0
    while start < len(items):
        current_number = items[start]["number"]
        end = start + 1
        while end < len(items) and items[end]["number"] == current_number:
            end += 1
        group_size = end - start
        for offset, row in enumerate(items[start:end], start=1):
            row["is_first_for_number"] = offset == 1
            row["is_number_continuation"] = offset > 1
            row["has_next_for_number"] = offset < group_size
            if offset < group_size:
                next_row = items[start + offset]
                row["has_next_for_different_tkp_in_number_group"] = (
                    (next_row.get("tkp_id") or "") != (row.get("tkp_id") or "")
                )
            else:
                row["has_next_for_different_tkp_in_number_group"] = False
        start = end
    for index, row in enumerate(items):
        previous = items[index - 1] if index > 0 else None
        row["is_first_for_tkp"] = (
            previous is None
            or previous["number"] != row["number"]
            or (previous.get("tkp_id") or "") != (row.get("tkp_id") or "")
        )
    return items


def _build_contract_payment_schedule_rows(registrations):
    rows = []
    for registration in registrations:
        products = list(registration.ordered_products()) if getattr(registration, "pk", None) else []
        if not products:
            products = [None]
        stored_stages = list(getattr(registration, "stage_payloads_json", None) or [])
        rolling_start_date = _contract_schedule_base_start_date()
        product_count = len(products)
        for index, product in enumerate(products, start=1):
            stage_payload = {}
            if stored_stages:
                if index - 1 < len(stored_stages) and isinstance(stored_stages[index - 1], dict):
                    stage_payload = stored_stages[index - 1]
                else:
                    stage_payload = next(
                        (
                            item for item in stored_stages
                            if str(item.get("product_id") or "") == str(getattr(product, "pk", "") or "")
                        ),
                        {},
                    )

            service_term_months = _contract_schedule_decimal(
                stage_payload.get("service_term_months")
                if stage_payload.get("service_term_months") not in (None, "")
                else registration.service_term_months
            )
            preliminary_report_term_unit = _contract_schedule_preliminary_term_unit(
                stage_payload.get("preliminary_report_term_unit")
                or getattr(registration, "preliminary_report_term_unit", "")
            )
            final_report_term_weeks = _contract_schedule_decimal(
                stage_payload.get("final_report_term_weeks")
                if stage_payload.get("final_report_term_weeks") not in (None, "")
                else registration.final_report_term_weeks
            )
            final_report_term_unit = _contract_schedule_final_term_unit(
                stage_payload.get("final_report_term_unit")
                or getattr(registration, "final_report_term_unit", "")
            )
            preliminary_report_date = _parse_contract_schedule_date(stage_payload.get("preliminary_report_date"))
            if preliminary_report_date is None:
                preliminary_report_date = registration.preliminary_report_date
            final_report_date = _parse_contract_schedule_date(stage_payload.get("final_report_date"))
            if final_report_date is None:
                final_report_date = registration.final_report_date
            evaluation_date = _parse_contract_schedule_date(stage_payload.get("evaluation_date"))
            if evaluation_date is None:
                evaluation_date = registration.evaluation_date

            if preliminary_report_date and service_term_months is not None:
                start_date = _subtract_contract_schedule_preliminary_term(
                    preliminary_report_date,
                    service_term_months,
                    preliminary_report_term_unit,
                )
            else:
                start_date = rolling_start_date
            if not preliminary_report_date and service_term_months is not None:
                preliminary_report_date = _add_contract_schedule_preliminary_term(
                    start_date,
                    service_term_months,
                    preliminary_report_term_unit,
                )
            if not final_report_date and preliminary_report_date and final_report_term_weeks is not None:
                final_report_date = _add_contract_schedule_final_term(
                    preliminary_report_date,
                    final_report_term_weeks,
                    final_report_term_unit,
                )
            stage_end_date = final_report_date or preliminary_report_date or start_date
            next_delay_days = stage_payload.get("next_stage_delay_days")
            if next_delay_days not in (None, ""):
                try:
                    rolling_start_date = stage_end_date + timedelta(days=int(next_delay_days))
                except (TypeError, ValueError):
                    rolling_start_date = stage_end_date
            else:
                rolling_start_date = stage_end_date

            rows.append(
                {
                    "registration_id": registration.pk,
                    "is_first_for_registration": index == 1,
                    "is_continuation": index > 1,
                    "has_next_for_registration": index < product_count,
                    "number": registration.formatted_number,
                    "tkp_id": (
                        registration.proposal_registration.short_uid
                        if registration.proposal_registration_id and registration.proposal_registration
                        else ""
                    ),
                    "agreement_type": registration.get_agreement_type_display(),
                    "sub_number": registration.sub_number,
                    "contract_number": registration.contract_number,
                    "group": registration.group_display,
                    "project_id": registration.short_uid,
                    "type": (getattr(product, "short_name", "") or str(product or "")).strip(),
                    "name": registration.name,
                    "stage": f"Этап {index}",
                    "evaluation_date": evaluation_date,
                    "start_date": start_date,
                    "service_term_months": service_term_months,
                    "preliminary_report_term_unit": preliminary_report_term_unit,
                    "preliminary_report_term_display": _contract_schedule_preliminary_term_display(
                        service_term_months,
                        preliminary_report_term_unit,
                    ),
                    "preliminary_report_date": preliminary_report_date,
                    "final_report_term_weeks": final_report_term_weeks,
                    "final_report_term_unit": final_report_term_unit,
                    "final_report_term_display": _contract_schedule_final_term_display(
                        final_report_term_weeks,
                        final_report_term_unit,
                    ),
                    "final_report_date": final_report_date,
                    "advance_percent": _contract_schedule_decimal(
                        stage_payload.get("advance_percent")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.advance_percent
                    ),
                    "advance_term_days": (
                        stage_payload.get("advance_term_days")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.advance_term_days
                    ),
                    "preliminary_report_percent": _contract_schedule_decimal(
                        stage_payload.get("preliminary_report_percent")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.preliminary_report_percent
                    ),
                    "preliminary_report_term_days": (
                        stage_payload.get("preliminary_report_term_days")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.preliminary_report_term_days
                    ),
                    "final_report_percent": _contract_schedule_decimal(
                        stage_payload.get("final_report_percent")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.final_report_percent
                    ),
                    "final_report_term_days": (
                        stage_payload.get("final_report_term_days")
                        if stage_payload.get("payment_schedule_common") is False
                        else registration.final_report_term_days
                    ),
                    "edit_url": reverse("contracts_project_registration_edit", args=[registration.pk]),
                }
            )
    return rows


def _contracts_development_context():
    product_prefetch = models.Prefetch(
        "product_links",
        queryset=ContractProjectRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
    )
    registrations = _annotate_contract_registration_number_groups(
        ContractProjectRegistration.objects
        .select_related("country", "asset_owner_country", "group_member", "type", "proposal_registration")
        .prefetch_related(product_prefetch)
        .all()
    )
    contract_project_order_ids = [registration.pk for registration in registrations]
    return {
        "registrations": registrations,
        "contract_payment_schedule_rows": _annotate_contract_payment_schedule_number_groups(
            _build_contract_payment_schedule_rows(registrations)
        ),
        "contract_payment_schedule_ui_columns": CONTRACT_PAYMENT_SCHEDULE_UI_COLUMNS,
        "contract_payment_schedule_empty_colspan": len(CONTRACT_PAYMENT_SCHEDULE_UI_COLUMNS) + 1,
        "contract_project_order_signature": _contract_project_order_signature(contract_project_order_ids),
    }


def _render_contracts_development_updated(request):
    resp = render(request, CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE, _contracts_development_context())
    resp["HX-Trigger"] = "contracts-updated"
    return resp


def _render_contracts_project_registration_form(request, form, *, action, registration=None):
    from projects_app.views import _registration_form_context
    from proposals_app.views import _proposal_product_autofill_data

    context = _registration_form_context(form, action, registration)
    context.update(_proposal_product_autofill_data())
    prefill_ranked_products = getattr(form, "prefill_ranked_products", None)
    if prefill_ranked_products is not None:
        context["ranked_products"] = prefill_ranked_products
    return render(
        request,
        CONTRACTS_PROJECT_REG_FORM_TEMPLATE,
        context,
    )


def _normalize_contract_development_positions():
    items = ContractProjectRegistration.objects.order_by("position", "id").only("id", "position")
    for idx, item in enumerate(items, start=1):
        if item.position != idx:
            ContractProjectRegistration.objects.filter(pk=item.pk).update(position=idx)


def _contract_project_order_signature(contract_project_ids):
    return ":".join(str(contract_project_id) for contract_project_id in contract_project_ids)


def _save_ranked_contract_project_products(registration, product_ids):
    normalized_ids = []
    for raw_id in product_ids:
        try:
            product_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        normalized_ids.append(product_id)

    ContractProjectRegistrationProduct.objects.filter(registration=registration).delete()
    if normalized_ids:
        ContractProjectRegistrationProduct.objects.bulk_create(
            [
                ContractProjectRegistrationProduct(
                    registration=registration,
                    product_id=product_id,
                    rank=rank,
                )
                for rank, product_id in enumerate(normalized_ids, start=1)
            ]
        )
    _sync_contract_project_registration_primary_product(registration.pk)


@login_required
@require_http_methods(["GET"])
def contracts_partial(request):
    return render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))


@login_required
@require_http_methods(["GET"])
def contracts_execution_partial(request):
    from projects_app.views import _payment_request_context

    return render(
        request,
        CONTRACTS_EXECUTION_PARTIAL_TEMPLATE,
        _payment_request_context(request.user),
    )


@login_required
@require_http_methods(["GET"])
def contracts_development_partial(request):
    return render(request, CONTRACTS_DEVELOPMENT_PARTIAL_TEMPLATE, _contracts_development_context())


@login_required
@user_passes_test(staff_required)
@require_POST
def contracts_project_registration_row_order(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Некорректный формат порядка проектов договоров."}, status=400)

    raw_ids = payload.get("ordered_contract_project_ids") or []
    try:
        ordered_contract_project_ids = [int(value) for value in raw_ids]
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "Порядок проектов договоров содержит некорректные идентификаторы."},
            status=400,
        )
    if len(ordered_contract_project_ids) != len(set(ordered_contract_project_ids)):
        return JsonResponse({"ok": False, "error": "Порядок проектов договоров содержит дубли."}, status=400)

    base_signature = str(payload.get("base_order_signature") or "")
    with transaction.atomic():
        current_items = list(
            ContractProjectRegistration.objects.select_for_update().order_by("position", "id").only("id", "position")
        )
        current_contract_project_ids = [item.pk for item in current_items]
        current_signature = _contract_project_order_signature(current_contract_project_ids)
        desired_signature = _contract_project_order_signature(ordered_contract_project_ids)

        conflict_payload = {
            "ok": False,
            "error": "Порядок проектов договоров был изменен. Таблица будет обновлена.",
            "current_contract_project_ids": current_contract_project_ids,
            "order_signature": current_signature,
        }
        if base_signature and base_signature != current_signature:
            if ordered_contract_project_ids == current_contract_project_ids:
                return JsonResponse({"ok": True, "order_signature": current_signature})
            return JsonResponse(conflict_payload, status=409)
        if set(ordered_contract_project_ids) != set(current_contract_project_ids):
            return JsonResponse(conflict_payload, status=409)

        for idx, contract_project_id in enumerate(ordered_contract_project_ids, start=1):
            ContractProjectRegistration.objects.filter(pk=contract_project_id).update(position=idx)
    return JsonResponse({"ok": True, "order_signature": desired_signature})


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def contracts_project_registration_prefill_from_proposal(request, proposal_pk):
    proposal = get_object_or_404(
        ProposalRegistration.objects
        .select_related("group_member", "type", "country", "asset_owner_country")
        .prefetch_related(
            models.Prefetch(
                "product_links",
                queryset=ProposalRegistrationProduct.objects.select_related("product").order_by("rank", "id"),
            )
        ),
        pk=proposal_pk,
    )
    registration = None
    raw_registration_pk = request.GET.get("registration")
    if raw_registration_pk:
        registration = get_object_or_404(ContractProjectRegistration, pk=raw_registration_pk)
    form = build_contract_project_form_from_proposal(proposal, registration=registration)
    return _render_contracts_project_registration_form(
        request,
        form,
        action="edit" if registration else "create",
        registration=registration,
    )


@login_required
@user_passes_test(staff_required)
@require_POST
def contracts_project_registration_status_update(request, pk: int):
    status_value = (request.POST.get("status") or "").strip()
    valid_statuses = {value for value, _label in ContractProjectRegistration.STATUS_CHOICES}
    if status_value not in valid_statuses:
        return JsonResponse({"ok": False, "error": "Некорректный статус договора."}, status=400)

    registration = get_object_or_404(
        ContractProjectRegistration.objects.only("id", "status"),
        pk=pk,
    )
    if registration.status != status_value:
        registration.status = status_value
        registration.save(update_fields=["status"])

    return JsonResponse({"ok": True, "status": registration.status})


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
        return _render_contracts_project_registration_form(request, form, action="create")

    from projects_app.views import (
        _next_position,
        _sync_selection_kwargs,
        _sync_to_legal_entity_record,
    )

    obj = form.save(commit=False)
    if not getattr(obj, "position", 0):
        obj.position = _next_position(ContractProjectRegistration)
    obj.save()
    _save_ranked_contract_project_products(obj, getattr(form, "cleaned_type_ids", []))
    _sync_to_legal_entity_record(
        obj.customer,
        obj.country,
        obj.identifier,
        obj.registration_number,
        obj.registration_date,
        request.user,
        business_entity_source="[Договоры / Проекты договоров / Заказчик]",
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contracts_project_registration_edit(request, pk):
    registration = get_object_or_404(ContractProjectRegistration, pk=pk)
    if request.method == "GET":
        return _render_contracts_project_registration_form(
            request,
            ContractProjectRegistrationForm(instance=registration),
            action="edit",
            registration=registration,
        )

    form = ContractProjectRegistrationForm(request.POST, instance=registration)
    if not form.is_valid():
        return _render_contracts_project_registration_form(
            request, form, action="edit", registration=registration,
        )

    from projects_app.views import (
        _sync_selection_kwargs,
        _sync_to_legal_entity_record,
    )

    obj = form.save()
    _save_ranked_contract_project_products(obj, getattr(form, "cleaned_type_ids", []))
    _sync_to_legal_entity_record(
        obj.customer,
        obj.country,
        obj.identifier,
        obj.registration_number,
        obj.registration_date,
        request.user,
        business_entity_source="[Договоры / Проекты договоров / Заказчик]",
        **_sync_selection_kwargs(request, "customer_autocomplete"),
    )
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def contracts_project_registration_delete(request, pk):
    registration = get_object_or_404(ContractProjectRegistration, pk=pk)
    registration.delete()
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def contracts_project_registration_move_up(request, pk):
    _normalize_contract_development_positions()
    items = list(ContractProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx > 0:
        current, previous = items[idx], items[idx - 1]
        ContractProjectRegistration.objects.filter(pk=current.id).update(position=previous.position)
        ContractProjectRegistration.objects.filter(pk=previous.id).update(position=current.position)
        _normalize_contract_development_positions()
    return _render_contracts_development_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["POST", "GET"])
def contracts_project_registration_move_down(request, pk):
    _normalize_contract_development_positions()
    items = list(ContractProjectRegistration.objects.order_by("position", "id").only("id", "position"))
    idx = next((i for i, item in enumerate(items) if item.id == pk), None)
    if idx is not None and idx < len(items) - 1:
        current, nxt = items[idx], items[idx + 1]
        ContractProjectRegistration.objects.filter(pk=current.id).update(position=nxt.position)
        ContractProjectRegistration.objects.filter(pk=nxt.id).update(position=current.position)
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
@user_passes_test(contract_signing_manager_required)
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
@user_passes_test(contract_signing_manager_required)
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
@user_passes_test(contract_signing_manager_required)
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
@require_http_methods(["GET"])
def contract_return_comment_modal(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related("registration", "employee", "employee__user"),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    if not _user_can_access_contract_return(performer, request.user):
        return HttpResponse("Недостаточно прав для просмотра комментариев.", status=403)

    comments = (
        ContractReturnComment.objects
        .filter(_contract_return_comment_filter(performer))
        .select_related("author")
        .order_by("created_at", "id")
    )
    counts = _contract_return_counts(performer)
    return render(
        request,
        "contracts_app/components/return_comment_modal.html",
        {
            "performer": performer,
            "comments": comments,
            "lawyer_count": counts["lawyer_count"],
            "expert_count": counts["expert_count"],
            "add_comment_url": "contracts_return_comment_add",
            "return_url": "contracts_return_performer_contract",
            "can_return_contract": _is_contract_expert(request.user),
        },
    )


@login_required
@require_POST
def contract_return_comment_add(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related("registration", "employee", "employee__user"),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    if not _user_can_access_contract_return(performer, request.user):
        return HttpResponse("Недостаточно прав для добавления комментария.", status=403)

    value = (request.POST.get("value") or "").strip()
    if not value:
        return HttpResponseBadRequest("Введите текст комментария.")

    ContractReturnComment.objects.create(
        performer=performer,
        contract_batch_id=performer.contract_batch_id,
        text=value,
        author=request.user,
        author_role=_contract_return_author_role(request.user),
    )
    comments = (
        ContractReturnComment.objects
        .filter(_contract_return_comment_filter(performer))
        .select_related("author")
        .order_by("created_at", "id")
    )
    counts = _contract_return_counts(performer)
    history_html = render_to_string(
        "contracts_app/components/return_comment_thread.html",
        {
            "performer": performer,
            "comments": comments,
            "oob": True,
        },
        request=request,
    )
    resp = HttpResponse(history_html)
    resp["HX-Trigger"] = json.dumps({
        "contracts:return-comment-updated": {
            "performerId": performer.pk,
            "lawyerCount": counts["lawyer_count"],
            "expertCount": counts["expert_count"],
            "lastRole": counts["last_role"],
        }
    })
    return resp


@login_required
@require_POST
def contract_return_performer_contract(request, pk):
    from notifications_app.services import complete_contract_notifications_for_performers

    performer = get_object_or_404(
        Performer.objects.select_related("registration", "employee", "employee__user"),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    if not _is_contract_expert(request.user) or not _user_can_access_contract_return(performer, request.user):
        return JsonResponse({"ok": False, "error": "Вернуть договор может только Эксперт."}, status=403)
    if performer.contract_signing_date:
        return JsonResponse({"ok": False, "error": "Договор уже подписан факсимиле."}, status=400)
    if performer.contract_send_date:
        return JsonResponse({"ok": False, "error": "Скан договора уже отправлен."}, status=400)
    if not performer.contract_sent_at:
        return JsonResponse({"ok": False, "error": "Договор уже возвращён на составление проекта."}, status=400)

    with transaction.atomic():
        locked = Performer.objects.select_for_update().get(pk=performer.pk)
        if locked.contract_batch_id:
            batch_filter = Q(contract_batch_id=locked.contract_batch_id)
        else:
            batch_filter = Q(pk=locked.pk)
        returned_ids = list(Performer.objects.filter(batch_filter).values_list("pk", flat=True))
        updated = Performer.objects.filter(batch_filter).update(
            contract_sent_at=None,
            contract_deadline_at=None,
            contract_signing_note="Разрабатывается проект договора",
            contract_conclusion_status="",
        )
        completed_notifications = complete_contract_notifications_for_performers(
            performer_ids=returned_ids,
            actor=request.user,
        )

    return JsonResponse(
        {
            "ok": True,
            "updated": updated,
            "completed_notifications": completed_notifications,
            "status": "Разрабатывается проект договора",
        }
    )


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_form_edit(request, pk):
    performer = get_object_or_404(
        Performer.objects.select_related(
            "registration", "registration__type", "currency",
            "employee", "employee__user", "employee__person_record",
            "contract_group_member",
        ),
        pk=pk,
        contract_batch_id__isnull=False,
    )
    _attach_contract_batch_display_fields([performer])
    _attach_contract_group_members([performer])
    if request.method == "POST":
        form = ContractEditForm(request.POST, instance=performer)
        if form.is_valid():
            obj = form.save()
            group_filter = _contract_representative_filter(obj)
            if obj.contract_batch_id or obj.participation_batch_id:
                Performer.objects.filter(group_filter).exclude(pk=obj.pk).update(
                    contract_group_member_id=obj.contract_group_member_id,
                    contract_number=obj.contract_number,
                    contract_date=obj.contract_date,
                    prepayment=obj.prepayment,
                    final_payment=obj.final_payment,
                    contract_file=obj.contract_file,
                )
            resp = render(request, CONTRACTS_PARTIAL_TEMPLATE, _contracts_context(request.user))
            resp["HX-Trigger"] = "contracts-updated"
            return resp
    else:
        form = ContractEditForm(
            instance=performer,
            group_member_initial=getattr(performer, "contract_group_member_default", None),
        )

    total_price = (
        Performer.objects
        .filter(_contract_representative_filter(performer), agreed_amount__isnull=False)
        .aggregate(total=Sum("agreed_amount"))
        .get("total")
    )
    performer.total_price = total_price
    _attach_contract_batch_display_fields([performer])
    _attach_contract_group_members([performer])
    _attach_contract_responsible_names([performer])

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
@user_passes_test(contract_signing_manager_required)
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
