from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0049_numcaprecord_gar_territory_numcaprecord_inn"),
    ]

    operations = [
        migrations.AddField(
            model_name="oksmcountry",
            name="short_name_genitive",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование (краткое) в род. пад."),
        ),
    ]
