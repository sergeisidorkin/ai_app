from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0015_russianfederationsubjectcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="russianfederationsubjectcode",
            name="source",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="Источник"),
        ),
        migrations.AlterField(
            model_name="russianfederationsubjectcode",
            name="fns_code",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Код ФНС России"),
        ),
        migrations.AlterModelOptions(
            name="russianfederationsubjectcode",
            options={
                "ordering": ["position", "id"],
                "verbose_name": "Код субъекта Российской Федерации",
                "verbose_name_plural": "Коды ФНС России для субъектов Российской Федерации",
            },
        ),
    ]
