from django.db import migrations
from django.utils import timezone


def backfill_email_valid_from(apps, schema_editor):
    EmailRecord = apps.get_model("contacts_app", "EmailRecord")
    today = timezone.localdate()

    for item in EmailRecord.objects.filter(valid_from__isnull=True).iterator():
        item.valid_from = item.record_date or today
        item.save(update_fields=["valid_from"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0011_backfill_person_emails"),
    ]

    operations = [
        migrations.RunPython(backfill_email_valid_from, noop_reverse),
    ]
