import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from classifiers_app.models import TerritorialDivision
from policy_app.models import Grade
from .forms import ExpertSpecialtyForm, ExpertProfileForm, ExpertContractDetailsForm, _active_regions_qs
from .models import ExpertSpecialty, ExpertProfile, ExpertProfileSpecialty, EXCLUDED_ROLES

PARTIAL_TEMPLATE = "experts_app/experts_partial.html"
FORM_TEMPLATE = "experts_app/specialty_form.html"
PROFILE_FORM_TEMPLATE = "experts_app/profile_form.html"
CONTRACT_DETAILS_FORM_TEMPLATE = "experts_app/contract_details_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "experts-updated"


def _render_form_with_errors(request, template, context):
    response = render(request, template, context)
    response["HX-Retarget"] = "#experts-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


def staff_required(u):
    return u.is_active and u.is_staff


def _ensure_profiles():
    from users_app.models import Employee
    eligible = Employee.objects.select_related("user").exclude(
        role__in=EXCLUDED_ROLES
    ).exclude(role="")
    existing_ids = set(
        ExpertProfile.objects.values_list("employee_id", flat=True)
    )
    to_create = []
    mx = ExpertProfile.objects.aggregate(m=Max("position"))["m"] or 0
    for emp in eligible:
        if emp.pk not in existing_ids:
            mx += 1
            to_create.append(ExpertProfile(employee=emp, position=mx))
    if to_create:
        ExpertProfile.objects.bulk_create(to_create)


def _experts_context():
    _ensure_profiles()
    return {
        "specialties": ExpertSpecialty.objects.select_related(
            "expertise_direction", "expertise_dir",
            "head_of_direction", "head_of_direction__user",
        ).prefetch_related("owners").all(),
        "profiles": ExpertProfile.objects.select_related(
            "employee", "employee__user",
            "expertise_direction",
            "grade", "country", "region",
        ).prefetch_related(
            models.Prefetch(
                "ranked_specialties",
                queryset=ExpertProfileSpecialty.objects.select_related("specialty").order_by("rank"),
            )
        ).all(),
    }


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _experts_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_position():
    mx = ExpertSpecialty.objects.aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _normalize_positions():
    for idx, obj in enumerate(ExpertSpecialty.objects.all()):
        if obj.position != idx:
            ExpertSpecialty.objects.filter(pk=obj.pk).update(position=idx)


# ---------------------------------------------------------------------------
#  Partials
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def experts_partial(request):
    return render(request, PARTIAL_TEMPLATE, _experts_context())


# ---------------------------------------------------------------------------
#  ExpertSpecialty CRUD
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_form_create(request):
    if request.method == "GET":
        form = ExpertSpecialtyForm()
        return render(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ExpertSpecialtyForm(request.POST)
    if not form.is_valid():
        return _render_form_with_errors(request, FORM_TEMPLATE, {"form": form, "action": "create"})
    form.instance.position = _next_position()
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def specialty_form_edit(request, pk: int):
    specialty = get_object_or_404(ExpertSpecialty, pk=pk)
    if request.method == "GET":
        form = ExpertSpecialtyForm(instance=specialty)
        return render(request, FORM_TEMPLATE, {"form": form, "action": "edit", "specialty": specialty})
    form = ExpertSpecialtyForm(request.POST, instance=specialty)
    if not form.is_valid():
        return _render_form_with_errors(request, FORM_TEMPLATE, {"form": form, "action": "edit", "specialty": specialty})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def specialty_delete(request, pk: int):
    get_object_or_404(ExpertSpecialty, pk=pk).delete()
    _normalize_positions()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def specialty_move_up(request, pk: int):
    obj = get_object_or_404(ExpertSpecialty, pk=pk)
    prev = ExpertSpecialty.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ExpertSpecialty.objects.filter(pk=obj.pk).update(position=obj.position)
        ExpertSpecialty.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def specialty_move_down(request, pk: int):
    obj = get_object_or_404(ExpertSpecialty, pk=pk)
    nxt = ExpertSpecialty.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ExpertSpecialty.objects.filter(pk=obj.pk).update(position=obj.position)
        ExpertSpecialty.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  ExpertProfile CRUD
# ---------------------------------------------------------------------------

def _specialty_options():
    return [
        {"id": s.pk, "label": s.specialty}
        for s in ExpertSpecialty.objects.exclude(specialty="").order_by("position")
    ]


def _profile_form_context(form, profile):
    grades_map = _build_grades_map()
    regions_map = _build_regions_map()
    spec_options = _specialty_options()
    ranked_specialties = [
        {"rank": link.rank, "specialty_id": link.specialty_id}
        for link in ExpertProfileSpecialty.objects.filter(profile=profile).order_by("rank")
    ]
    return {
        "form": form,
        "action": "edit",
        "profile": profile,
        "grades_map_json": json.dumps(grades_map, ensure_ascii=False),
        "regions_map_json": json.dumps(regions_map, ensure_ascii=False),
        "specialty_options": spec_options,
        "specialty_options_json": json.dumps(spec_options, ensure_ascii=False),
        "ranked_specialties": ranked_specialties,
    }


def _save_ranked_specialties(profile, post_data):
    specialty_ids = post_data.getlist("specialty_id")
    ExpertProfileSpecialty.objects.filter(profile=profile).delete()
    to_create = []
    for rank, raw_id in enumerate(specialty_ids, start=1):
        if raw_id:
            try:
                sid = int(raw_id)
            except (ValueError, TypeError):
                continue
            to_create.append(ExpertProfileSpecialty(
                profile=profile, specialty_id=sid, rank=rank,
            ))
    if to_create:
        ExpertProfileSpecialty.objects.bulk_create(to_create)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def profile_form_edit(request, pk: int):
    profile = get_object_or_404(ExpertProfile, pk=pk)
    if request.method == "GET":
        form = ExpertProfileForm(instance=profile)
        return render(request, PROFILE_FORM_TEMPLATE, _profile_form_context(form, profile))
    form = ExpertProfileForm(request.POST, instance=profile)
    if not form.is_valid():
        return render(request, PROFILE_FORM_TEMPLATE, _profile_form_context(form, profile))
    form.save()
    _save_ranked_specialties(profile, request.POST)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def profile_move_up(request, pk: int):
    obj = get_object_or_404(ExpertProfile, pk=pk)
    prev = ExpertProfile.objects.filter(position__lt=obj.position).order_by("-position").first()
    if prev:
        obj.position, prev.position = prev.position, obj.position
        ExpertProfile.objects.filter(pk=obj.pk).update(position=obj.position)
        ExpertProfile.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def profile_move_down(request, pk: int):
    obj = get_object_or_404(ExpertProfile, pk=pk)
    nxt = ExpertProfile.objects.filter(position__gt=obj.position).order_by("position").first()
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        ExpertProfile.objects.filter(pk=obj.pk).update(position=obj.position)
        ExpertProfile.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  ExpertProfile Contract Details
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def contract_details_form_edit(request, pk: int):
    profile = get_object_or_404(ExpertProfile, pk=pk)
    if request.method == "GET":
        form = ExpertContractDetailsForm(instance=profile)
        return render(request, CONTRACT_DETAILS_FORM_TEMPLATE, {
            "form": form, "profile": profile,
        })
    form = ExpertContractDetailsForm(request.POST, instance=profile)
    if not form.is_valid():
        return render(request, CONTRACT_DETAILS_FORM_TEMPLATE, {
            "form": form, "profile": profile,
        })
    form.save()
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  JSON helpers for dynamic form filtering
# ---------------------------------------------------------------------------

def _build_grades_map():
    """direction_id -> [{id, label, qualification}, ...]"""
    result = {}
    for g in Grade.objects.select_related(
        "created_by__employee_profile"
    ).all():
        emp = getattr(g.created_by, "employee_profile", None)
        dept_id = str(emp.department_id) if emp and emp.department_id else "__none__"
        result.setdefault(dept_id, []).append({
            "id": g.pk,
            "label": g.grade_ru,
            "qualification": g.qualification,
            "qualification_levels": g.qualification_levels,
        })
    return result


def _build_regions_map():
    """country_id -> [{id, label}, ...]"""
    result = {}
    for r in _active_regions_qs():
        key = str(r.country_id)
        result.setdefault(key, []).append({
            "id": r.pk,
            "label": r.region_name,
        })
    return result
