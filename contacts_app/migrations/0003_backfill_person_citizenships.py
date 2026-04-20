from django.db import migrations
from django.utils import timezone


def backfill_person_citizenships(apps, schema_editor):
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")

    next_position = CitizenshipRecord.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0
    today = timezone.localdate()

    for person in PersonRecord.objects.order_by("position", "id").iterator():
        if CitizenshipRecord.objects.filter(person_id=person.pk).exists():
            continue
        next_position += 1
        CitizenshipRecord.objects.create(
            person_id=person.pk,
            country_id=person.citizenship_id,
            status="",
            identifier=person.identifier or "",
            number=person.number or "",
            valid_from=None,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_position,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0002_citizenshiprecord"),
    ]

    operations = [
        migrations.RunPython(backfill_person_citizenships, noop_reverse),
    ]
