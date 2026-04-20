from django.db import migrations
from django.utils import timezone


def backfill_email_records(apps, schema_editor):
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    EmailRecord = apps.get_model("contacts_app", "EmailRecord")

    next_position = EmailRecord.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0
    today = timezone.localdate()

    for person in PersonRecord.objects.order_by("position", "id").iterator():
        if EmailRecord.objects.filter(person_id=person.pk).exists():
            continue
        next_position += 1
        EmailRecord.objects.create(
            person_id=person.pk,
            email="",
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
        ("contacts_app", "0010_emailrecord"),
    ]

    operations = [
        migrations.RunPython(backfill_email_records, noop_reverse),
    ]
