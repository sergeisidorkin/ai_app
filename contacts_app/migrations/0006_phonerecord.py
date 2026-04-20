from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_phone_records(apps, schema_editor):
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    PhoneRecord = apps.get_model("contacts_app", "PhoneRecord")

    next_position = PhoneRecord.objects.order_by("-position", "-id").values_list("position", flat=True).first() or 0
    today = timezone.localdate()

    for person in PersonRecord.objects.order_by("position", "id").iterator():
        if PhoneRecord.objects.filter(person_id=person.pk).exists():
            continue
        next_position += 1
        PhoneRecord.objects.create(
            person_id=person.pk,
            country_id=None,
            code="",
            phone_number="",
            valid_from=None,
            valid_to=None,
            record_date=today,
            record_author="",
            source="",
            position=next_position,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0047_physicalentityidentifier"),
        ("contacts_app", "0005_remove_personrecord_identifier_and_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhoneRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(blank=True, default="", max_length=32, verbose_name="Код")),
                ("phone_number", models.CharField(blank=True, default="", max_length=255, verbose_name="Номер телефона")),
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
                        related_name="contact_phone_records",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="phones",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
            ],
            options={
                "verbose_name": "Телефонный номер",
                "verbose_name_plural": "Реестр телефонных номеров",
                "ordering": ["position", "id"],
            },
        ),
        migrations.RunPython(backfill_phone_records, noop_reverse),
    ]
