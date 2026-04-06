from datetime import date

from django.db import migrations


def fill_business_entity_record_date(apps, schema_editor):
    BusinessEntityRecord = apps.get_model("classifiers_app", "BusinessEntityRecord")
    BusinessEntityRecord.objects.filter(record_date__isnull=True).update(record_date=date.today())


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0025_businessentityrecord_record_date"),
    ]

    operations = [
        migrations.RunPython(fill_business_entity_record_date, migrations.RunPython.noop),
    ]
