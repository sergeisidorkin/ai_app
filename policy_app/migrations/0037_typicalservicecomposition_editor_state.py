from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0036_typicalserviceterm"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalservicecomposition",
            name="service_composition_editor_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Состав услуг: состояние редактора",
            ),
        ),
    ]
