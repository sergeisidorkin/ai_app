from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0017_personrecord_full_name_genitive"),
    ]

    operations = [
        migrations.AddField(
            model_name="personrecord",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("male", "Мужской"), ("female", "Женский")],
                default="",
                max_length=10,
                verbose_name="Пол",
            ),
        ),
    ]
