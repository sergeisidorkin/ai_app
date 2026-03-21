from django.db import migrations, models


def convert_date_to_datetime(apps, schema_editor):
    """Existing DateField values become midnight DateTimeField values automatically."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0042_performer_scan_upload"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_scan_document",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Скан договора",
            ),
        ),
        migrations.AlterField(
            model_name="performer",
            name="contract_upload_date",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Дата загрузки",
            ),
        ),
    ]
