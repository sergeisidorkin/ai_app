from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("experts_app", "0019_expertcontractdetails_registration_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expertcontractdetails",
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
