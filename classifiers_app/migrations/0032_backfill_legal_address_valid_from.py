from django.db import migrations


ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def forwards_backfill_legal_address_valid_from(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias

    for identifier_record in BusinessEntityIdentifierRecord.objects.using(db_alias).exclude(valid_from__isnull=True):
        LegalEntityRecord.objects.using(db_alias).filter(
            identifier_record_id=identifier_record.pk,
            attribute=ATTRIBUTE_LEGAL_ADDRESS,
            valid_from__isnull=True,
        ).update(valid_from=identifier_record.valid_from)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0031_backfill_identifier_legal_addresses"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_legal_address_valid_from, migrations.RunPython.noop),
    ]
