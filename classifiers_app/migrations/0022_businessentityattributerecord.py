from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0021_businessentityrelationrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityAttributeRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attribute_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование атрибута")),
                ("subsection_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование подраздела")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Атрибут",
                "verbose_name_plural": "Реестр атрибутов",
                "ordering": ["position", "id"],
            },
        ),
    ]
