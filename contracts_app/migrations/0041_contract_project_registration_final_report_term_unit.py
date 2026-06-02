from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0040_contract_project_registration_preliminary_report_term_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="final_report_term_unit",
            field=models.CharField(
                choices=[
                    ("days", "дн."),
                    ("weeks", "нед."),
                    ("months", "мес."),
                ],
                default="weeks",
                max_length=10,
                verbose_name="Единица срока подготовки Итогового отчёта",
            ),
        ),
    ]
