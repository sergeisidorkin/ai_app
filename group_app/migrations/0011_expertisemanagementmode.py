from django.db import migrations, models
import django.db.models.deletion


def backfill_management_modes(apps, schema_editor):
    ExpertiseDirection = apps.get_model("policy_app", "ExpertiseDirection")
    ExpertiseManagementMode = apps.get_model("group_app", "ExpertiseManagementMode")
    existing = set(
        ExpertiseManagementMode.objects.values_list("expertise_direction_id", flat=True)
    )
    ExpertiseManagementMode.objects.bulk_create(
        [
            ExpertiseManagementMode(
                expertise_direction_id=direction_id,
                mode="management_company",
            )
            for direction_id in ExpertiseDirection.objects.exclude(pk__in=existing).values_list("pk", flat=True)
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0054_policyexpertspecialty"),
        ("group_app", "0010_set_management_company"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpertiseManagementMode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("management_company", "Управление через УК"),
                            ("separate", "Раздельное управление"),
                        ],
                        default="management_company",
                        max_length=32,
                        verbose_name="Режим",
                    ),
                ),
                (
                    "expertise_direction",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="management_mode",
                        to="policy_app.expertisedirection",
                        verbose_name="Направление экспертизы",
                    ),
                ),
            ],
            options={
                "verbose_name": "Режим управления",
                "verbose_name_plural": "Режим управления",
                "ordering": ["expertise_direction__position", "expertise_direction_id"],
            },
        ),
        migrations.RunPython(backfill_management_modes, migrations.RunPython.noop),
    ]
