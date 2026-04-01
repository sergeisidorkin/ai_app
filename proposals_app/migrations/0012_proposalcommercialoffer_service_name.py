from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0011_proposalcommercialoffer"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalcommercialoffer",
            name="service_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Услуги"),
        ),
    ]
