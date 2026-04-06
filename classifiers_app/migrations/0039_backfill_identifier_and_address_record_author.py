from django.db import migrations


ATTRIBUTE_NAME = "Наименование"
ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def _latest_non_empty_author(queryset):
    candidate = None
    for item in queryset.iterator():
        if (item.record_author or "").strip():
            candidate = item
    return (candidate.record_author or "").strip() if candidate else ""


def forwards_backfill_record_author(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias

    for identifier in BusinessEntityIdentifierRecord.objects.using(db_alias).all().iterator():
        if (identifier.record_author or "").strip():
            continue
        author = _latest_non_empty_author(
            LegalEntityRecord.objects.using(db_alias)
            .filter(identifier_record_id=identifier.pk, attribute=ATTRIBUTE_NAME)
            .order_by("record_date", "id")
        )
        if not author:
            author = _latest_non_empty_author(
                LegalEntityRecord.objects.using(db_alias)
                .filter(identifier_record_id=identifier.pk)
                .order_by("record_date", "id")
            )
        if author:
            identifier.record_author = author
            identifier.save(update_fields=["record_author"])

    for address in LegalEntityRecord.objects.using(db_alias).filter(attribute=ATTRIBUTE_LEGAL_ADDRESS).iterator():
        if (address.record_author or "").strip():
            continue
        author = ""
        if address.identifier_record_id:
            identifier = (
                BusinessEntityIdentifierRecord.objects.using(db_alias)
                .filter(pk=address.identifier_record_id)
                .only("record_author")
                .first()
            )
            if identifier and (identifier.record_author or "").strip():
                author = identifier.record_author.strip()
        if not author and address.identifier_record_id:
            author = _latest_non_empty_author(
                LegalEntityRecord.objects.using(db_alias)
                .filter(identifier_record_id=address.identifier_record_id, attribute=ATTRIBUTE_NAME)
                .order_by("record_date", "id")
            )
        if not author and address.identifier_record_id:
            author = _latest_non_empty_author(
                LegalEntityRecord.objects.using(db_alias)
                .filter(identifier_record_id=address.identifier_record_id)
                .exclude(pk=address.pk)
                .order_by("record_date", "id")
            )
        if author:
            address.record_author = author
            address.save(update_fields=["record_author"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0038_businessentityidentifierrecord_record_metadata"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_record_author, migrations.RunPython.noop),
    ]
