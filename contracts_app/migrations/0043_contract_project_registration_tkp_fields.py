from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0042_contractprojectregistration_source_data_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="proposal_project_name",
            field=models.TextField(blank=True, default="", verbose_name="Наименование ТКП (проекта)"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="purpose",
            field=models.TextField(blank=True, default="", verbose_name="Цель оказания услуг"),
        ),
    ]
