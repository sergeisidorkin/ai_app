from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0045_businessentityidentifierrecord_registration_region_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityrecord",
            name="record_author",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи"),
        ),
        migrations.AddField(
            model_name="businessentityrecord",
            name="source",
            field=models.TextField(blank=True, default="", verbose_name="Источник"),
        ),
    ]
