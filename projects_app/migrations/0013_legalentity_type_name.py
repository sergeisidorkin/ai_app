from django.db import migrations, models


def fill_type_name(apps, schema_editor):
    LegalEntity = apps.get_model("projects_app", "LegalEntity")
    WorkVolume = apps.get_model("projects_app", "WorkVolume")
    qs = LegalEntity.objects.select_related("work_item")
    for entity in qs:
        work = entity.work_item
        if not work:
            continue
        entity.work_type = work.type or ""
        entity.work_name = work.name or ""
        entity.save(update_fields=["work_type", "work_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0012_legalentity"),
    ]

    operations = [
        migrations.AddField(
            model_name="legalentity",
            name="work_type",
            field=models.CharField(verbose_name="Тип", max_length=100, blank=True),
        ),
        migrations.AddField(
            model_name="legalentity",
            name="work_name",
            field=models.CharField(verbose_name="Название", max_length=255, blank=True),
        ),
        migrations.RunPython(fill_type_name, migrations.RunPython.noop),
    ]