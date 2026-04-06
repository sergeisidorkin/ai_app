from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0036_validate_no_period_overlaps"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="businessentityidentifierrecord",
            constraint=ExclusionConstraint(
                name="bei_no_overlap_per_business_entity",
                expressions=[
                    ("business_entity", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="legalentityrecord",
            constraint=ExclusionConstraint(
                name="ler_name_no_overlap_per_identifier",
                expressions=[
                    ("identifier_record", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(attribute="Наименование", identifier_record__isnull=False),
            ),
        ),
        migrations.AddConstraint(
            model_name="legalentityrecord",
            constraint=ExclusionConstraint(
                name="ler_address_no_overlap_per_identifier",
                expressions=[
                    ("identifier_record", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(attribute="Юридический адрес", identifier_record__isnull=False),
            ),
        ),
    ]
