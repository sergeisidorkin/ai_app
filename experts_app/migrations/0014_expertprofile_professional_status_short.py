from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0013_expertprofile_professional_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofile",
            name="professional_status_short",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Профессиональный статус (кратко)",
            ),
        ),
    ]
