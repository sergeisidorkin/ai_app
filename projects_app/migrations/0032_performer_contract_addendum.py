from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0031_backfill_contract_batch_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_is_addendum",
            field=models.BooleanField(default=False, verbose_name="Доп. соглашение"),
        ),
        migrations.AddField(
            model_name="performer",
            name="contract_addendum_number",
            field=models.PositiveIntegerField(
                null=True, blank=True, verbose_name="Номер доп. соглашения",
            ),
        ),
    ]
