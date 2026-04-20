from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0046_businessentityrecord_record_author_and_source"),
        ("contacts_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CitizenshipRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(blank=True, default="", max_length=255, verbose_name="Статус")),
                ("identifier", models.CharField(blank=True, default="", max_length=255, verbose_name="Идентификатор")),
                ("number", models.CharField(blank=True, default="", max_length=255, verbose_name="Номер")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действ. от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действ. до")),
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
                        related_name="contact_citizenship_records",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="citizenships",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
            ],
            options={
                "verbose_name": "Гражданство",
                "verbose_name_plural": "Реестр гражданств и идентификаторов",
                "ordering": ["position", "id"],
            },
        ),
    ]
