from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0018_businessentityrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityIdentifierRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifier_type", models.CharField(max_length=255, verbose_name="Тип идентификатора")),
                ("number", models.CharField(blank=True, default="", max_length=255, verbose_name="Номер")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действителен от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действителен до")),
                ("is_active", models.BooleanField(default=True, verbose_name="Актуален")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business_entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="identifiers", to="classifiers_app.businessentityrecord", verbose_name="ID")),
            ],
            options={
                "verbose_name": "Идентификатор бизнес-сущности",
                "verbose_name_plural": "Реестр идентификаторов",
                "ordering": ["position", "id"],
            },
        ),
    ]
