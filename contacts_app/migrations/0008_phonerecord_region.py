from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contacts_app", "0007_phonerecord_phone_type_extension"),
    ]

    operations = [
        migrations.AddField(
            model_name="phonerecord",
            name="region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион"),
        ),
    ]
