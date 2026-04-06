from django.db import migrations


ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def forwards_backfill_legal_address_record_date(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias

    identifier_dates = {
        item.pk: item.record_date
        for item in BusinessEntityIdentifierRecord.objects.using(db_alias)
        .exclude(record_date__isnull=True)
        .only("pk", "record_date")
    }

    for address in LegalEntityRecord.objects.using(db_alias).filter(
        attribute=ATTRIBUTE_LEGAL_ADDRESS,
        record_date__isnull=True,
    ).iterator():
        record_date = None
        if address.identifier_record_id:
            record_date = identifier_dates.get(address.identifier_record_id)
        if record_date is None and address.created_at:
            record_date = address.created_at.date()
        if record_date is not None:
            address.record_date = record_date
            address.save(update_fields=["record_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0039_backfill_identifier_and_address_record_author"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_legal_address_record_date, migrations.RunPython.noop),
    ]
