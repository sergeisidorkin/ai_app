from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0008_proposalasset"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalLegalEntity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "asset_short_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=512,
                        verbose_name="Наименование актива (краткое)",
                    ),
                ),
                ("short_name", models.CharField(blank=True, default="", max_length=512, verbose_name="Наименование (краткое)")),
                ("identifier", models.CharField(blank=True, default="", max_length=255, verbose_name="Идентификатор")),
                (
                    "registration_number",
                    models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрационный номер"),
                ),
                ("registration_date", models.DateField(blank=True, null=True, verbose_name="Дата регистрации")),
                (
                    "country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proposal_legal_entities",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="legal_entities",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП",
                    ),
                ),
            ],
            options={
                "verbose_name": "Юрлицо ТКП",
                "verbose_name_plural": "Юрлица ТКП",
                "ordering": ["position", "id"],
            },
        ),
    ]
