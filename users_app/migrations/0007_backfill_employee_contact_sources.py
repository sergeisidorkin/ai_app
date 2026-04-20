from django.db import migrations


EMPLOYEE_SOURCE = "[Пользователи / Сотрудники]"
EXTERNAL_SOURCE = "[Пользователи / Внешние пользователи]"


def backfill_employee_contact_sources(apps, schema_editor):
    Employee = apps.get_model("users_app", "Employee")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")
    PhoneRecord = apps.get_model("contacts_app", "PhoneRecord")
    EmailRecord = apps.get_model("contacts_app", "EmailRecord")
    PositionRecord = apps.get_model("contacts_app", "PositionRecord")

    for employee in Employee.objects.select_related("user").order_by("position", "id").iterator():
        source = EMPLOYEE_SOURCE if employee.user.is_staff else EXTERNAL_SOURCE

        if employee.managed_email_record_id:
            EmailRecord.objects.filter(pk=employee.managed_email_record_id).update(source=source)

        if employee.managed_position_record_id:
            PositionRecord.objects.filter(pk=employee.managed_position_record_id).update(source=source)

        if employee.person_record_id:
            citizenship = (
                CitizenshipRecord.objects.filter(
                    person_id=employee.person_record_id,
                    status="",
                    identifier="",
                    number="",
                    valid_from__isnull=True,
                    valid_to__isnull=True,
                )
                .order_by("position", "id")
                .first()
            )
            if citizenship and citizenship.source != source:
                CitizenshipRecord.objects.filter(pk=citizenship.pk).update(source=source)

            phone = (
                PhoneRecord.objects.filter(
                    person_id=employee.person_record_id,
                    country_id__isnull=True,
                    code="",
                    phone_type="mobile",
                    region="",
                    phone_number="",
                    extension="",
                    valid_to__isnull=True,
                )
                .order_by("position", "id")
                .first()
            )
            if phone and phone.source != source:
                PhoneRecord.objects.filter(pk=phone.pk).update(source=source)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users_app", "0006_backfill_employee_contacts"),
    ]

    operations = [
        migrations.RunPython(backfill_employee_contact_sources, noop_reverse),
    ]
