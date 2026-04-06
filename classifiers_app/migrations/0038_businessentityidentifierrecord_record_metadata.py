from django.db import migrations, models


def forwards_fill_identifier_record_metadata(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    db_alias = schema_editor.connection.alias

    for item in BusinessEntityIdentifierRecord.objects.using(db_alias).filter(record_date__isnull=True).iterator():
        item.record_date = item.created_at.date() if item.created_at else None
        item.save(update_fields=["record_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0037_add_period_exclusion_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="record_author",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи"),
        ),
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="record_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата записи"),
        ),
        migrations.RunPython(forwards_fill_identifier_record_metadata, migrations.RunPython.noop),
    ]
