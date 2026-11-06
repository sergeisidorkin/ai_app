from django.db import migrations, models
from django.db.models import Max


COORDINATOR_SPECIALTY = "Координатор"


def mark_coordinator_specialty(apps, schema_editor):
    ExpertSpecialty = apps.get_model("experts_app", "ExpertSpecialty")
    specialty = ExpertSpecialty.objects.filter(specialty=COORDINATOR_SPECIALTY).first()
    if specialty is None:
        last_position = ExpertSpecialty.objects.aggregate(value=Max("position"))["value"] or 0
        ExpertSpecialty.objects.create(
            specialty=COORDINATOR_SPECIALTY,
            grants_project_rights=True,
            is_group_owner=True,
            position=last_position + 1,
        )
        return
    if not specialty.grants_project_rights:
        specialty.grants_project_rights = True
        specialty.save(update_fields=["grants_project_rights"])


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0024_alter_expertspecialty_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertspecialty",
            name="grants_project_rights",
            field=models.BooleanField(db_default=False, default=False, verbose_name="Даёт права в проекте"),
        ),
        migrations.RunPython(mark_coordinator_specialty, migrations.RunPython.noop),
    ]
