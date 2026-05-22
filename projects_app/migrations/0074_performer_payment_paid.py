from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0073_performer_payment_request_sender"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="advance_payment_paid",
            field=models.BooleanField(default=False, verbose_name="Аванс оплачен"),
        ),
        migrations.AddField(
            model_name="performer",
            name="final_payment_paid",
            field=models.BooleanField(default=False, verbose_name="Окончательный платёж оплачен"),
        ),
    ]
