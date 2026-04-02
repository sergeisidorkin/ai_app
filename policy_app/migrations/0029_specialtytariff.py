from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0009_okvcurrency_approval_date_okvcurrency_expiry_date_and_more"),
        ("experts_app", "0013_expertprofile_professional_status"),
        ("group_app", "0006_orgunit_expertise_fk"),
        ("policy_app", "0028_typicalservicecomposition"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecialtyTariff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("specialty_group", models.CharField(blank=True, default="", max_length=255, verbose_name="Группа специальностей")),
                ("daily_rate_tkp_eur", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Дневная ставка оплаты в евро для ТКП")),
                ("daily_rate_ss", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Дневная ставка оплаты для с/с")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "currency",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="specialty_tariffs",
                        to="classifiers_app.okvcurrency",
                        verbose_name="Валюта",
                    ),
                ),
                (
                    "expertise_direction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="specialty_tariffs",
                        to="group_app.orgunit",
                        verbose_name="Направление экспертизы",
                    ),
                ),
                (
                    "specialties",
                    models.ManyToManyField(
                        blank=True,
                        related_name="specialty_tariffs",
                        to="experts_app.expertspecialty",
                        verbose_name="Специальности",
                    ),
                ),
            ],
            options={
                "verbose_name": "Тариф специальностей",
                "verbose_name_plural": "Тарифы специальностей",
                "ordering": ["position", "id"],
            },
        ),
    ]
