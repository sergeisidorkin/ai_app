from django.db import migrations, models
import django.db.models.deletion


def forwards_fill_identifier_registration_fields(apps, schema_editor):
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
        identifier_record.registration_country_id = name_record.registration_country_id
        identifier_record.registration_region = name_record.registration_region or ""
        identifier_record.registration_code = ""
        if name_record.registration_country_id:
            country = getattr(name_record, "registration_country", None)
            identifier_record.registration_code = getattr(country, "code", "") or ""
        identifier_record.save(update_fields=["registration_country", "registration_region", "registration_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0028_recompute_legalentityrecord_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="registration_code",
            field=models.CharField(blank=True, default="", max_length=16, verbose_name="Код"),
        ),
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="registration_country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="business_entity_identifier_records",
                to="classifiers_app.oksmcountry",
                verbose_name="Страна регистрации",
            ),
        ),
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="registration_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион"),
        ),
        migrations.RunPython(forwards_fill_identifier_registration_fields, migrations.RunPython.noop),
    ]
