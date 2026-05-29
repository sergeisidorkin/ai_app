import csv
import io
import json
import os
from datetime import date as date_type

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from classifiers_app.models import TerritorialDivision
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ADMIN_GROUP,
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUPS,
    EXPERT_GROUP,
    ExpertiseDirection,
    LAWYER_GROUP,
    Grade,
)
from users_app.models import Employee
from contacts_app.models import SpecialtyRecord
from .forms import ExpertSpecialtyForm, ExpertProfileForm, ExpertContractDetailsForm, _active_regions_qs
from .models import ExpertContractDetails, ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty

PARTIAL_TEMPLATE = "experts_app/experts_partial.html"
CONTRACT_REQUISITES_PARTIAL_TEMPLATE = "experts_app/contract_requisites_partial.html"
FORM_TEMPLATE = "experts_app/specialty_form.html"
PROFILE_FORM_TEMPLATE = "experts_app/profile_form.html"
CONTRACT_DETAILS_FORM_TEMPLATE = "experts_app/contract_details_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "experts-updated"
CONTRACT_REQUISITES_HX_EVENT = "contract-requisites-updated"
CONTRACT_DETAILS_TARGET_REQUISITES = "contract-requisites"
EXECUTOR_SPECIALTY_SOURCE = "[Исполнители / База физлиц-исполнителей]"
CONTRACT_DETAILS_COLUMN_PICKER = (
    ("1", "ФИО"),
    ("2", "ФИО (полное) род. падеж"),
    ("3", "Страна гражданства"),
    ("4", "Статус"),
    ("5", "Дата рожд."),
    ("6", "Пол"),
    ("7", "Гражданство"),
    ("8", "Идентификатор"),
    ("9", "Номер"),
    ("10", "СНИЛС"),
    ("11", "Самозан."),
    ("12", "Налог"),
    ("13", "Паспорт: серия"),
    ("14", "номер"),
    ("15", "кем выдан"),
    ("16", "дата выдачи"),
    ("17", "срок действия"),
    ("18", "код подразд."),
    ("19", "адрес регистрации"),
    ("20", "Наименование банка"),
    ("21", "SWIFT"),
    ("22", "ИНН банка"),
    ("23", "БИК"),
    ("24", "Рас. счет"),
    ("25", "Кор. счет"),
    ("26", "Адрес банка"),
    ("27", "Наим. банка-корр."),
    ("28", "Адрес банка-корр."),
    ("29", "БИК банка-корр."),
    ("30", "SWIFT банка-корр."),
    ("31", "Рас. счет банка-корр."),
    ("32", "Кор. счет банка-корр."),
    ("33", "Факсимиле"),
)


def _render_form_with_errors(request, template, context):
    response = render(request, template, context)
    response["HX-Retarget"] = "#experts-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
    return response


def staff_required(u):
    return u.is_active and u.is_staff


def _experts_record_author(user):
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() if user else ""
    return full if full else getattr(user, "email", "") or getattr(user, "username", "")


def _active_specialty_record_q():
    today = date_type.today()
    return Q(valid_to__isnull=True) | Q(valid_to__gt=today)


def _profile_person(profile):
    employee = getattr(profile, "employee", None)
    return getattr(employee, "person_record", None) if employee else None


def contract_requisites_access_required(user):
    if not user or not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False
    employee = getattr(user, "employee_profile", None)
    employee_role = getattr(employee, "role", "") or ""
    is_expert = user.groups.filter(name=EXPERT_GROUP).exists() or employee_role == EXPERT_GROUP
    is_lawyer = user.groups.filter(name=LAWYER_GROUP).exists() or employee_role == LAWYER_GROUP
    is_admin = (
        getattr(user, "is_superuser", False)
        or user.groups.filter(name=ADMIN_GROUP).exists()
        or employee_role == ADMIN_GROUP
    )
    return is_admin or is_lawyer or not is_expert


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


def _sync_profile_specialties_from_contacts(profiles):
    for profile in profiles:
        getattr(profile, "_prefetched_objects_cache", {}).pop("ranked_specialties", None)
        person = _profile_person(profile)
        if not person:
            continue
        existing_links = list(
            ExpertProfileSpecialty.objects.filter(profile=profile)
            .select_related("contact_specialty_record")
            .order_by("rank", "id")
        )
        for link in existing_links:
            if link.contact_specialty_record_id or not link.specialty_id:
                continue
            contact_record = _ensure_contact_specialty_record(profile, link.specialty_id)
            if contact_record:
                link.contact_specialty_record = contact_record
                link.save(update_fields=["contact_specialty_record"])
        active_records = list(
            SpecialtyRecord.objects.filter(person=person)
            .filter(_active_specialty_record_q())
            .exclude(specialty__isnull=True)
            .select_related("specialty")
            .order_by("position", "id")
        )
        rank_by_record = {
            link.contact_specialty_record_id: link.rank
            for link in existing_links
            if link.contact_specialty_record_id
        }
        rank_by_specialty = {}
        for link in existing_links:
            rank_by_specialty.setdefault(link.specialty_id, link.rank)

        ordered_records = sorted(
            active_records,
            key=lambda item: (
                rank_by_record.get(item.pk, rank_by_specialty.get(item.specialty_id, 10**9)),
                item.position,
                item.pk,
            ),
        )
        desired = []
        seen_specialty_ids = set()
        for item in ordered_records:
            if not item.specialty_id or item.specialty_id in seen_specialty_ids:
                continue
            seen_specialty_ids.add(item.specialty_id)
            desired.append((item.pk, item.specialty_id))
        current = [(link.contact_specialty_record_id, link.specialty_id) for link in existing_links]
        if desired == current:
            continue
        ExpertProfileSpecialty.objects.filter(profile=profile).delete()
        to_create = [
            ExpertProfileSpecialty(
                profile=profile,
                specialty_id=specialty_id,
                contact_specialty_record_id=record_id,
                rank=rank,
            )
            for rank, (record_id, specialty_id) in enumerate(desired, start=1)
        ]
        if to_create:
            ExpertProfileSpecialty.objects.bulk_create(to_create)


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
                queryset=ExpertProfileSpecialty.objects.select_related(
                    "specialty", "contact_specialty_record",
                ).order_by("rank"),
            ),
        ).all()
    )
    _sync_profile_contact_fields(profiles)
    _sync_profile_specialties_from_contacts(profiles)
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


def _contract_details_context():
    _ensure_profiles()
    profiles = list(
        ExpertProfile.objects.select_related(
            "employee", "employee__user", "employee__person_record",
        ).filter(
            employee__user__is_staff=True,
        ).all()
    )
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
        "contract_details": contract_details,
        "contract_details_column_picker": CONTRACT_DETAILS_COLUMN_PICKER,
    }


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _experts_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _render_contract_details_updated(request):
    response = render(request, CONTRACT_REQUISITES_PARTIAL_TEMPLATE, _contract_details_context())
    response[HX_TRIGGER_HEADER] = CONTRACT_REQUISITES_HX_EVENT
    return response


def _contract_details_form_target(request):
    target_context = (
        request.POST.get("target_context")
        or request.GET.get("target")
        or ""
    )
    if target_context == CONTRACT_DETAILS_TARGET_REQUISITES:
        return CONTRACT_DETAILS_TARGET_REQUISITES, "#contract-requisites-pane"
    return "experts", "#experts-pane"


def _contract_details_form_context(form, contract_detail, target_context, hx_target):
    return {
        "form": form,
        "contract_detail": contract_detail,
        "contract_details_context": target_context,
        "contract_details_hx_target": hx_target,
    }


def _render_contract_details_form(request, form, contract_detail, target_context, hx_target):
    return render(
        request,
        CONTRACT_DETAILS_FORM_TEMPLATE,
        _contract_details_form_context(form, contract_detail, target_context, hx_target),
    )


def _render_contract_details_form_with_errors(request, form, contract_detail, target_context, hx_target):
    response = _render_contract_details_form(request, form, contract_detail, target_context, hx_target)
    if target_context == CONTRACT_DETAILS_TARGET_REQUISITES:
        response["HX-Retarget"] = "#contract-requisites-modal .modal-content"
    else:
        response["HX-Retarget"] = "#experts-contract-details-modal .modal-content"
    response["HX-Reswap"] = "innerHTML"
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


@login_required
@user_passes_test(contract_requisites_access_required)
@require_http_methods(["GET"])
def contract_requisites_partial(request):
    return render(request, CONTRACT_REQUISITES_PARTIAL_TEMPLATE, _contract_details_context())


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


ESP_CSV_HEADERS = [
    "Специальность",
    "Специальность на англ. языке",
    "Владелец",
    "Направление экспертизы",
    "Подразделение",
    "Руководитель направления",
]


def _csv_lookup_key(value):
    return str(value or "").strip().lower()


def _specialties_queryset():
    return ExpertSpecialty.objects.select_related(
        "expertise_direction",
        "expertise_dir",
        "head_of_direction",
        "head_of_direction__user",
    ).prefetch_related("owners").order_by("position", "id")


def _parse_experts_csv_rows(csv_file):
    if not csv_file:
        return None, {"ok": False, "error": "Файл не выбран."}
    if not csv_file.name.lower().endswith(".csv"):
        return None, {"ok": False, "error": "Допустимы только файлы CSV."}

    try:
        raw = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode("cp1251")
        except Exception:
            return None, {
                "ok": False,
                "error": "Не удалось прочитать файл. Проверьте кодировку (UTF-8 или Windows-1251).",
            }

    try:
        reader = csv.reader(io.StringIO(raw), delimiter=";")
        rows = list(reader)
        if not rows:
            return None, {"ok": False, "error": "Файл пуст."}
        if len(rows[0]) <= 1:
            reader = csv.reader(io.StringIO(raw), delimiter=",")
            rows = list(reader)
    except csv.Error as exc:
        return None, {
            "ok": False,
            "error": f"Ошибка разбора CSV: {exc}. Проверьте формат и кодировку файла.",
        }

    if len(rows) < 2:
        return None, {
            "ok": False,
            "error": "Файл должен содержать заголовок и хотя бы одну строку данных.",
        }
    return rows, None


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def esp_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(ESP_CSV_HEADERS)

    for item in _specialties_queryset():
        writer.writerow(
            [
                item.specialty,
                item.specialty_en,
                item.owner_display,
                item.expertise_dir.short_name if item.expertise_dir else "",
                item.expertise_direction.department_name if item.expertise_direction else "",
                item.head_of_direction.job_title if item.head_of_direction else "",
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="expert_specialties.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def esp_csv_upload(request):
    rows, error = _parse_experts_csv_rows(request.FILES.get("csv_file"))
    if error:
        return JsonResponse(error, status=400)

    specialties_by_name = {
        _csv_lookup_key(s.specialty): s
        for s in ExpertSpecialty.objects.exclude(specialty="").all()
    }
    expertise_dirs = {}
    for direction in ExpertiseDirection.objects.all():
        for label in (direction.short_name, direction.name):
            key = _csv_lookup_key(label)
            if key:
                expertise_dirs[key] = direction
    org_units = {
        key: unit
        for unit in OrgUnit.objects.all()
        for key in (_csv_lookup_key(unit.department_name), _csv_lookup_key(unit.short_name))
        if key
    }
    employees_by_job_title = {
        _csv_lookup_key(employee.job_title): employee
        for employee in Employee.objects.filter(
            role__in=(DEPARTMENT_HEAD_GROUP, *DIRECTOR_GROUPS),
        ).exclude(job_title="")
    }
    owners_by_short_name = {
        member.short_name.strip().lower(): member
        for member in GroupMember.objects.exclude(short_name="").all()
    }

    created = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 6:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 6: "
                "Специальность, Специальность на англ. языке, Владелец, "
                "Направление экспертизы, Подразделение, Руководитель направления."
            )
            continue

        specialty = row[0].strip()
        specialty_en = row[1].strip()
        owner_raw = row[2].strip()
        expertise_dir_name = row[3].strip()
        department_name = row[4].strip()
        head_of_direction_name = row[5].strip()

        if not specialty:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: Специальность.")
            continue

        if _csv_lookup_key(specialty) in specialties_by_name:
            warnings.append(f"Строка {i}: специальность «{specialty}» уже существует, пропущена.")
            continue

        expertise_dir = None
        if expertise_dir_name:
            expertise_dir = expertise_dirs.get(_csv_lookup_key(expertise_dir_name))
            if expertise_dir is None:
                warnings.append(f"Строка {i}: направление экспертизы «{expertise_dir_name}» не найдено.")
                continue

        expertise_direction = None
        if department_name:
            expertise_direction = org_units.get(_csv_lookup_key(department_name))
            if expertise_direction is None:
                warnings.append(f"Строка {i}: подразделение «{department_name}» не найдено.")
                continue

        head_of_direction = None
        if head_of_direction_name:
            head_of_direction = employees_by_job_title.get(_csv_lookup_key(head_of_direction_name))
            if head_of_direction is None:
                warnings.append(
                    f"Строка {i}: руководитель направления «{head_of_direction_name}» не найден."
                )
                continue

        is_group_owner = not owner_raw or owner_raw == "Группа"
        owner_ids = []
        if not is_group_owner:
            owner_names = [item.strip() for item in owner_raw.split(",") if item.strip()]
            missing_owners = [
                name for name in owner_names if name.lower() not in owners_by_short_name
            ]
            if missing_owners:
                warnings.append(f"Строка {i}: владельцы не найдены: {', '.join(missing_owners)}.")
                continue
            owner_ids = [owners_by_short_name[name.lower()].pk for name in owner_names]

        try:
            item = ExpertSpecialty.objects.create(
                specialty=specialty,
                specialty_en=specialty_en,
                expertise_dir=expertise_dir,
                expertise_direction=expertise_direction,
                head_of_direction=head_of_direction,
                is_group_owner=is_group_owner,
                position=_next_position(),
            )
            if owner_ids:
                item.owners.set(owner_ids)
            specialties_by_name[_csv_lookup_key(specialty)] = item
            created += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return JsonResponse({"ok": True, "created": created, "warnings": warnings})


EPR_CSV_HEADERS = [
    "ФИО",
    "Эл. почта (логин)",
    "Дополнительная эл. почта",
    "Телефон",
    "Дополнительный телефон",
    "Направление экспертизы",
    "Специальность",
    "Профессиональный статус",
    "Профессиональный статус (кратко)",
    "Грейд",
    "Страна",
    "Регион проживания",
    "Статус",
    "Дата",
]


def _profiles_list():
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
                queryset=ExpertProfileSpecialty.objects.select_related(
                    "specialty", "contact_specialty_record",
                ).order_by("rank"),
            ),
        ).order_by("position", "id")
    )
    _sync_profile_contact_fields(profiles)
    _sync_profile_specialties_from_contacts(profiles)
    return profiles


def _profile_specialties_display(profile):
    parts = []
    for link in profile.ranked_specialties.all():
        name = (link.specialty.specialty or "").strip()
        if name:
            parts.append(name)
    return ", ".join(parts)


def _save_profile_specialties_by_names(profile, specialties_raw, specialties_by_name, *, user=None):
    specialty_names = [item.strip() for item in specialties_raw.split(",") if item.strip()]
    rows = []
    missing = []
    for name in specialty_names:
        spec = specialties_by_name.get(_csv_lookup_key(name))
        if spec is None:
            missing.append(name)
            continue
        rows.append({"specialty_id": str(spec.pk), "contact_specialty_record_id": ""})
    if missing:
        return False, missing
    _sync_ranked_specialties_to_contact_records(profile, rows, user=user)
    return True, []


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET"])
def epr_csv_download(request):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(EPR_CSV_HEADERS)

    for profile in _profiles_list():
        writer.writerow(
            [
                profile.full_name,
                profile.employee.user.email or "",
                profile.resolved_extra_email() or "",
                profile.employee.primary_phone_display or "",
                profile.resolved_extra_phone() or "",
                profile.expertise_direction.department_name if profile.expertise_direction else "",
                _profile_specialties_display(profile),
                profile.professional_status,
                profile.professional_status_short,
                profile.grade.grade_ru if profile.grade else "",
                profile.country.short_name if profile.country else "",
                profile.region.region_name if profile.region else "",
                profile.status,
                profile.updated_at.strftime("%d.%m.%Y") if profile.updated_at else "",
            ]
        )

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="expert_profiles.csv"'
    return response


@login_required
@user_passes_test(staff_required)
@require_POST
def epr_csv_upload(request):
    rows, error = _parse_experts_csv_rows(request.FILES.get("csv_file"))
    if error:
        return JsonResponse(error, status=400)

    profiles_by_email = {}
    for profile in _profiles_list():
        email = (profile.employee.user.email or "").strip().lower()
        if email:
            profiles_by_email[email] = profile

    org_units = {
        key: unit
        for unit in OrgUnit.objects.filter(Q(unit_type="expertise") | Q(level=1))
        for key in (_csv_lookup_key(unit.department_name), _csv_lookup_key(unit.short_name))
        if key
    }
    grades_by_name = {
        _csv_lookup_key(grade.grade_ru): grade
        for grade in Grade.objects.exclude(grade_ru="").all()
    }
    specialties_by_name = {
        _csv_lookup_key(s.specialty): s
        for s in ExpertSpecialty.objects.exclude(specialty="").all()
    }

    updated = 0
    warnings = []

    for i, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < 14:
            warnings.append(
                f"Строка {i}: недостаточно столбцов ({len(row)}, ожидается 14: "
                "ФИО, Эл. почта (логин), Дополнительная эл. почта, Телефон, "
                "Дополнительный телефон, Направление экспертизы, Специальность, "
                "Профессиональный статус, Профессиональный статус (кратко), Грейд, "
                "Страна, Регион проживания, Статус, Дата."
            )
            continue

        email = row[1].strip()
        if not email:
            warnings.append(f"Строка {i}: не заполнены обязательные поля: Эл. почта (логин).")
            continue

        profile = profiles_by_email.get(email.lower())
        if profile is None:
            warnings.append(f"Строка {i}: исполнитель с email «{email}» не найден, пропущена.")
            continue

        expertise_direction_name = row[5].strip()
        specialties_raw = row[6].strip()
        professional_status = row[7].strip()
        professional_status_short = row[8].strip()
        grade_name = row[9].strip()
        status = row[12].strip()

        expertise_direction = None
        if expertise_direction_name:
            expertise_direction = org_units.get(_csv_lookup_key(expertise_direction_name))
            if expertise_direction is None:
                warnings.append(
                    f"Строка {i}: направление экспертизы «{expertise_direction_name}» не найдено."
                )
                continue

        grade = None
        if grade_name:
            grade = grades_by_name.get(_csv_lookup_key(grade_name))
            if grade is None:
                warnings.append(f"Строка {i}: грейд «{grade_name}» не найден.")
                continue

        ok, missing_specialties = _save_profile_specialties_by_names(
            profile, specialties_raw, specialties_by_name, user=request.user,
        )
        if not ok:
            warnings.append(
                f"Строка {i}: специальности не найдены: {', '.join(missing_specialties)}."
            )
            continue

        try:
            profile.expertise_direction = expertise_direction
            profile.professional_status = professional_status
            profile.professional_status_short = professional_status_short
            profile.grade = grade
            profile.status = status
            profile.save(update_fields=[
                "expertise_direction",
                "professional_status",
                "professional_status_short",
                "grade",
                "status",
                "updated_at",
            ])
            updated += 1
        except Exception as exc:
            warnings.append(f"Строка {i}: ошибка сохранения — {exc}")

    return JsonResponse({"ok": True, "updated": updated, "warnings": warnings})


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
    _sync_profile_specialties_from_contacts([profile])
    person = _profile_person(profile)
    ranked_specialties = []
    used_contact_ids = set()
    links = (
        ExpertProfileSpecialty.objects.filter(profile=profile)
        .select_related("contact_specialty_record")
        .order_by("rank", "id")
    )
    for link in links:
        contact_record = link.contact_specialty_record
        if contact_record_id := getattr(contact_record, "pk", None):
            if (
                person
                and contact_record.person_id == person.pk
                and contact_record.specialty_id
                and (contact_record.valid_to is None or contact_record.valid_to > date_type.today())
            ):
                ranked_specialties.append(
                    {
                        "rank": len(ranked_specialties) + 1,
                        "specialty_id": contact_record.specialty_id,
                        "contact_specialty_record_id": contact_record_id,
                    }
                )
                used_contact_ids.add(contact_record_id)
            continue
        if link.specialty_id:
            ranked_specialties.append(
                {
                    "rank": len(ranked_specialties) + 1,
                    "specialty_id": link.specialty_id,
                    "contact_specialty_record_id": "",
                }
            )
    if person:
        extra_records = (
            SpecialtyRecord.objects.filter(person=person)
            .filter(_active_specialty_record_q())
            .exclude(pk__in=used_contact_ids)
            .exclude(specialty__isnull=True)
            .order_by("position", "id")
        )
        for record in extra_records:
            ranked_specialties.append(
                {
                    "rank": len(ranked_specialties) + 1,
                    "specialty_id": record.specialty_id,
                    "contact_specialty_record_id": record.pk,
                }
            )
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


def _next_contact_specialty_position():
    return (SpecialtyRecord.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _close_contact_specialty_record(record, *, user=None):
    today = date_type.today()
    if record.valid_to and record.valid_to <= today:
        return
    record.valid_to = today
    record.record_date = today
    record.record_author = _experts_record_author(user)
    record.save(update_fields=["valid_to", "record_date", "record_author", "is_active", "updated_at"])


def _ensure_contact_specialty_record(profile, specialty_id, contact_record_id="", *, user=None):
    person = _profile_person(profile)
    if not person or not specialty_id:
        return None
    today = date_type.today()
    contact_record = None
    if contact_record_id:
        contact_record = SpecialtyRecord.objects.filter(pk=contact_record_id, person=person).first()
        if contact_record and contact_record.specialty_id != specialty_id:
            _close_contact_specialty_record(contact_record, user=user)
            contact_record = None
    if contact_record is None:
        contact_record = (
            SpecialtyRecord.objects.filter(person=person, specialty_id=specialty_id)
            .filter(_active_specialty_record_q())
            .order_by("position", "id")
            .first()
        )
    if contact_record is None:
        contact_record = SpecialtyRecord(
            person=person,
            specialty_id=specialty_id,
            valid_from=today,
            valid_to=None,
            is_active=True,
            user_kind=person.user_kind or "",
            record_date=today,
            record_author=_experts_record_author(user),
            source=EXECUTOR_SPECIALTY_SOURCE,
            position=_next_contact_specialty_position(),
        )
        contact_record.save()
    else:
        update_fields = []
        if contact_record.valid_to is not None and contact_record.valid_to <= today:
            contact_record.valid_to = None
            update_fields.append("valid_to")
        expected_user_kind = person.user_kind or ""
        if contact_record.user_kind != expected_user_kind:
            contact_record.user_kind = expected_user_kind
            update_fields.append("user_kind")
        if not contact_record.source:
            contact_record.source = EXECUTOR_SPECIALTY_SOURCE
            update_fields.append("source")
        if update_fields:
            contact_record.save(update_fields=update_fields + ["is_active", "updated_at"])
    return contact_record


def _sync_ranked_specialties_to_contact_records(profile, rows, *, user=None):
    person = _profile_person(profile)
    selected = []
    seen_specialty_ids = set()
    for row in rows:
        raw_specialty_id = row.get("specialty_id")
        if not raw_specialty_id:
            continue
        try:
            specialty_id = int(raw_specialty_id)
        except (TypeError, ValueError):
            continue
        if specialty_id in seen_specialty_ids:
            continue
        seen_specialty_ids.add(specialty_id)
        contact_record = _ensure_contact_specialty_record(
            profile,
            specialty_id,
            row.get("contact_specialty_record_id") or "",
            user=user,
        )
        selected.append((specialty_id, contact_record))

    selected_contact_ids = {record.pk for _, record in selected if record is not None}
    if person:
        obsolete_records = (
            SpecialtyRecord.objects.filter(person=person)
            .filter(_active_specialty_record_q())
            .exclude(pk__in=selected_contact_ids)
        )
        for record in obsolete_records:
            _close_contact_specialty_record(record, user=user)

    ExpertProfileSpecialty.objects.filter(profile=profile).delete()
    to_create = [
        ExpertProfileSpecialty(
            profile=profile,
            specialty_id=specialty_id,
            contact_specialty_record=contact_record,
            rank=rank,
        )
        for rank, (specialty_id, contact_record) in enumerate(selected, start=1)
    ]
    if to_create:
        ExpertProfileSpecialty.objects.bulk_create(to_create)


def _save_ranked_specialties(profile, post_data, *, user=None):
    specialty_ids = post_data.getlist("specialty_id")
    contact_record_ids = post_data.getlist("contact_specialty_record_id")
    rows = []
    for idx, specialty_id in enumerate(specialty_ids):
        rows.append(
            {
                "specialty_id": specialty_id,
                "contact_specialty_record_id": contact_record_ids[idx] if idx < len(contact_record_ids) else "",
            }
        )
    _sync_ranked_specialties_to_contact_records(profile, rows, user=user)


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
    _save_ranked_specialties(profile, request.POST, user=request.user)
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
    target_context, hx_target = _contract_details_form_target(request)
    if request.method == "GET":
        form = ExpertContractDetailsForm(instance=contract_detail)
        return _render_contract_details_form(request, form, contract_detail, target_context, hx_target)
    old_facsimile_name = contract_detail.facsimile_file.name if contract_detail.facsimile_file else ""
    has_new_facsimile = "facsimile_file" in request.FILES
    clear_facsimile = bool(request.POST.get("facsimile_file-clear")) and not has_new_facsimile
    form = ExpertContractDetailsForm(request.POST, request.FILES, instance=contract_detail)
    if not form.is_valid():
        return _render_contract_details_form_with_errors(
            request, form, contract_detail, target_context, hx_target
        )
    saved_contract_detail = form.save()
    new_facsimile_name = (
        saved_contract_detail.facsimile_file.name
        if saved_contract_detail.facsimile_file else ""
    )
    if old_facsimile_name and (clear_facsimile or (has_new_facsimile and old_facsimile_name != new_facsimile_name)):
        storage = saved_contract_detail._meta.get_field("facsimile_file").storage
        if storage.exists(old_facsimile_name):
            storage.delete(old_facsimile_name)
    if target_context == CONTRACT_DETAILS_TARGET_REQUISITES:
        return _render_contract_details_updated(request)
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
