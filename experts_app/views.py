import json
import os

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Max, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from classifiers_app.models import TerritorialDivision
from policy_app.models import Grade
from .forms import ExpertSpecialtyForm, ExpertProfileForm, ExpertContractDetailsForm, _active_regions_qs
from .models import ExpertContractDetails, ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty

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
    eligible = Employee.objects.select_related("user").filter(user__is_staff=True)
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


def _sync_profile_contact_fields(profiles):
    updates = []
    for profile in profiles:
        expected_extra_email = profile.resolved_extra_email()
        expected_extra_phone = profile.resolved_extra_phone()
        expected_country = profile.resolved_country()
        expected_region = profile.resolved_region()
        if (
            profile.extra_email == expected_extra_email
            and profile.extra_phone == expected_extra_phone
            and profile.country_id == getattr(expected_country, "pk", None)
            and profile.region_id == getattr(expected_region, "pk", None)
        ):
            continue
        profile.extra_email = expected_extra_email
        profile.extra_phone = expected_extra_phone
        profile.country = expected_country
        profile.region = expected_region
        updates.append(profile)
    if updates:
        ExpertProfile.objects.bulk_update(updates, ["extra_email", "extra_phone", "country", "region"])


def _sync_contract_detail_records(profiles):
    from contacts_app.models import CitizenshipRecord

    person_to_profile = {}
    profile_ids = []
    for profile in profiles:
        employee = getattr(profile, "employee", None)
        person_id = getattr(employee, "person_record_id", None) if employee else None
        if not person_id:
            continue
        person_to_profile[person_id] = profile
        profile_ids.append(profile.pk)

    if not person_to_profile:
        if profile_ids:
            ExpertContractDetails.objects.filter(expert_profile_id__in=profile_ids).delete()
        return

    def _person_birth_date(profile):
        employee = getattr(profile, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "birth_date", None)

    def _person_full_name_genitive(profile):
        employee = getattr(profile, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "full_name_genitive", "") or ""

    def _person_gender(profile):
        employee = getattr(profile, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "gender", "") or ""

    def _calculated_citizenship(gender_value, citizenship):
        if (getattr(citizenship, "status", "") or "").strip() != "Гражданство":
            return ""
        country = getattr(citizenship, "country", None)
        country_name = (
            getattr(country, "short_name_genitive", "")
            or getattr(country, "short_name", "")
            or ""
        ).strip()
        prefix = ExpertContractDetails.CITIZENSHIP_PREFIXES.get(gender_value or "")
        if not prefix or not country_name:
            return ""
        return f"{prefix} {country_name}"

    citizenships = list(
        CitizenshipRecord.objects.select_related("country").filter(
            person_id__in=person_to_profile.keys()
        ).order_by("position", "id")
    )
    current_citizenship_ids = {item.pk for item in citizenships}
    existing_items = {
        item.citizenship_record_id: item
        for item in ExpertContractDetails.objects.select_related("citizenship_record").filter(
            citizenship_record_id__in=current_citizenship_ids
        )
    }

    to_create = []
    to_update = []
    for citizenship in citizenships:
        profile = person_to_profile.get(citizenship.person_id)
        if not profile:
            continue
        existing = existing_items.get(citizenship.pk)
        if existing is None:
            to_create.append(
                ExpertContractDetails(
                    expert_profile=profile,
                    citizenship_record=citizenship,
                    full_name_genitive=_person_full_name_genitive(profile),
                    gender=_person_gender(profile),
                    citizenship=_calculated_citizenship(_person_gender(profile), citizenship),
                    birth_date=_person_birth_date(profile),
                )
            )
            continue
        changed = False
        if existing.expert_profile_id != profile.pk:
            existing.expert_profile = profile
            changed = True
        expected_full_name_genitive = _person_full_name_genitive(profile)
        if existing.full_name_genitive != expected_full_name_genitive:
            existing.full_name_genitive = expected_full_name_genitive
            changed = True
        expected_gender = _person_gender(profile)
        if existing.gender != expected_gender:
            existing.gender = expected_gender
            changed = True
        expected_citizenship = _calculated_citizenship(expected_gender, citizenship)
        if existing.citizenship != expected_citizenship:
            existing.citizenship = expected_citizenship
            changed = True
        expected_birth_date = _person_birth_date(profile)
        if existing.birth_date != expected_birth_date:
            existing.birth_date = expected_birth_date
            changed = True
        if changed:
            to_update.append(existing)

    if to_create:
        ExpertContractDetails.objects.bulk_create(to_create)
    if to_update:
        ExpertContractDetails.objects.bulk_update(
            to_update,
            ["expert_profile", "full_name_genitive", "gender", "citizenship", "birth_date"],
        )

    ExpertContractDetails.objects.filter(expert_profile_id__in=profile_ids).exclude(
        citizenship_record_id__in=current_citizenship_ids
    ).delete()


def _experts_context():
    _ensure_profiles()
    profiles = list(
        ExpertProfile.objects.select_related(
            "employee", "employee__user", "employee__person_record", "employee__managed_email_record",
            "expertise_direction",
            "grade", "country", "region",
        ).filter(
            employee__user__is_staff=True,
        ).prefetch_related(
            "employee__person_record__emails",
            "employee__person_record__phones",
            "employee__person_record__residence_addresses",
            models.Prefetch(
                "ranked_specialties",
                queryset=ExpertProfileSpecialty.objects.select_related("specialty").order_by("rank"),
            ),
        ).all()
    )
    _sync_profile_contact_fields(profiles)
    _sync_contract_detail_records(profiles)
    contract_details = list(
        ExpertContractDetails.objects.select_related(
            "expert_profile",
            "expert_profile__employee",
            "expert_profile__employee__person_record",
            "expert_profile__employee__user",
            "citizenship_record",
            "citizenship_record__country",
            "citizenship_record__person",
        ).filter(
            expert_profile__employee__user__is_staff=True,
            citizenship_record__is_active=True,
        ).order_by(
            "expert_profile__position",
            "citizenship_record__position",
            "citizenship_record_id",
            "id",
        )
    )
    return {
        "specialties": ExpertSpecialty.objects.select_related(
            "expertise_direction", "expertise_dir",
            "head_of_direction", "head_of_direction__user",
        ).prefetch_related("owners").all(),
        "profiles": profiles,
        "contract_details": contract_details,
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
    contract_detail = get_object_or_404(
        ExpertContractDetails.objects.select_related(
            "expert_profile",
            "expert_profile__employee",
            "expert_profile__employee__person_record",
            "expert_profile__employee__user",
            "citizenship_record",
            "citizenship_record__country",
        ),
        pk=pk,
    )
    if request.method == "GET":
        form = ExpertContractDetailsForm(instance=contract_detail)
        return render(request, CONTRACT_DETAILS_FORM_TEMPLATE, {
            "form": form,
            "contract_detail": contract_detail,
        })
    old_facsimile_name = contract_detail.facsimile_file.name if contract_detail.facsimile_file else ""
    has_new_facsimile = "facsimile_file" in request.FILES
    clear_facsimile = bool(request.POST.get("facsimile_file-clear")) and not has_new_facsimile
    form = ExpertContractDetailsForm(request.POST, request.FILES, instance=contract_detail)
    if not form.is_valid():
        return render(request, CONTRACT_DETAILS_FORM_TEMPLATE, {
            "form": form,
            "contract_detail": contract_detail,
        })
    saved_contract_detail = form.save()
    new_facsimile_name = (
        saved_contract_detail.facsimile_file.name
        if saved_contract_detail.facsimile_file else ""
    )
    if old_facsimile_name and (clear_facsimile or (has_new_facsimile and old_facsimile_name != new_facsimile_name)):
        storage = saved_contract_detail._meta.get_field("facsimile_file").storage
        if storage.exists(old_facsimile_name):
            storage.delete(old_facsimile_name)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def contract_facsimile_download(request, pk: int):
    contract_detail = get_object_or_404(ExpertContractDetails, pk=pk)
    if not contract_detail.facsimile_file:
        raise Http404("Файл не найден")
    file_path = contract_detail.facsimile_file.path
    if not os.path.isfile(file_path):
        raise Http404("Файл не найден на диске")
    from urllib.parse import quote

    basename = os.path.basename(file_path)
    response = FileResponse(open(file_path, "rb"), content_type="application/octet-stream")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(basename)}"
    return response


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
