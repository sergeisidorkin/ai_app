from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0009_proposallegalentity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalObject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "legal_entity_short_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=512,
                        verbose_name="Наименование юрлица (краткое)",
                    ),
                ),
                (
                    "short_name",
                    models.CharField(blank=True, default="", max_length=512, verbose_name="Наименование объекта (краткое)"),
                ),
                ("region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион")),
                ("object_type", models.CharField(blank=True, default="", max_length=255, verbose_name="Тип")),
                ("license", models.CharField(blank=True, default="", max_length=255, verbose_name="Лицензия")),
                ("registration_date", models.DateField(blank=True, null=True, verbose_name="Дата регистрации")),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proposal_objects",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП",
                    ),
                ),
            ],
            options={
                "verbose_name": "Объект ТКП",
                "verbose_name_plural": "Объекты ТКП",
                "ordering": ["position", "id"],
            },
        ),
    ]
