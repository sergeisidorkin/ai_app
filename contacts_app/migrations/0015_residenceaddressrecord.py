from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0049_numcaprecord_gar_territory_numcaprecord_inn"),
        ("contacts_app", "0014_phonerecord_is_primary"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResidenceAddressRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион")),
                ("postal_code", models.CharField(blank=True, default="", max_length=32, verbose_name="Индекс")),
                ("locality", models.CharField(blank=True, default="", max_length=255, verbose_name="Населенный пункт")),
                ("street", models.CharField(blank=True, default="", max_length=255, verbose_name="Улица")),
                ("building", models.CharField(blank=True, default="", max_length=255, verbose_name="Здание")),
                ("premise", models.CharField(blank=True, default="", max_length=255, verbose_name="Помещение")),
                ("premise_part", models.CharField(blank=True, default="", max_length=255, verbose_name="Часть помещения")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действ. от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действ. до")),
                ("is_active", models.BooleanField(default=True, verbose_name="Актуален")),
                ("record_date", models.DateField(blank=True, null=True, verbose_name="Дата записи")),
                ("record_author", models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи")),
                ("source", models.TextField(blank=True, default="", verbose_name="Источник")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contact_residence_address_records",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="residence_addresses",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
            ],
            options={
                "verbose_name": "Адрес проживания",
                "verbose_name_plural": "Реестр адресов проживания",
                "ordering": ["position", "id"],
            },
        ),
    ]
