from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0016_russianfederationsubjectcode_source_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="russianfederationsubjectcode",
            name="source",
            field=models.TextField(blank=True, default="", verbose_name="Источник"),
        ),
    ]
