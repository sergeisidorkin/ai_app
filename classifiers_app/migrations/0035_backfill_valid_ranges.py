from django.db import migrations
from django.db.backends.postgresql.psycopg_any import DateRange


ATTRIBUTE_NAME = "Наименование"


def _closed_date_range(valid_from, valid_to):
    return DateRange(valid_from, valid_to, "[]")


def _half_open_date_range(valid_from, valid_to):
    return DateRange(valid_from, valid_to, "[)")


def forwards_backfill_valid_ranges(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")

    db_alias = schema_editor.connection.alias

    for item in BusinessEntityIdentifierRecord.objects.using(db_alias).all().iterator():
        item.valid_range = _closed_date_range(item.valid_from, item.valid_to)
        item.is_active = item.valid_to is None
        item.save(update_fields=["valid_range", "is_active"])

    for item in LegalEntityRecord.objects.using(db_alias).all().iterator():
        if item.attribute == ATTRIBUTE_NAME:
            item.valid_from = item.name_received_date
            item.valid_to = item.name_changed_date
            item.valid_range = _half_open_date_range(item.name_received_date, item.name_changed_date)
            item.is_active = item.name_changed_date is None
            update_fields = ["valid_from", "valid_to", "valid_range", "is_active"]
        else:
            item.valid_range = _closed_date_range(item.valid_from, item.valid_to)
            item.is_active = item.valid_to is None
            update_fields = ["valid_range", "is_active"]
        item.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0034_add_valid_range_fields"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_valid_ranges, migrations.RunPython.noop),
    ]
