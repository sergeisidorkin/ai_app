from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0070_performer_participation_batch_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="advance_payment_request_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Дата отправки заявки на аванс",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="final_payment_request_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Дата отправки заявки на окончательный платёж",
            ),
        ),
    ]
