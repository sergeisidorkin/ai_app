import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects_app", "0036_performer_contract_project_created"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractProjectTargetFolder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder_name", models.CharField(max_length=255)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="contract_project_target_folder",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Целевая папка проекта договора",
                "verbose_name_plural": "Целевые папки проекта договора",
            },
        ),
    ]
