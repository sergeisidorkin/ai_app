from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0013_legalentityrecord"),
        ("proposals_app", "0007_update_country_full_name_variable"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
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
                        related_name="proposal_assets",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assets",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП",
                    ),
                ),
            ],
            options={
                "verbose_name": "Актив ТКП",
                "verbose_name_plural": "Активы ТКП",
                "ordering": ["position", "id"],
            },
        ),
    ]
