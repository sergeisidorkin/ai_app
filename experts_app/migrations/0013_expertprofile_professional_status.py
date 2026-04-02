from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0012_expertprofile_yandex_mail"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofile",
            name="professional_status",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Профессиональный статус",
            ),
        ),
    ]
