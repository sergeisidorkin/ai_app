from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0011_add_corr_bank_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofile",
            name="yandex_mail",
            field=models.CharField(
                blank=True, default="", max_length=255, verbose_name="Яндекс Почта"
            ),
        ),
    ]
