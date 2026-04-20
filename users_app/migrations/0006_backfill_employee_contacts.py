from django.db import migrations
from django.utils import timezone


def backfill_employee_contacts(apps, schema_editor):
    Employee = apps.get_model("users_app", "Employee")
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    PositionRecord = apps.get_model("contacts_app", "PositionRecord")
    PhoneRecord = apps.get_model("contacts_app", "PhoneRecord")
    EmailRecord = apps.get_model("contacts_app", "EmailRecord")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")

    def next_position(model):
        return model.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0

    next_prs = next_position(PersonRecord)
    next_ctz = next_position(CitizenshipRecord)
    next_tel = next_position(PhoneRecord)
    next_eml = next_position(EmailRecord)
    next_psn = next_position(PositionRecord)
    today = timezone.localdate()

    for employee in Employee.objects.select_related("user").order_by("position", "id").iterator():
        kind = "employee" if employee.user.is_staff else "external"

        next_prs += 1
        person = PersonRecord.objects.create(
            last_name=employee.user.last_name or "",
            first_name=employee.user.first_name or "",
            middle_name=employee.patronymic or "",
            user_kind=kind,
            position=next_prs,
        )

        next_ctz += 1
        CitizenshipRecord.objects.create(
            person=person,
            country_id=None,
            status="",
            identifier="",
            number="",
            valid_from=None,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_ctz,
        )

        next_tel += 1
        PhoneRecord.objects.create(
            person=person,
            country_id=None,
            code="",
            phone_type="mobile",
            region="",
            phone_number="",
            extension="",
            valid_from=today,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_tel,
        )

        next_eml += 1
        email = EmailRecord.objects.create(
            person=person,
            email=employee.user.email or "",
            valid_from=today,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_eml,
            is_user_managed=True,
            user_kind=kind,
        )

        next_psn += 1
        position = PositionRecord.objects.create(
            person=person,
            organization_short_name=(employee.employment if employee.user.is_staff else employee.organization) or "",
            job_title=employee.job_title or "",
            valid_from=today,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_psn,
            is_user_managed=True,
        )

        Employee.objects.filter(pk=employee.pk).update(
            person_record=person,
            managed_email_record=email,
            managed_position_record=position,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users_app", "0005_employee_contact_links_remove_phone"),
    ]

    operations = [
        migrations.RunPython(backfill_employee_contacts, noop_reverse),
    ]
