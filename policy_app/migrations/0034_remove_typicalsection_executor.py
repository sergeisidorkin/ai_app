import re

from django.db import migrations


def _split_executor_value(raw_value):
    parts = []
    seen = set()
    for item in re.split(r"\s*(?:;|,|\n|/)\s*", str(raw_value or "").strip()):
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append(name)
    return parts


def backfill_executor_to_ranked_specialties(apps, schema_editor):
    TypicalSection = apps.get_model("policy_app", "TypicalSection")
    TypicalSectionSpecialty = apps.get_model("policy_app", "TypicalSectionSpecialty")
    ExpertSpecialty = apps.get_model("experts_app", "ExpertSpecialty")

    max_position = ExpertSpecialty.objects.order_by("-position").values_list("position", flat=True).first() or 0

    for section in TypicalSection.objects.exclude(executor="").iterator():
        existing_ids = set(
            TypicalSectionSpecialty.objects.filter(section_id=section.pk).values_list("specialty_id", flat=True)
        )
        next_rank = (
            TypicalSectionSpecialty.objects.filter(section_id=section.pk).order_by("-rank").values_list("rank", flat=True).first()
            or 0
        )
        for specialty_name in _split_executor_value(section.executor):
            specialty = ExpertSpecialty.objects.filter(specialty=specialty_name).first()
            if specialty is None:
                max_position += 1
                specialty = ExpertSpecialty.objects.create(
                    specialty=specialty_name,
                    specialty_en="",
                    position=max_position,
                )
            if specialty.pk in existing_ids:
                continue
            next_rank += 1
            TypicalSectionSpecialty.objects.create(
                section_id=section.pk,
                specialty_id=specialty.pk,
                rank=next_rank,
            )
            existing_ids.add(specialty.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0033_typicalsection_exclude_from_tkp_autofill"),
    ]

    operations = [
        migrations.RunPython(backfill_executor_to_ranked_specialties, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="typicalsection",
            name="executor",
        ),
    ]
