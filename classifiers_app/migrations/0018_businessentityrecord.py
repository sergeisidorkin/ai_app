from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0017_alter_russianfederationsubjectcode_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=512, verbose_name="Наименование")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Бизнес-сущность",
                "verbose_name_plural": "Реестр бизнес-сущностей",
                "ordering": ["position", "id"],
            },
        ),
    ]
