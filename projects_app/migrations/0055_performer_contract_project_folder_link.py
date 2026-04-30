from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0054_projectregistration_project_manager_prs_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_folder_link",
            field=models.URLField(blank=True, default="", verbose_name="Ссылка на папку проекта договора"),
        ),
    ]
