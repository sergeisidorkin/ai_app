from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0055_proposalcommercialoffer_code_merge_without_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="preliminary_report_term_unit",
            field=models.CharField(
                choices=[("months", "мес."), ("days", "дн."), ("weeks", "нед.")],
                default="months",
                max_length=10,
                verbose_name="Единица срока подготовки Предварительного отчёта",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="final_report_term_unit",
            field=models.CharField(
                choices=[("days", "дн."), ("weeks", "нед."), ("months", "мес.")],
                default="weeks",
                max_length=10,
                verbose_name="Единица срока подготовки Итогового отчёта",
            ),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="service_term_months",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0)],
                verbose_name="Предварительный отчёт",
            ),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="final_report_term_weeks",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0)],
                verbose_name="Итоговый отчёт",
            ),
        ),
    ]
