from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0024_backfill_business_entities_from_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityrecord",
            name="record_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата записи"),
        ),
    ]
