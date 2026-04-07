import json
import logging
import os
from datetime import date as dt_date, datetime
from decimal import Decimal
from urllib.parse import quote

from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Max, Prefetch
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from classifiers_app.models import LegalEntityRecord
from core.cloud_storage import build_folder_url, get_primary_cloud_storage_label, is_nextcloud_primary
from experts_app.models import ExpertProfile, ExpertProfileSpecialty
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.workspace import build_proposal_workspace_path, create_proposal_workspace
from policy_app.models import (
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalSectionSpecialty,
    TypicalServiceComposition,
)
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
from .document_generation import get_generated_docx_path, store_generated_documents
from .models import ProposalRegistration, ProposalTemplate, ProposalVariable
from .services import normalize_proposal_delivery_channels, send_proposal_dispatch_emails
from .variable_resolver import resolve_variables

PROPOSALS_PARTIAL_TEMPLATE = "proposals_app/proposals_partial.html"
PROPOSAL_FORM_TEMPLATE = "proposals_app/proposal_form_page.html"
PROPOSAL_DISPATCH_FORM_TEMPLATE = "proposals_app/proposal_dispatch_form.html"
PROPOSAL_TEMPLATE_FORM_TEMPLATE = "proposals_app/proposal_template_form.html"
PROPOSAL_VARIABLE_FORM_TEMPLATE = "proposals_app/proposal_variable_form.html"

HX_TRIGGER_HEADER = "HX-Trigger"
HX_PROPOSALS_UPDATED_EVENT = "proposals-updated"
logger = logging.getLogger(__name__)


def _normalize_nextcloud_path(path: str) -> str:
    raw_path = str(path or "").strip()
    if not raw_path:
        return ""
    if raw_path == "/":
        return "/"
    return f"/{raw_path.strip('/')}"


def _resolve_shared_target_path(path: str, share_map: dict[str, object]) -> str:
    normalized_path = _normalize_nextcloud_path(path)
    if not normalized_path:
        return ""

    direct_share = share_map.get(normalized_path)
    direct_target_path = str(getattr(direct_share, "target_path", "") or "").strip()
    if direct_target_path:
        return direct_target_path
    if direct_share is not None:
        return normalized_path

    parent_candidates = []
    for shared_path, share in share_map.items():
        normalized_shared_path = _normalize_nextcloud_path(shared_path)
        target_path = str(getattr(share, "target_path", "") or "").strip()
        if not normalized_shared_path:
            continue
        if normalized_path == normalized_shared_path or normalized_path.startswith(f"{normalized_shared_path}/"):
            parent_candidates.append((len(normalized_shared_path), normalized_shared_path, target_path))

    if not parent_candidates:
        return ""

    _, shared_path, target_path = max(parent_candidates, key=lambda item: item[0])
    if not target_path:
        return normalized_path
    suffix = normalized_path[len(shared_path) :].strip("/")
    if not suffix:
        return target_path
    return f"{target_path.rstrip('/')}/{suffix}"


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
):
    from classifiers_app.views import sync_autocomplete_registry_entry

    sync_autocomplete_registry_entry(
        short_name=short_name,
        country=country,
        identifier_type=identifier,
        registration_number=registration_number,
        registration_date=registration_date,
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


def _should_sync_proposal_related_row(item):
    return bool(
        (item.get("short_name") or "").strip()
        and (
            item.get("selected_from_autocomplete")
            or item.get("user_edited")
        )
    )


def _attach_proposal_folder_urls(proposals, user=None):
    folder_cache = {}
    share_resolution_paths = set()
    viewer_has_nextcloud_link = False

    def _stored_public(proposal):
        return (getattr(proposal, "proposal_workspace_public_url", "") or "").strip()

    def _assign_fallback_urls_without_share_resolution():
        for proposal in proposals:
            path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
            if not path:
                continue
            folder_cache.setdefault(path, build_folder_url(path))
            proposal.proposal_workspace_folder_url = _stored_public(proposal) or folder_cache.get(path, "")

    for proposal in proposals:
        path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
        proposal.proposal_workspace_folder_url = _stored_public(proposal)
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

    resolved_cache = {}
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

            for path in share_resolution_paths:
                target_path = _resolve_shared_target_path(path, share_map)
                direct_share = share_map.get(path)
                direct_target_path = str(getattr(direct_share, "target_path", "") or "").strip()
                if not target_path and direct_share is None:
                    try:
                        share = client.get_user_share(client.username, path, link.nextcloud_user_id)
                    except NextcloudApiError as exc:
                        logger.warning(
                            "Could not resolve Nextcloud share target for proposal path %s: %s",
                            path,
                            exc,
                        )
                        share = None
                    target_path = str(getattr(share, "target_path", "") or "").strip()
                elif not target_path and direct_target_path:
                    target_path = direct_target_path
                if target_path:
                    resolved_cache[path] = client.build_files_url(target_path)

    for proposal in proposals:
        path = getattr(proposal, "proposal_workspace_disk_path", "") or build_proposal_workspace_path(proposal)
        if path:
            if viewer_has_nextcloud_link:
                proposal.proposal_workspace_folder_url = (
                    resolved_cache.get(path)
                    or folder_cache.get(path, "")
                    or _stored_public(proposal)
                )
            else:
                proposal.proposal_workspace_folder_url = (
                    resolved_cache.get(path)
                    or _stored_public(proposal)
                    or folder_cache.get(path, "")
                )


def _proposals_context(user=None):
    proposals = ProposalRegistration.objects.select_related(
        "group_member",
        "country",
        "asset_owner_country",
        "type",
        "currency",
    ).all()
    _attach_proposal_folder_urls(proposals, user=user)
    proposal_templates = list(ProposalTemplate.objects.select_related("group_member", "product").all())
    proposal_variables = ProposalVariable.objects.all()
    order_map = _proposal_group_member_order_map()
    for template in proposal_templates:
        if template.group_member_id:
            template.group_display = _proposal_group_member_short(
                template.group_member, order_map.get(template.group_member_id, 0)
            )
        else:
            template.group_display = ""
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
        "primary_cloud_storage_label": get_primary_cloud_storage_label(),
        "proposal_request_sent_initial": timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M"),
        "has_active_smtp_connection": has_active_smtp_connection,
    }


def _render_proposals_updated(request):
    response = render(request, PROPOSALS_PARTIAL_TEMPLATE, _proposals_context(request.user))
    response[HX_TRIGGER_HEADER] = HX_PROPOSALS_UPDATED_EVENT
    return response


def _maybe_create_nextcloud_proposal_workspace(request, proposal) -> None:
    if not is_nextcloud_primary():
        return
    try:
        workspace_path = create_proposal_workspace(request.user, proposal)
    except NextcloudApiError:
        # The registry row should still be saved even if the cloud sync fails.
        return
    proposal.proposal_workspace_disk_path = workspace_path
    # For Nextcloud we want the table icon to resolve to a user share with editor
    # permissions, not to a public readonly link.
    proposal.proposal_workspace_public_url = ""
    proposal.save(update_fields=["proposal_workspace_disk_path", "proposal_workspace_public_url"])


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
            }
        )
    return render(
        request,
        PROPOSAL_FORM_TEMPLATE,
        {
            "form": form,
            "action": action,
            "proposal": proposal,
            "typical_sections_json": sections_map,
            "service_goal_reports_json": service_goal_reports_map,
            "typical_service_compositions_json": typical_service_compositions_map,
        },
    )


def _render_dispatch_form(request, *, form, proposal):
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


def _find_proposal_template(proposal, templates):
    if not proposal.type_id:
        return None

    candidates = []
    for template in templates:
        if template.product_id != proposal.type_id:
            continue
        if template.group_member_id and template.group_member_id != proposal.group_member_id:
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
            1 if template.group_member_id == proposal.group_member_id else 0,
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
    return render(request, PROPOSALS_PARTIAL_TEMPLATE, _proposals_context(request.user))


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
        request.user,
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
            request.user,
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
        request.user,
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
            request.user,
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

    form.save()
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
    if sent_proposal_ids:
        updated = ProposalRegistration.objects.filter(pk__in=sent_proposal_ids).update(sent_date=sent_at_display)

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
            "delivery_channels": list(email_result["delivery_channels"]),
            "email_delivery": email_result["email_delivery"],
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
        .order_by("position", "id")
    )
    if len(proposals) != len(proposal_ids):
        return JsonResponse({"ok": False, "error": "Часть выбранных строк не найдена."}, status=400)

    templates = list(
        ProposalTemplate.objects
        .select_related("group_member", "product")
        .filter(file__gt="")
    )
    variables = list(
        ProposalVariable.objects.filter(
            source_section__gt="",
            source_table__gt="",
            source_column__gt="",
        ).order_by("position", "id")
    )

    errors = []
    warnings = []
    generated_count = 0

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
            replacements, _ = resolve_variables(proposal, variables)
            from contracts_app.docx_processor import process_template

            docx_bytes = process_template(template_bytes, replacements)
            stored = store_generated_documents(proposal, docx_bytes, None)
        except Exception as exc:
            errors.append(f"{proposal.short_uid}: {exc}")
            continue

        ProposalRegistration.objects.filter(pk=proposal.pk).update(
            docx_file_name=stored["docx_name"],
            docx_file_link="",
            pdf_file_name=stored["pdf_name"],
            pdf_file_link=stored["pdf_url"],
        )
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

    return JsonResponse(
        {
            "ok": True,
            "message": "Документы ТКП успешно созданы.",
            "generated": generated_count,
            "warnings": warnings,
        }
    )


@login_required
@require_GET
def proposal_generated_docx_download(request, pk: int):
    proposal = get_object_or_404(ProposalRegistration, pk=pk)
    file_path = get_generated_docx_path(proposal)
    if not file_path:
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
    return _render_proposals_updated(request)


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
    return _render_proposals_updated(request)


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
