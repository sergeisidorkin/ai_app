from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0010_proposalobject"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalCommercialOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("specialist", models.CharField(blank=True, default="", max_length=255, verbose_name="Специалист")),
                ("job_title", models.CharField(blank=True, default="", max_length=255, verbose_name="Должность")),
                (
                    "professional_status",
                    models.CharField(blank=True, default="", max_length=255, verbose_name="Профессиональный статус"),
                ),
                (
                    "rate_eur_per_day",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        validators=[MinValueValidator(0)],
                        verbose_name="Ставка, евро / день",
                    ),
                ),
                ("asset_day_counts", models.JSONField(blank=True, default=list, verbose_name="Количество дней")),
                (
                    "total_eur_without_vat",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=15,
                        null=True,
                        validators=[MinValueValidator(0)],
                        verbose_name="Итого, евро без НДС",
                    ),
                ),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="commercial_offers",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП",
                    ),
                ),
            ],
            options={
                "verbose_name": "Коммерческое предложение ТКП",
                "verbose_name_plural": "Коммерческие предложения ТКП",
                "ordering": ["position", "id"],
            },
        ),
    ]
