from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0039_performer_contract_project_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата договора"),
        ),
    ]
