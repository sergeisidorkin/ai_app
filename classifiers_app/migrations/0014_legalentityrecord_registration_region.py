from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0013_legalentityrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="legalentityrecord",
            name="registration_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион"),
        ),
    ]
