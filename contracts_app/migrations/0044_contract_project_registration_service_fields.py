from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0043_contract_project_registration_tkp_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_sections_json",
            field=models.JSONField(blank=True, default=list, verbose_name="Состав услуг: разделы"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_sections_editor_state",
            field=models.JSONField(blank=True, default=list, verbose_name="Состав услуг: состояние редактора"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_composition",
            field=models.TextField(blank=True, default="", verbose_name="Состав услуг"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_composition_customer_tz",
            field=models.TextField(blank=True, default="", verbose_name="Состав услуг: ТЗ Заказчика"),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_customer_tz_editor_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Состав услуг: состояние редактора ТЗ Заказчика",
            ),
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="service_composition_mode",
            field=models.CharField(
                blank=True,
                default="sections",
                max_length=20,
                verbose_name="Режим состава услуг",
            ),
        ),
    ]
