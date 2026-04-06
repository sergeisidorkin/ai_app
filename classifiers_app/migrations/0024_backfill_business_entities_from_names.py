from django.db import migrations


ATTRIBUTE_NAME = "Наименование"


def forwards_backfill_business_entities_from_names(apps, schema_editor):
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")
    BusinessEntityRecord = apps.get_model("classifiers_app", "BusinessEntityRecord")
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")

    db_alias = schema_editor.connection.alias

    next_ber_position = (
        BusinessEntityRecord.objects.using(db_alias).order_by("-position").values_list("position", flat=True).first() or 0
    ) + 1
    next_bei_position = (
        BusinessEntityIdentifierRecord.objects.using(db_alias).order_by("-position").values_list("position", flat=True).first() or 0
    ) + 1

    records = LegalEntityRecord.objects.using(db_alias).filter(
        attribute=ATTRIBUTE_NAME,
        identifier_record_id__isnull=True,
    ).order_by("position", "id")

    for record in records.iterator():
        business_entity = BusinessEntityRecord.objects.using(db_alias).create(
            name=record.short_name or record.full_name or "",
            comment="",
            position=next_ber_position,
        )
        next_ber_position += 1

        identifier_record = BusinessEntityIdentifierRecord.objects.using(db_alias).create(
            business_entity_id=business_entity.id,
            identifier_type=record.identifier or "",
            number=record.registration_number or "",
            valid_from=record.registration_date,
            valid_to=None,
            is_active=True,
            position=next_bei_position,
        )
        next_bei_position += 1

        LegalEntityRecord.objects.using(db_alias).filter(pk=record.pk).update(identifier_record_id=identifier_record.id)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0023_unify_legal_entities_and_addresses"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_business_entities_from_names, migrations.RunPython.noop),
    ]
