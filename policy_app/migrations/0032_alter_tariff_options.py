from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0031_tariff_service_days_tkp"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="tariff",
            options={
                "ordering": ["created_by", "position", "id"],
                "verbose_name": "Тариф",
                "verbose_name_plural": "Тарифы разделов (услуг)",
            },
        ),
    ]
