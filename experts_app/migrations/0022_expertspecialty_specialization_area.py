from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("experts_app", "0021_expertprofilespecialty_contact_record"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertspecialty",
            name="specialization_area",
            field=models.CharField(
                blank=True,
                default="",
                max_length=512,
                verbose_name="Область специализации",
            ),
        ),
    ]
