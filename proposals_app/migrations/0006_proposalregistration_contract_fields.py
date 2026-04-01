from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0013_legalentityrecord"),
        ("proposals_app", "0005_proposalvariable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="advance_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
                verbose_name="Размер предоплаты в процентах",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="advance_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок предоплаты в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="currency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_registrations",
                to="classifiers_app.okvcurrency",
                verbose_name="Валюта",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="evaluation_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата оценки"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="final_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата итогового отчёта"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="final_report_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
                verbose_name="Размер оплаты Итогового отчёта в процентах",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="final_report_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок оплаты Итогового отчёта в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="preliminary_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата предварительного отчёта"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="preliminary_report_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
                verbose_name="Размер оплаты Предварительного отчёта в процентах",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="preliminary_report_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок оплаты Предварительного отчёта в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="purpose",
            field=models.TextField(blank=True, default="", verbose_name="Цель оказания услуг"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="report_languages",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Языки отчёта"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="service_composition",
            field=models.TextField(blank=True, default="", verbose_name="Состав услуг"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="service_cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=15,
                null=True,
                validators=[MinValueValidator(0)],
                verbose_name="Стоимость услуг",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="service_term_months",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0)],
                verbose_name="Срок оказания услуг, мес.",
            ),
        ),
    ]
