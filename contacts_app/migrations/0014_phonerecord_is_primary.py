from django.db import migrations, models
from django.db.models import Q


def assign_primary_phone_per_person(apps, schema_editor):
    PhoneRecord = apps.get_model("contacts_app", "PhoneRecord")
    person_ids = (
        PhoneRecord.objects.order_by()
        .values_list("person_id", flat=True)
        .distinct()
    )
    for person_id in person_ids:
        first_phone = (
            PhoneRecord.objects.filter(person_id=person_id)
            .order_by("position", "id")
            .first()
        )
        if first_phone is not None:
            PhoneRecord.objects.filter(pk=first_phone.pk).update(is_primary=True)


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0013_user_management_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="phonerecord",
            name="is_primary",
            field=models.BooleanField(default=False, verbose_name="Основной"),
        ),
        migrations.RunPython(assign_primary_phone_per_person, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="phonerecord",
            constraint=models.UniqueConstraint(
                condition=Q(is_primary=True),
                fields=("person",),
                name="contacts_phone_primary_per_person",
            ),
        ),
    ]
