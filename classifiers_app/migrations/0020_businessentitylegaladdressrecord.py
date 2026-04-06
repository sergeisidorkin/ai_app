from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0019_businessentityidentifierrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityLegalAddressRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион")),
                ("postal_code", models.CharField(blank=True, default="", max_length=32, verbose_name="Индекс")),
                ("municipality", models.CharField(blank=True, default="", max_length=255, verbose_name="Муниципальное образование")),
                ("settlement", models.CharField(blank=True, default="", max_length=255, verbose_name="Поселение")),
                ("locality", models.CharField(blank=True, default="", max_length=255, verbose_name="Населенный пункт")),
                ("district", models.CharField(blank=True, default="", max_length=255, verbose_name="Квартал / район")),
                ("street", models.CharField(blank=True, default="", max_length=255, verbose_name="Улица")),
                ("building", models.CharField(blank=True, default="", max_length=255, verbose_name="Здание")),
                ("premise", models.CharField(blank=True, default="", max_length=255, verbose_name="Помещение")),
                ("premise_part", models.CharField(blank=True, default="", max_length=255, verbose_name="Часть помещения")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действителен от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действителен до")),
                ("is_active", models.BooleanField(default=True, verbose_name="Актуален")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("country", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="business_entity_legal_addresses", to="classifiers_app.oksmcountry", verbose_name="Страна")),
                ("identifier_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="legal_addresses", to="classifiers_app.businessentityidentifierrecord", verbose_name="ID-IDN")),
            ],
            options={
                "verbose_name": "Юридический адрес",
                "verbose_name_plural": "Реестр юридических адресов",
                "ordering": ["position", "id"],
            },
        ),
    ]
