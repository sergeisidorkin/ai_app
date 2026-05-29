from datetime import date

from django.db import migrations, models
from django.db.models import Max, Q
import django.db.models.deletion


EXECUTOR_SPECIALTY_SOURCE = "[Исполнители / База физлиц-исполнителей]"


def backfill_contact_specialty_records(apps, schema_editor):
    ExpertProfileSpecialty = apps.get_model("experts_app", "ExpertProfileSpecialty")
    SpecialtyRecord = apps.get_model("contacts_app", "SpecialtyRecord")
    PersonRecord = apps.get_model("contacts_app", "PersonRecord")
    today = date.today()
    next_position = (SpecialtyRecord.objects.using(schema_editor.connection.alias).aggregate(mx=Max("position")).get("mx") or 0) + 1

    links = (
        ExpertProfileSpecialty.objects.using(schema_editor.connection.alias)
        .select_related("profile__employee")
        .filter(contact_specialty_record__isnull=True)
        .order_by("profile_id", "rank", "id")
    )
    for link in links:
        person_id = getattr(getattr(link.profile, "employee", None), "person_record_id", None)
        if not person_id or not link.specialty_id:
            continue
        contact_record = (
            SpecialtyRecord.objects.using(schema_editor.connection.alias)
            .filter(person_id=person_id, specialty_id=link.specialty_id)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=today))
            .order_by("position", "id")
            .first()
        )
        if contact_record is None:
            person = PersonRecord.objects.using(schema_editor.connection.alias).filter(pk=person_id).first()
            contact_record = SpecialtyRecord.objects.using(schema_editor.connection.alias).create(
                person_id=person_id,
                specialty_id=link.specialty_id,
                valid_from=today,
                valid_to=None,
                is_active=True,
                user_kind=getattr(person, "user_kind", "") or "",
                record_date=today,
                record_author="",
                source=EXECUTOR_SPECIALTY_SOURCE,
                position=next_position,
            )
            next_position += 1
        link.contact_specialty_record_id = contact_record.pk
        link.save(update_fields=["contact_specialty_record"])


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0020_specialtyrecord"),
        ("experts_app", "0020_alter_expertcontractdetails_gender"),
        ("users_app", "0008_employee_person_record_many_to_one"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofilespecialty",
            name="contact_specialty_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="expert_profile_links",
                to="contacts_app.specialtyrecord",
            ),
        ),
        migrations.RunPython(backfill_contact_specialty_records, migrations.RunPython.noop),
    ]
