import django.contrib.postgres.fields.ranges
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0033_enable_btree_gist"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessentityidentifierrecord",
            name="valid_range",
            field=django.contrib.postgres.fields.ranges.DateRangeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Технический диапазон действия",
            ),
        ),
        migrations.AddField(
            model_name="legalentityrecord",
            name="valid_range",
            field=django.contrib.postgres.fields.ranges.DateRangeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Технический диапазон действия",
            ),
        ),
    ]
