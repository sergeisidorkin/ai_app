from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0037_contractprojecttargetfolder"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_link",
            field=models.URLField(blank=True, default="", verbose_name="Ссылка на проект договора"),
        ),
    ]
