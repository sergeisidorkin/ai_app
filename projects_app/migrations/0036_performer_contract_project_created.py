from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0035_add_performer_participation_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_created",
            field=models.BooleanField(default=False, verbose_name="Проект договора создан"),
        ),
    ]
