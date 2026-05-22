from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0072_payment_request_numbers"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="advance_payment_request_sender",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Отправитель заявки на аванс",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="final_payment_request_sender",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Отправитель заявки на окончательный платёж",
            ),
        ),
    ]
