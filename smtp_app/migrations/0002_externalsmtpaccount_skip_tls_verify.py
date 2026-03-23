from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("smtp_app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="externalsmtpaccount",
            name="skip_tls_verify",
            field=models.BooleanField(default=False, verbose_name="Не проверять TLS-сертификат"),
        ),
    ]
