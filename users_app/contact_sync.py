from datetime import date as date_type

from django.contrib.auth import get_user_model
from django.db.models import Max, Q

from contacts_app.models import (
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    USER_KIND_EMPLOYEE,
    USER_KIND_EXTERNAL,
)


def _record_author(user=None):
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() if user else ""
    return full if full else getattr(user, "email", "") or getattr(user, "username", "") or ""


def _next_position(model):
    return (model.objects.aggregate(mx=Max("position")).get("mx") or 0) + 1


def _user_kind_for_employee(employee):
    return USER_KIND_EMPLOYEE if getattr(employee.user, "is_staff", False) else USER_KIND_EXTERNAL


def _source_for_employee(employee):
    return "[Пользователи / Сотрудники]" if getattr(employee.user, "is_staff", False) else "[Пользователи / Внешние пользователи]"


def _managed_organization_value(employee):
    if getattr(employee.user, "is_staff", False):
        values = [employee.employment or ""]
        department_name = ""
        if getattr(employee, "department_id", None) and getattr(employee, "department", None):
            department_name = employee.department.department_name or ""
        if department_name:
            values.append(department_name)
        return " / ".join(part.strip() for part in values if part and part.strip())
    return employee.organization or ""


def _linked_employee_queryset(employee_model, person_id, *, exclude_employee_id=None):
    queryset = employee_model.objects.select_related("user").filter(person_record_id=person_id)
    if exclude_employee_id:
        queryset = queryset.exclude(pk=exclude_employee_id)
    return queryset


def _resolve_person_user_kind(employee_model, person_id, *, exclude_employee_id=None):
    queryset = _linked_employee_queryset(
        employee_model,
        person_id,
        exclude_employee_id=exclude_employee_id,
    )
    if queryset.filter(user__is_staff=True).exists():
        return USER_KIND_EMPLOYEE
    if queryset.exists():
        return USER_KIND_EXTERNAL
    return ""


def _refresh_person_user_kind(employee_model, person_id, *, exclude_employee_id=None):
    if not person_id:
        return ""
    user_kind = _resolve_person_user_kind(
        employee_model,
        person_id,
        exclude_employee_id=exclude_employee_id,
    )
    PersonRecord.objects.filter(pk=person_id).update(user_kind=user_kind)
    return user_kind


def _bootstrap_citizenship(person):
    return (
        person.citizenships.filter(
            status="",
            identifier="",
            number="",
            valid_from__isnull=True,
            valid_to__isnull=True,
        )
        .order_by("position", "id")
        .first()
    )


def _bootstrap_phone(person):
    return (
        person.phones.filter(
            country__isnull=True,
            code="",
            phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
            region="",
            phone_number="",
            extension="",
            valid_to__isnull=True,
        )
        .order_by("position", "id")
        .first()
    )


def _ensure_person_bootstrap_rows(person, *, source="", actor=None):
    today = date_type.today()
    if not person.citizenships.exists():
        CitizenshipRecord.objects.create(
            person=person,
            country=person.citizenship,
            status="",
            identifier="",
            number="",
            valid_from=None,
            valid_to=None,
            record_date=today,
            record_author=_record_author(actor),
            source=source,
            position=_next_position(CitizenshipRecord),
        )
    else:
        citizenship = _bootstrap_citizenship(person)
        if citizenship and citizenship.source != source:
            CitizenshipRecord.objects.filter(pk=citizenship.pk).update(source=source)
    if not person.phones.exists():
        PhoneRecord.objects.create(
            person=person,
            country=None,
            code="",
            phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
            region="",
            phone_number="",
            is_primary=True,
            extension="",
            valid_from=today,
            valid_to=None,
            record_date=today,
            record_author=_record_author(actor),
            source=source,
            position=_next_position(PhoneRecord),
        )
    else:
        phone = _bootstrap_phone(person)
        if phone:
            updates = {}
            if phone.source != source:
                updates["source"] = source
            if not person.phones.filter(is_primary=True).exists():
                updates["is_primary"] = True
            if updates:
                PhoneRecord.objects.filter(pk=phone.pk).update(**updates)


def _sync_person(employee, *, actor=None):
    source = _source_for_employee(employee)
    previous_person_id = getattr(employee, "_previous_person_record_id", None)
    person = employee.person_record
    if person is None:
        person = PersonRecord.objects.create(
            last_name=employee.user.last_name or "",
            first_name=employee.user.first_name or "",
            middle_name=employee.patronymic or "",
            user_kind="",
            position=_next_position(PersonRecord),
        )
    else:
        updates = {}
        should_sync_person_name = bool(
            previous_person_id
            and previous_person_id == person.pk
            and not _linked_employee_queryset(employee.__class__, person.pk, exclude_employee_id=employee.pk).exists()
        )
        if should_sync_person_name:
            if person.last_name != (employee.user.last_name or ""):
                updates["last_name"] = employee.user.last_name or ""
            if person.first_name != (employee.user.first_name or ""):
                updates["first_name"] = employee.user.first_name or ""
            if person.middle_name != (employee.patronymic or ""):
                updates["middle_name"] = employee.patronymic or ""
        if updates:
            PersonRecord.objects.filter(pk=person.pk).update(**updates)
            for key, value in updates.items():
                setattr(person, key, value)
    _ensure_person_bootstrap_rows(person, source=source, actor=actor)
    return person


def _sync_managed_email(employee, person, *, actor=None):
    kind = _user_kind_for_employee(employee)
    source = _source_for_employee(employee)
    item = employee.managed_email_record
    today = date_type.today()
    defaults = {
        "person": person,
        "email": employee.user.email or "",
        "valid_from": today,
        "valid_to": None,
        "record_date": today,
        "record_author": _record_author(actor),
        "source": source,
        "position": _next_position(EmailRecord),
        "is_user_managed": True,
        "user_kind": kind,
    }
    if item is None or item.person_id != person.pk:
        reusable = (
            EmailRecord.objects
            .filter(
                person=person,
                email=defaults["email"],
                employee_email_link__isnull=True,
            )
            .order_by("-is_active", "position", "id")
            .first()
        )
        if reusable is None:
            return EmailRecord.objects.create(**defaults)
        item = reusable

    updates = {}
    if item.email != defaults["email"]:
        updates["email"] = defaults["email"]
    if not item.valid_from:
        updates["valid_from"] = today
    if item.valid_to is not None:
        updates["valid_to"] = None
    if not item.is_active:
        updates["is_active"] = True
    if item.record_date != today:
        updates["record_date"] = today
    if item.record_author != defaults["record_author"]:
        updates["record_author"] = defaults["record_author"]
    if item.source != defaults["source"]:
        updates["source"] = defaults["source"]
    if not item.is_user_managed:
        updates["is_user_managed"] = True
    if item.user_kind != kind:
        updates["user_kind"] = kind
    if updates:
        EmailRecord.objects.filter(pk=item.pk).update(**updates)
        for key, value in updates.items():
            setattr(item, key, value)
    return item


def _sync_managed_position(employee, person, *, actor=None):
    source = _source_for_employee(employee)
    item = employee.managed_position_record
    today = date_type.today()
    defaults = {
        "person": person,
        "organization_short_name": _managed_organization_value(employee),
        "job_title": employee.job_title or "",
        "valid_from": today,
        "valid_to": None,
        "record_date": today,
        "record_author": _record_author(actor),
        "source": source,
        "position": _next_position(PositionRecord),
        "is_user_managed": True,
    }
    if item is None or item.person_id != person.pk:
        reusable = (
            PositionRecord.objects
            .filter(
                person=person,
                organization_short_name=defaults["organization_short_name"],
                job_title=defaults["job_title"],
                employee_position_link__isnull=True,
            )
            .order_by("-is_active", "position", "id")
            .first()
        )
        if reusable is None:
            return PositionRecord.objects.create(**defaults)
        item = reusable

    updates = {}
    if item.organization_short_name != defaults["organization_short_name"]:
        updates["organization_short_name"] = defaults["organization_short_name"]
    if item.job_title != defaults["job_title"]:
        updates["job_title"] = defaults["job_title"]
    if not item.valid_from:
        updates["valid_from"] = today
    if item.valid_to is not None:
        updates["valid_to"] = None
    if not item.is_active:
        updates["is_active"] = True
    if item.record_date != today:
        updates["record_date"] = today
    if item.record_author != defaults["record_author"]:
        updates["record_author"] = defaults["record_author"]
    if item.source != defaults["source"]:
        updates["source"] = defaults["source"]
    if not item.is_user_managed:
        updates["is_user_managed"] = True
    if updates:
        PositionRecord.objects.filter(pk=item.pk).update(**updates)
        for key, value in updates.items():
            setattr(item, key, value)
    return item


def sync_employee_contacts(employee, *, actor=None):
    previous_person_id = getattr(employee, "_previous_person_record_id", None)
    if previous_person_id and previous_person_id != employee.person_record_id:
        detach_employee_contacts(employee, previous_person_id=previous_person_id)
        employee.managed_email_record = None
        employee.managed_email_record_id = None
        employee.managed_position_record = None
        employee.managed_position_record_id = None

    person = _sync_person(employee, actor=actor)
    email = _sync_managed_email(employee, person, actor=actor)
    position = _sync_managed_position(employee, person, actor=actor)
    employee.__class__.objects.filter(pk=employee.pk).update(
        person_record=person,
        managed_email_record=email,
        managed_position_record=position,
    )
    employee.person_record = person
    employee.managed_email_record = email
    employee.managed_position_record = position
    person.user_kind = _refresh_person_user_kind(employee.__class__, person.pk)
    employee._previous_person_record_id = person.pk


def _optional_pk(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _contact_attr(row, name):
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def staff_locked_contact_matches(*, emails=(), person_ids=(), email_record_ids=()):
    from .models import Employee

    email_keys = []
    seen_emails = set()
    for email in emails:
        key = str(email or "").strip().casefold()
        if not key or key in seen_emails:
            continue
        seen_emails.add(key)
        email_keys.append(key)
    locked_emails = set()
    if email_keys:
        query = Q()
        for key in email_keys:
            query |= Q(email__iexact=key)
        locked_emails = {
            str(email or "").strip().casefold()
            for email in get_user_model().objects.filter(is_staff=True).filter(query).values_list("email", flat=True)
            if str(email or "").strip()
        }
    person_id_set = {pk for pk in (_optional_pk(value) for value in person_ids) if pk}
    email_record_id_set = {pk for pk in (_optional_pk(value) for value in email_record_ids) if pk}
    locked_person_ids = set()
    if person_id_set:
        locked_person_ids = set(
            Employee.objects.filter(person_record_id__in=person_id_set, user__is_staff=True).values_list(
                "person_record_id",
                flat=True,
            )
        )
    locked_email_record_ids = set()
    if email_record_id_set:
        locked_email_record_ids = set(
            Employee.objects.filter(
                managed_email_record_id__in=email_record_id_set,
                user__is_staff=True,
            ).values_list("managed_email_record_id", flat=True)
        )
    return {
        "emails": locked_emails,
        "person_ids": locked_person_ids,
        "email_record_ids": locked_email_record_ids,
    }


def contact_fields_are_staff_locked(*, email="", person_id=None, email_record_id=None, matches=None):
    if matches is None:
        matches = staff_locked_contact_matches(
            emails=[email],
            person_ids=[person_id],
            email_record_ids=[email_record_id],
        )
    email_key = str(email or "").strip().casefold()
    person_pk = _optional_pk(person_id)
    email_record_pk = _optional_pk(email_record_id)
    if email_key and email_key in matches["emails"]:
        return True
    if person_pk and person_pk in matches["person_ids"]:
        return True
    if email_record_pk and email_record_pk in matches["email_record_ids"]:
        return True
    return False


def annotate_staff_locked_contacts(rows):
    rows = list(rows)
    matches = staff_locked_contact_matches(
        emails=[_contact_attr(row, "email") for row in rows],
        person_ids=[_contact_attr(row, "person_id") for row in rows],
        email_record_ids=[_contact_attr(row, "email_record_id") for row in rows],
    )
    for row in rows:
        locked = contact_fields_are_staff_locked(
            email=_contact_attr(row, "email"),
            person_id=_contact_attr(row, "person_id"),
            email_record_id=_contact_attr(row, "email_record_id"),
            matches=matches,
        )
        if isinstance(row, dict):
            row["contact_fields_locked"] = locked
        else:
            row.contact_fields_locked = locked
    return rows


def staff_employee_for_dispatch_contact(*, email="", person_id=None, email_record_id=None):
    from .models import Employee

    queryset = Employee.objects.select_related(
        "user",
        "person_record",
        "managed_email_record",
        "managed_position_record",
    ).filter(user__is_staff=True)
    normalized_email = str(email or "").strip()
    if normalized_email:
        match = queryset.filter(user__email__iexact=normalized_email).first()
        if match is not None:
            return match
    email_record_pk = _optional_pk(email_record_id)
    if email_record_pk:
        match = queryset.filter(managed_email_record_id=email_record_pk).first()
        if match is not None:
            return match
    person_pk = _optional_pk(person_id)
    if person_pk:
        match = queryset.filter(person_record_id=person_pk).first()
        if match is not None:
            return match
    if normalized_email:
        match = queryset.filter(managed_email_record__email__iexact=normalized_email).first()
        if match is not None:
            return match
    return None


def detach_employee_contacts(employee, *, previous_person_id=None):
    person_id = previous_person_id if previous_person_id is not None else employee.person_record_id
    if person_id:
        _refresh_person_user_kind(
            employee.__class__,
            person_id,
            exclude_employee_id=employee.pk,
        )
    if employee.managed_email_record_id:
        EmailRecord.objects.filter(pk=employee.managed_email_record_id).update(
            is_user_managed=False,
            user_kind="",
        )
    if employee.managed_position_record_id:
        PositionRecord.objects.filter(pk=employee.managed_position_record_id).update(
            is_user_managed=False,
        )
