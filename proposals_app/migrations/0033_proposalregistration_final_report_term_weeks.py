from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0032_seed_actives_name_list_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="final_report_term_weeks",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0)],
                verbose_name="Срок подготовки Итогового отчёта, нед.",
            ),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="final_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата Итогового отчёта"),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="preliminary_report_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата Предварительного отчёта"),
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
                verbose_name="Срок подготовки Предварительного отчёта, мес.",
            ),
        ),
    ]
