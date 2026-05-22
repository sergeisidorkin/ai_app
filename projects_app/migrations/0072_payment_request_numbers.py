from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0071_performer_payment_request_sent_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentRequestCounter",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "last_number",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Последний номер заявки",
                    ),
                ),
            ],
            options={
                "verbose_name": "Счётчик заявок на оплату",
                "verbose_name_plural": "Счётчик заявок на оплату",
            },
        ),
        migrations.AddField(
            model_name="performer",
            name="advance_payment_request_number",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Номер заявки на аванс",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="final_payment_request_number",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Номер заявки на окончательный платёж",
            ),
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model(
                "projects_app", "PaymentRequestCounter"
            ).objects.get_or_create(pk=1, defaults={"last_number": 0}),
            migrations.RunPython.noop,
        ),
    ]
