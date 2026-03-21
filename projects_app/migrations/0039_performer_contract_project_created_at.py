from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0038_performer_contract_project_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_project_created_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата создания проекта договора"),
        ),
    ]
