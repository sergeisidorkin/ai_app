from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0016_backfill_person_residence_addresses"),
    ]

    operations = [
        migrations.AddField(
            model_name="personrecord",
            name="full_name_genitive",
            field=models.CharField(
                blank=True,
                default="",
                max_length=512,
                verbose_name="ФИО (полное) в родительном падеже",
            ),
        ),
    ]
