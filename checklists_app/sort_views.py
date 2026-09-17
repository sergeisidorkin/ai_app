from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST

from projects_app.models import ProjectRegistration

from .access import user_can_sort_checklists
from .models import ChecklistSortProposal, ChecklistSortRun
from .sort_service import (
    SortConfigError,
    SortRunConflict,
    latest_runs_for_sections,
    section_label,
    serialize_run,
    start_sort_run,
)
from .sort_verify import (
    VerifyConflict,
    VerifyError,
    adopt_cross_section_proposals,
    start_verify_proposal,
)
from .views import _project_meta, _project_options, _resolve_asset_name, _resolve_section


def _forbid_unless_sorter(request):
    if not user_can_sort_checklists(request.user):
        return HttpResponseForbidden("Недостаточно прав.")
    return None


def _sort_project(request):
    project_uid = (request.GET.get("project_uid") or request.POST.get("project_uid") or "").strip()
    if not project_uid:
        return None, JsonResponse({"error": "Не выбран проект."}, status=400)
    project = get_object_or_404(
        ProjectRegistration.objects.select_related("type"),
        short_uid=project_uid,
    )
    return project, None


def _run_queryset():
    return ChecklistSortRun.objects.select_related("section").prefetch_related("proposals")


def _section_groups(project, resolved_asset, section_id):
    asset = resolved_asset if resolved_asset != "all" else ""
    meta = _project_meta(project, resolved_asset)
    sections_meta = list(meta.get("sections") or [])
    if section_id and section_id != "all":
        try:
            int(section_id)
        except (TypeError, ValueError):
            return [], None
        section = _resolve_section(project, section_id, resolved_asset)
        if section is None:
            return [], None
        match = [row for row in sections_meta if row["id"] == section.id]
        if match:
            sections_meta = match
        else:
            sections_meta = [{"id": section.id, "name": section_label(section)}]
    adopt_cross_section_proposals(project, asset)
    runs_map = latest_runs_for_sections(
        project,
        [row["id"] for row in sections_meta],
        asset,
    )
    groups = []
    for row in sections_meta:
        run = runs_map.get(row["id"])
        groups.append({
            "section_id": row["id"],
            "section_name": row["name"],
            "run": serialize_run(run) if run else None,
        })
    single_run = groups[0]["run"] if len(groups) == 1 else None
    return groups, single_run


@login_required
@require_GET
def sort_panel(request):
    forbidden = _forbid_unless_sorter(request)
    if forbidden:
        return forbidden

    project_options = _project_options(request.user)
    selected_project_uid = project_options[0]["short_uid"] if project_options else None
    selected_project = (
        ProjectRegistration.objects.select_related("type").filter(short_uid=selected_project_uid).first()
    )
    meta = _project_meta(selected_project, None) if selected_project else {
        "assets": [],
        "asset_items": [],
        "asset": "",
        "sections": [],
    }
    try:
        meta_url_base = reverse("checklists_app:project_meta", args=["__uid__"])
        start_url = reverse("checklists_app:sort_start")
        status_url = reverse("checklists_app:sort_status")
        verify_url = reverse("checklists_app:sort_verify")
    except NoReverseMatch:
        meta_url_base = "/checklists/project-meta/__uid__/"
        start_url = "/checklists/sort/start/"
        status_url = "/checklists/sort/status/"
        verify_url = "/checklists/sort/verify/"

    return render(
        request,
        "checklists_app/sort_panel.html",
        {
            "project_options": project_options,
            "selected_project_uid": selected_project_uid,
            "asset_items": meta.get("asset_items", []),
            "selected_asset": meta.get("asset") or "",
            "section_options": meta.get("sections") or [],
            "project_meta_url_base": meta_url_base,
            "sort_start_url": start_url,
            "sort_status_url": status_url,
            "sort_verify_url": verify_url,
            "allow_local_inbox": bool(getattr(settings, "DSH_SORT_ALLOW_LOCAL_INBOX", False)),
            "local_inbox_placeholder": "/Users/sergei/Desktop/Workspace/checklist-sort-test/inbox",
        },
    )


@login_required
@require_POST
def sort_start(request):
    forbidden = _forbid_unless_sorter(request)
    if forbidden:
        return forbidden

    project_uid = (request.POST.get("project_uid") or "").strip()
    section_id = (request.POST.get("section") or "").strip()
    asset_name = (request.POST.get("asset") or "").strip()
    if not project_uid:
        return JsonResponse({"error": "Не выбран проект."}, status=400)
    if not section_id or section_id == "all":
        return JsonResponse({"error": "Не выбран раздел."}, status=400)

    project = get_object_or_404(
        ProjectRegistration.objects.select_related("type"),
        short_uid=project_uid,
    )
    resolved_asset = _resolve_asset_name(project, asset_name)
    section = _resolve_section(project, section_id, resolved_asset)
    if section is None:
        return JsonResponse({"error": "Не выбран раздел."}, status=400)

    source_kind = (request.POST.get("source_kind") or "cloud").strip() or "cloud"
    local_inbox_path = (request.POST.get("local_inbox_path") or "").strip()
    if source_kind not in {"cloud", "local"}:
        source_kind = "cloud"

    try:
        run = start_sort_run(
            project=project,
            section=section,
            asset_name=resolved_asset if resolved_asset != "all" else "",
            user=request.user,
            source_kind=source_kind,
            local_inbox_path=local_inbox_path,
        )
    except SortConfigError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except SortRunConflict as exc:
        return JsonResponse({"error": str(exc)}, status=409)

    run = _run_queryset().get(pk=run.pk)
    return JsonResponse({"run": serialize_run(run)})


@login_required
@require_POST
def sort_verify(request):
    forbidden = _forbid_unless_sorter(request)
    if forbidden:
        return forbidden

    proposal_id = (request.POST.get("proposal_id") or "").strip()
    if not proposal_id:
        return JsonResponse({"error": "Не выбран комплект."}, status=400)
    proposal = get_object_or_404(
        ChecklistSortProposal.objects.select_related("run", "run__project", "run__section", "run__started_by"),
        pk=proposal_id,
    )
    origin_id = proposal.run_id
    try:
        start_verify_proposal(proposal=proposal, user=request.user)
    except VerifyError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except VerifyConflict as exc:
        run = _run_queryset().get(pk=proposal.run_id)
        return JsonResponse({"error": str(exc), "run": serialize_run(run)}, status=409)

    proposal.refresh_from_db()
    run = _run_queryset().get(pk=proposal.run_id)
    payload = {"run": serialize_run(run)}
    if proposal.run_id != origin_id:
        payload["origin_run"] = serialize_run(_run_queryset().get(pk=origin_id))
    return JsonResponse(payload)


@login_required
@require_GET
def sort_status(request):
    forbidden = _forbid_unless_sorter(request)
    if forbidden:
        return forbidden

    run_id = (request.GET.get("run_id") or "").strip()
    if run_id:
        run = get_object_or_404(_run_queryset(), pk=run_id)
        return JsonResponse({"run": serialize_run(run)})

    project, error = _sort_project(request)
    if error:
        return error
    section_id = (request.GET.get("section") or "all").strip() or "all"
    asset_name = (request.GET.get("asset") or "").strip()
    resolved_asset = _resolve_asset_name(project, asset_name)
    groups, single_run = _section_groups(project, resolved_asset, section_id)
    return JsonResponse({"run": single_run, "groups": groups})
