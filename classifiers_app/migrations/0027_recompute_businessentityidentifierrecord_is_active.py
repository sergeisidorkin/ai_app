from django.db import migrations


def recompute_business_entity_identifier_is_active(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    BusinessEntityIdentifierRecord.objects.filter(valid_to__isnull=True).update(is_active=True)
    BusinessEntityIdentifierRecord.objects.filter(valid_to__isnull=False).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0026_fill_businessentityrecord_record_date"),
    ]

    operations = [
        migrations.RunPython(recompute_business_entity_identifier_is_active, migrations.RunPython.noop),
    ]
