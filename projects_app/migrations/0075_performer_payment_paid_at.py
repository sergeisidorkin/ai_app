from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0074_performer_payment_paid"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="advance_payment_paid_at",
            field=models.DateTimeField(
                "Дата изменения оплаты аванса",
                blank=True,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="final_payment_paid_at",
            field=models.DateTimeField(
                "Дата изменения оплаты окончательного платежа",
                blank=True,
                null=True,
            ),
        ),
    ]
