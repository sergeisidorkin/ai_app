from django.db import migrations, models


def bootstrap_legal_entities(apps, schema_editor):
    WorkVolume = apps.get_model("projects_app", "WorkVolume")
    LegalEntity = apps.get_model("projects_app", "LegalEntity")

    counters = {}
    qs = WorkVolume.objects.select_related("project").order_by("project__position", "position", "id")
    for work in qs:
        pid = work.project_id
        if not pid:
            continue
        counters[pid] = counters.get(pid, 0) + 1
        LegalEntity.objects.create(
            position=counters[pid],
            project_id=pid,
            work_item_id=work.id,
            legal_name=work.asset_name or work.name or "",
            registration_number=work.registration_number,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0011_stage3_term_calc"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalEntity",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID")),
                ("position", models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")),
                ("legal_name", models.CharField(max_length=255, blank=True, verbose_name="Наименование юридического лица")),
                ("registration_number", models.CharField(max_length=100, blank=True, verbose_name="Регистрационный номер")),
                ("project", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="legal_entities", to="projects_app.projectregistration", verbose_name="Проект")),
                ("work_item", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="legal_entities", to="projects_app.workvolume", verbose_name="Наименование актива")),
            ],
            options={
                "ordering": ["project__position", "position", "id"],
                "verbose_name": "Юридическое лицо",
                "verbose_name_plural": "Юридические лица",
            },
        ),
        migrations.RunPython(bootstrap_legal_entities, migrations.RunPython.noop),
    ]