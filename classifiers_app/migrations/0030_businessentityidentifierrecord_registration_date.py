from django.db import migrations, models


def forwards_fill_identifier_registration_date(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    for identifier_record in BusinessEntityIdentifierRecord.objects.all().iterator():
        name_record = (
            LegalEntityRecord.objects.filter(
                identifier_record_id=identifier_record.pk,
                attribute="Наименование",
            )
            .order_by("position", "id")
            .first()
        )
        if not name_record:
            continue
        identifier_record.registration_date = name_record.registration_date
        identifier_record.save(update_fields=["registration_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0029_businessentityidentifierrecord_registration_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="registration_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата регистрации"),
        ),
        migrations.RunPython(forwards_fill_identifier_registration_date, migrations.RunPython.noop),
    ]
