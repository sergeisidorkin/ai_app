from django.db import migrations, models
import django.db.models.deletion


ATTRIBUTE_NAME = "Наименование"
ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"


def forwards_unify_legal_entities_and_addresses(apps, schema_editor):
    LegalEntityRecord = apps.get_model("classifiers_app", "LegalEntityRecord")
    BusinessEntityLegalAddressRecord = apps.get_model("classifiers_app", "BusinessEntityLegalAddressRecord")

    db_alias = schema_editor.connection.alias

    LegalEntityRecord.objects.using(db_alias).all().update(attribute=ATTRIBUTE_NAME)

    current_max_position = (
        LegalEntityRecord.objects.using(db_alias).order_by("-position").values_list("position", flat=True).first() or 0
    )
    next_position = current_max_position + 1

    for address in BusinessEntityLegalAddressRecord.objects.using(db_alias).order_by("position", "id"):
        LegalEntityRecord.objects.using(db_alias).create(
            attribute=ATTRIBUTE_LEGAL_ADDRESS,
            short_name="",
            full_name="",
            identifier="",
            registration_number="",
            registration_date=None,
            identifier_record_id=address.identifier_record_id,
            registration_country_id=address.country_id,
            registration_region=address.region,
            record_date=None,
            record_author="",
            name_received_date=None,
            name_changed_date=None,
            postal_code=address.postal_code,
            municipality=address.municipality,
            settlement=address.settlement,
            locality=address.locality,
            district=address.district,
            street=address.street,
            building=address.building,
            premise=address.premise,
            premise_part=address.premise_part,
            valid_from=address.valid_from,
            valid_to=address.valid_to,
            is_active=address.is_active,
            position=next_position,
        )
        next_position += 1


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0022_businessentityattributerecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="legalentityrecord",
            name="attribute",
            field=models.CharField(
                choices=[(ATTRIBUTE_NAME, ATTRIBUTE_NAME), (ATTRIBUTE_LEGAL_ADDRESS, ATTRIBUTE_LEGAL_ADDRESS)],
                db_index=True,
                default=ATTRIBUTE_NAME,
                max_length=64,
                verbose_name="Атрибут",
            ),
        ),
        migrations.AlterField(
            model_name="legalentityrecord",
            name="short_name",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="Наименование (краткое)"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="legal_entity_records",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="ID-IDN",
            ),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="postal_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Индекс"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="municipality",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Муниципальное образование"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="settlement",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Поселение"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="locality",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Населенный пункт"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="district",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Квартал / район"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="street",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Улица"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="building",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Здание"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="premise",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Помещение"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="premise_part",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Часть помещения"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="valid_from",
            field=models.DateField(blank=True, null=True, verbose_name="Действителен от"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="valid_to",
            field=models.DateField(blank=True, null=True, verbose_name="Действителен до"),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Актуален"),
        ),
        migrations.RunPython(forwards_unify_legal_entities_and_addresses, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="BusinessEntityLegalAddressRecord",
        ),
    ]
