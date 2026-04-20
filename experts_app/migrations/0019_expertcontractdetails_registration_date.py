from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0018_expertcontractdetails_registration_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_date",
            field=models.DateField(blank=True, null=True, verbose_name="Регистрация: дата"),
        ),
    ]
