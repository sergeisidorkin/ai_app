from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0002_contractvariable"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractvariable",
            name="source_section",
            field=models.CharField("Раздел", max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="contractvariable",
            name="source_table",
            field=models.CharField("Таблица", max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="contractvariable",
            name="source_column",
            field=models.CharField("Столбец", max_length=100, blank=True, default=""),
        ),
    ]
