from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0036_seed_preliminary_report_term_month_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="service_customer_tz_editor_state",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Состав услуг: состояние редактора ТЗ Заказчика",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="service_sections_editor_state",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="Состав услуг: состояние редактора",
            ),
        ),
    ]
