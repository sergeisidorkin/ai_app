from django.db import migrations
from django.utils import timezone


def backfill_residence_address_records(apps, schema_editor):
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    ResidenceAddressRecord = apps.get_model("contacts_app", "ResidenceAddressRecord")

    next_position = ResidenceAddressRecord.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0
    today = timezone.localdate()

    for person in PersonRecord.objects.order_by("position", "id").iterator():
        if ResidenceAddressRecord.objects.filter(person_id=person.pk).exists():
            continue
        next_position += 1
        ResidenceAddressRecord.objects.create(
            person_id=person.pk,
            country_id=person.citizenship_id,
            region="",
            postal_code="",
            locality="",
            street="",
            building="",
            premise="",
            premise_part="",
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
        ("contacts_app", "0015_residenceaddressrecord"),
    ]

    operations = [
        migrations.RunPython(backfill_residence_address_records, noop_reverse),
    ]
