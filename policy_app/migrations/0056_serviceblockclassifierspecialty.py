from django.db import migrations, models
import django.db.models.deletion


def backfill_executors(apps, schema_editor):
    from policy_app.service_block_link import backfill_service_block_executors

    backfill_service_block_executors(
        apps.get_model("policy_app", "TypicalSection"),
        apps.get_model("policy_app", "TypicalSectionSpecialty"),
        apps.get_model("policy_app", "ServiceBlockClassifierSpecialty"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0024_alter_expertspecialty_options"),
        ("policy_app", "0055_typicalsection_service_block"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceBlockClassifierSpecialty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(default=1, verbose_name="Ранг")),
                (
                    "classifier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ranked_specialties",
                        to="policy_app.serviceblockclassifier",
                    ),
                ),
                (
                    "specialty",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_block_classifier_links",
                        to="experts_app.expertspecialty",
                    ),
                ),
            ],
            options={
                "verbose_name": "Специальность блока услуг",
                "verbose_name_plural": "Специальности блока услуг",
                "ordering": ["rank", "id"],
                "unique_together": {("classifier", "specialty")},
            },
        ),
        migrations.RunPython(backfill_executors, migrations.RunPython.noop),
    ]
