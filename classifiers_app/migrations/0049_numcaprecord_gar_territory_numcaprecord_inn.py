from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0048_numcaprecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="numcaprecord",
            name="gar_territory",
            field=models.TextField(blank=True, default="", verbose_name="Территория ГАР"),
        ),
        migrations.AddField(
            model_name="numcaprecord",
            name="inn",
            field=models.CharField(blank=True, default="", max_length=16, verbose_name="ИНН"),
        ),
    ]
