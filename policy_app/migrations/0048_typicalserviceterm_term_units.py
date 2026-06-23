from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0047_expertisedirection_specialization_area"),
    ]

    operations = [
        migrations.AlterField(
            model_name="typicalserviceterm",
            name="source_data_weeks",
            field=models.DecimalField(
                decimal_places=1,
                default=0,
                max_digits=6,
                validators=[MinValueValidator(0)],
                verbose_name="Сроки предоставления исходных данных",
            ),
        ),
        migrations.AlterField(
            model_name="typicalserviceterm",
            name="preliminary_report_months",
            field=models.DecimalField(
                decimal_places=1,
                default=0,
                max_digits=6,
                validators=[MinValueValidator(0)],
                verbose_name="Срок подготовки Предварительного отчёта",
            ),
        ),
        migrations.AlterField(
            model_name="typicalserviceterm",
            name="final_report_weeks",
            field=models.DecimalField(
                decimal_places=1,
                default=0,
                max_digits=6,
                validators=[MinValueValidator(0)],
                verbose_name="Срок подготовки Итогового отчёта",
            ),
        ),
        migrations.AddField(
            model_name="typicalserviceterm",
            name="source_data_term_unit",
            field=models.CharField(
                choices=[("days", "дн."), ("weeks", "нед."), ("months", "мес.")],
                default="weeks",
                max_length=10,
                verbose_name="Единица срока предоставления исходных данных",
            ),
        ),
        migrations.AddField(
            model_name="typicalserviceterm",
            name="preliminary_report_term_unit",
            field=models.CharField(
                choices=[("days", "дн."), ("weeks", "нед."), ("months", "мес.")],
                default="months",
                max_length=10,
                verbose_name="Единица срока подготовки Предварительного отчёта",
            ),
        ),
        migrations.AddField(
            model_name="typicalserviceterm",
            name="final_report_term_unit",
            field=models.CharField(
                choices=[("days", "дн."), ("weeks", "нед."), ("months", "мес.")],
                default="weeks",
                max_length=10,
                verbose_name="Единица срока подготовки Итогового отчёта",
            ),
        ),
    ]
