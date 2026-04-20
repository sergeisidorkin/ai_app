from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contacts_app", "0006_phonerecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="phonerecord",
            name="extension",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Добавочный номер"),
        ),
        migrations.AddField(
            model_name="phonerecord",
            name="phone_type",
            field=models.CharField(
                choices=[("mobile", "Мобильный"), ("landline", "Стационарный")],
                default="mobile",
                max_length=16,
                verbose_name="Тип связи",
            ),
        ),
    ]
