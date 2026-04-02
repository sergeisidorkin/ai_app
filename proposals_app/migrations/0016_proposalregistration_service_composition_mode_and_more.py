from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0015_proposalregistration_service_sections_json"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="service_composition_customer_tz",
            field=models.TextField(blank=True, default="", verbose_name="Состав услуг: ТЗ Заказчика"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="service_composition_mode",
            field=models.CharField(blank=True, default="sections", max_length=20, verbose_name="Режим состава услуг"),
        ),
    ]
