from django.db import migrations, models
from django.db.models import Q


def backfill_registration_region_code(apps, schema_editor):
    BusinessEntityIdentifierRecord = apps.get_model("classifiers_app", "BusinessEntityIdentifierRecord")
    TerritorialDivision = apps.get_model("classifiers_app", "TerritorialDivision")

    for item in BusinessEntityIdentifierRecord.objects.all().iterator():
        if not item.registration_country_id or not (item.registration_region or "").strip():
            continue
        divisions = TerritorialDivision.objects.filter(
            country_id=item.registration_country_id,
            region_name__iexact=item.registration_region.strip(),
        )
        if item.registration_date:
            divisions = divisions.filter(
                effective_date__lte=item.registration_date,
            ).filter(
                Q(abolished_date__isnull=True) | Q(abolished_date__gte=item.registration_date),
            )
        division = divisions.order_by("position", "id").first()
        if division is None:
            continue
        item.registration_region_code = division.region_code
        item.save(update_fields=["registration_region_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0044_finalize_reorganization_event_normalization"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="registration_region_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Код региона"),
        ),
        migrations.RunPython(backfill_registration_region_code, migrations.RunPython.noop),
    ]
