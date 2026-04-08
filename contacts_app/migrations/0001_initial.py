from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("classifiers_app", "0046_businessentityrecord_record_author_and_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Фамилия")),
                ("first_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Имя")),
                ("middle_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Отчество")),
                ("identifier", models.CharField(blank=True, default="", max_length=255, verbose_name="Идентификатор")),
                ("number", models.CharField(blank=True, default="", max_length=255, verbose_name="Номер")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "citizenship",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contact_person_records",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Гражданство",
                    ),
                ),
            ],
            options={
                "verbose_name": "Лицо",
                "verbose_name_plural": "Реестр лиц",
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="PositionRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "organization_short_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=512,
                        verbose_name="Наименование организации (краткое)",
                    ),
                ),
                ("job_title", models.CharField(blank=True, default="", max_length=255, verbose_name="Должность")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действ. от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действ. до")),
                ("record_date", models.DateField(blank=True, null=True, verbose_name="Дата записи")),
                ("record_author", models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи")),
                ("source", models.TextField(blank=True, default="", verbose_name="Источник")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="positions",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
            ],
            options={
                "verbose_name": "Должность",
                "verbose_name_plural": "Реестр должностей",
                "ordering": ["position", "id"],
            },
        ),
    ]
