from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0134_performer_display_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="PerformerSystemGroupState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_number", models.PositiveIntegerField(db_index=True, verbose_name="Номер проекта")),
                ("group_label", models.CharField(blank=True, default="", max_length=64, verbose_name="Группа")),
                ("specialty_name", models.CharField(max_length=255, verbose_name="Специальность")),
                (
                    "display_group_id",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Визуальная группа"),
                ),
                ("split_by_user", models.BooleanField(default=False, verbose_name="Разъединено пользователем")),
            ],
            options={
                "verbose_name": "Группа системной специальности",
                "verbose_name_plural": "Группы системных специальностей",
            },
        ),
        migrations.AddConstraint(
            model_name="performersystemgroupstate",
            constraint=models.UniqueConstraint(
                fields=("project_number", "group_label", "specialty_name"),
                name="ux_performer_system_group_state",
            ),
        ),
    ]
