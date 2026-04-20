from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0047_physicalentityidentifier"),
    ]

    operations = [
        migrations.CreateModel(
            name="NumcapRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=5, verbose_name="Код зоны")),
                ("begin", models.CharField(max_length=7, verbose_name="Начало диапазона")),
                ("end", models.CharField(max_length=7, verbose_name="Конец диапазона")),
                ("capacity", models.CharField(blank=True, default="", max_length=16, verbose_name="Емкость")),
                ("operator", models.CharField(blank=True, default="", max_length=255, verbose_name="Оператор")),
                ("region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Запись numcap",
                "verbose_name_plural": "Классификатор numcap",
                "ordering": ["position", "id"],
            },
        ),
    ]
