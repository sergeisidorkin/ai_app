from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0018_personrecord_gender"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personrecord",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("male", "мужской"), ("female", "женский")],
                default="",
                max_length=10,
                verbose_name="Пол",
            ),
        ),
    ]
