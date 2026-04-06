from django.db import migrations, models


def forwards_backfill_reorganization_event_uid(apps, schema_editor):
    BusinessEntityRelationRecord = apps.get_model("classifiers_app", "BusinessEntityRelationRecord")
    db_alias = schema_editor.connection.alias

    for item in BusinessEntityRelationRecord.objects.using(db_alias).filter(reorganization_event_uid="").only("pk"):
        item.reorganization_event_uid = f"{item.pk:05d}-REO"
        item.save(update_fields=["reorganization_event_uid"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0040_backfill_legal_address_record_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityrelationrecord",
            name="reorganization_event_uid",
            field=models.CharField(blank=True, db_index=True, default="", max_length=32, verbose_name="ID-REO"),
        ),
        migrations.RunPython(forwards_backfill_reorganization_event_uid, migrations.RunPython.noop),
    ]
