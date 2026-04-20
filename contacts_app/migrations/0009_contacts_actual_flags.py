from django.db import migrations, models


def backfill_contact_actual_flags(apps, schema_editor):
    PositionRecord = apps.get_model("contacts_app", "PositionRecord")
    PhoneRecord = apps.get_model("contacts_app", "PhoneRecord")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")

    PositionRecord.objects.filter(valid_to__isnull=True).update(is_active=True)
    PositionRecord.objects.filter(valid_to__isnull=False).update(is_active=False)

    PhoneRecord.objects.filter(valid_to__isnull=True).update(is_active=True)
    PhoneRecord.objects.filter(valid_to__isnull=False).update(is_active=False)

    CitizenshipRecord.objects.filter(valid_to__isnull=True).update(is_active=True)
    CitizenshipRecord.objects.filter(valid_to__isnull=False).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("contacts_app", "0008_phonerecord_region"),
    ]

    operations = [
        migrations.AddField(
            model_name="citizenshiprecord",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Актуален"),
        ),
        migrations.AddField(
            model_name="phonerecord",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Актуален"),
        ),
        migrations.AddField(
            model_name="positionrecord",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Актуален"),
        ),
        migrations.RunPython(backfill_contact_actual_flags, migrations.RunPython.noop),
    ]
