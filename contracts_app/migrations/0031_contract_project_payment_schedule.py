import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0030_contract_project_registration"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="advance_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Размер предоплаты в процентах",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="advance_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок предоплаты в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="evaluation_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата оценки"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="final_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата Итогового отчёта"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="final_report_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Размер оплаты Итогового отчёта в процентах",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="final_report_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок оплаты Итогового отчёта в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="final_report_term_weeks",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Срок подготовки Итогового отчёта, нед.",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="preliminary_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата Предварительного отчёта"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="preliminary_report_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Размер оплаты Предварительного отчёта в процентах",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="preliminary_report_term_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Срок оплаты Предварительного отчёта в календарных днях",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_term_months",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Срок подготовки Предварительного отчёта, мес.",
            ),
        ),
    ]
