from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0064_projectregistration_asset_owner_matches_customer"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="evaluation_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата оценки"),
        ),
    ]
