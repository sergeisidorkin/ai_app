from django.db import migrations
from django.db.models import Max


ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def forwards_backfill_identifier_legal_addresses(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias
    next_position = (
        LegalEntityRecord.objects.using(db_alias).aggregate(mx=Max("position")).get("mx") or 0
    ) + 1

    for identifier_record in BusinessEntityIdentifierRecord.objects.using(db_alias).order_by("position", "id"):
        address_record = (
            LegalEntityRecord.objects.using(db_alias)
            .filter(
                identifier_record_id=identifier_record.pk,
                attribute=ATTRIBUTE_LEGAL_ADDRESS,
            )
            .order_by("position", "id")
            .first()
        )

        if address_record is None:
            LegalEntityRecord.objects.using(db_alias).create(
                attribute=ATTRIBUTE_LEGAL_ADDRESS,
                short_name="",
                full_name="",
                identifier="",
                registration_number="",
                registration_date=None,
                identifier_record_id=identifier_record.pk,
                registration_country_id=identifier_record.registration_country_id,
                registration_region=identifier_record.registration_region or "",
                record_date=None,
                record_author="",
                name_received_date=None,
                name_changed_date=None,
                postal_code="",
                municipality="",
                settlement="",
                locality="",
                district="",
                street="",
                building="",
                premise="",
                premise_part="",
                valid_from=None,
                valid_to=None,
                is_active=True,
                position=next_position,
            )
            next_position += 1
            continue

        update_fields = []
        if not address_record.registration_country_id and identifier_record.registration_country_id:
            address_record.registration_country_id = identifier_record.registration_country_id
            update_fields.append("registration_country")
        if not (address_record.registration_region or "") and (identifier_record.registration_region or ""):
            address_record.registration_region = identifier_record.registration_region or ""
            update_fields.append("registration_region")
        if update_fields:
            update_fields.append("updated_at")
            address_record.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0030_businessentityidentifierrecord_registration_date"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_identifier_legal_addresses, migrations.RunPython.noop),
    ]
