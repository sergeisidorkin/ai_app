from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0046_typicalsection_is_system_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertisedirection",
            name="specialization_area",
            field=models.CharField(
                blank=True,
                default="",
                max_length=512,
                verbose_name="Область специализации",
            ),
        ),
    ]
