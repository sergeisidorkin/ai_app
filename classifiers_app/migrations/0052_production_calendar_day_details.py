from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0051_productioncalendarday"),
    ]

    operations = [
        migrations.AddField(
            model_name="productioncalendarday",
            name="is_shortened_day",
            field=models.BooleanField(default=False, verbose_name="Сокращенный день"),
        ),
        migrations.AddField(
            model_name="productioncalendarday",
            name="working_hours",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=4,
                null=True,
                verbose_name="Рабочие часы",
            ),
        ),
        migrations.AddField(
            model_name="productioncalendarday",
            name="source_document",
            field=models.TextField(blank=True, default="", verbose_name="Документ-основание"),
        ),
    ]
