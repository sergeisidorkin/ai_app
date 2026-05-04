from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0059_performer_contract_signed_pdf_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="performer",
            name="contract_signing_date",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата подписания"),
        ),
    ]
