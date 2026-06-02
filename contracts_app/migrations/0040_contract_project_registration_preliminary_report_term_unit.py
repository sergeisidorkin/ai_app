from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0039_contract_project_registration_contract_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="preliminary_report_term_unit",
            field=models.CharField(
                choices=[
                    ("months", "мес."),
                    ("days", "дн."),
                    ("weeks", "нед."),
                ],
                default="months",
                max_length=10,
                verbose_name="Единица срока подготовки Предварительного отчёта",
            ),
        ),
    ]
