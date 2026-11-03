from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0125_service_scope_key_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="terms_columns_json",
            field=models.JSONField(blank=True, default=dict, verbose_name="Столбцы сроков"),
        ),
    ]
