from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0014_legalentityrecord_registration_region"),
    ]

    operations = [
        migrations.CreateModel(
            name="RussianFederationSubjectCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_name", models.CharField(max_length=255, verbose_name="Наименование субъекта Российской Федерации")),
                ("oktmo_code", models.CharField(blank=True, default="", max_length=32, verbose_name="Код региона ОКТМО")),
                ("fns_code", models.CharField(blank=True, default="", max_length=64, verbose_name="Код ФНС")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Код субъекта Российской Федерации",
                "verbose_name_plural": "Коды субъектов Российской Федерации",
                "ordering": ["position", "id"],
            },
        ),
    ]
