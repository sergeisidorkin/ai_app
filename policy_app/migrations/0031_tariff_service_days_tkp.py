from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0030_specialtytariff_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="tariff",
            name="service_days_tkp",
            field=models.PositiveIntegerField(default=0, verbose_name="Объем услуг в днях для ТКП"),
        ),
    ]
