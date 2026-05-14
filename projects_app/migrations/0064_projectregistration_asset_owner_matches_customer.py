from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0063_projectregistration_asset_owner_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="asset_owner_matches_customer",
            field=models.BooleanField(default=True, verbose_name="Совпадает с Заказчиком"),
        ),
    ]
