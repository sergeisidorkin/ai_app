from django.db import migrations


def recompute_legal_entity_record_is_active(apps, schema_editor):
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")
    LegalEntityRecord.objects.filter(valid_to__isnull=True).update(is_active=True)
    LegalEntityRecord.objects.filter(valid_to__isnull=False).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0027_recompute_businessentityidentifierrecord_is_active"),
    ]

    operations = [
        migrations.RunPython(recompute_legal_entity_record_is_active, migrations.RunPython.noop),
    ]
