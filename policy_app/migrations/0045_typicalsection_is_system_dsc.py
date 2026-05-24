from django.db import migrations, models


DSC_DEFAULTS = {
    "code": "DSC",
    "short_name": "Description",
    "short_name_ru": "Описание",
    "name_en": "Product description",
    "name_ru": "Описание продукта",
    "accounting_type": "Раздел",
    "expertise_dir": None,
    "expertise_direction": None,
    "exclude_from_tkp_autofill": False,
    "is_system": True,
}


def _is_dsc(value):
    return str(value or "").strip().upper() == "DSC"


def seed_system_dsc_sections(apps, schema_editor):
    Product = apps.get_model("policy_app", "Product")
    TypicalSection = apps.get_model("policy_app", "TypicalSection")
    TypicalSectionSpecialty = apps.get_model("policy_app", "TypicalSectionSpecialty")
    db_alias = schema_editor.connection.alias

    for product in Product.objects.using(db_alias).order_by("position", "id"):
        sections = list(
            TypicalSection.objects.using(db_alias)
            .filter(product_id=product.pk)
            .order_by("position", "id")
        )
        section = next((item for item in sections if _is_dsc(item.code)), None)
        if section is None:
            section = TypicalSection.objects.using(db_alias).create(
                product_id=product.pk,
                position=0,
                **DSC_DEFAULTS,
            )
            sections.append(section)
        else:
            for field, value in DSC_DEFAULTS.items():
                setattr(section, field, value)
            section.save(using=db_alias)

        TypicalSectionSpecialty.objects.using(db_alias).filter(section_id=section.pk).delete()

        ordered = [section] + [item for item in sections if item.pk != section.pk]
        for index, item in enumerate(ordered, start=1):
            if item.position != index:
                TypicalSection.objects.using(db_alias).filter(pk=item.pk).update(position=index)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0044_typicalserviceterm_source_data_weeks"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalsection",
            name="is_system",
            field=models.BooleanField(default=False, verbose_name="Системный раздел"),
        ),
        migrations.RunPython(seed_system_dsc_sections, noop_reverse),
    ]
