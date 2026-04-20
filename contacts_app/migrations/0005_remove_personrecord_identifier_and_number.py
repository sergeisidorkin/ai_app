from django.db import migrations
from django.utils import timezone


def move_person_identifiers_to_citizenships(apps, schema_editor):
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")

    next_position = CitizenshipRecord.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0
    today = timezone.localdate()

    for person in PersonRecord.objects.order_by("position", "id").iterator():
        identifier = person.identifier or ""
        number = person.number or ""
        if not identifier and not number:
            continue

        citizenship = (
            CitizenshipRecord.objects
            .filter(person_id=person.pk)
            .order_by("position", "id")
            .first()
        )
        if citizenship is None:
            next_position += 1
            CitizenshipRecord.objects.create(
                person_id=person.pk,
                country_id=person.citizenship_id,
                status="",
                identifier=identifier,
                number=number,
                valid_from=None,
                valid_to=None,
                record_date=today,
                record_author="",
                source="",
                position=next_position,
            )
            continue

        updates = {}
        if identifier and not citizenship.identifier:
            updates["identifier"] = identifier
        if number and not citizenship.number:
            updates["number"] = number
        if updates:
            CitizenshipRecord.objects.filter(pk=citizenship.pk).update(**updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("contacts_app", "0004_personrecord_birth_date"),
    ]

    operations = [
        migrations.RunPython(move_person_identifiers_to_citizenships, noop_reverse),
        migrations.RemoveField(
            model_name="personrecord",
            name="identifier",
        ),
        migrations.RemoveField(
            model_name="personrecord",
            name="number",
        ),
    ]
