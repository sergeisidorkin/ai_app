from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0042_servicegoalreport_product_name_and_report_title_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalserviceterm",
            name="gantt_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Диаграмма Гантта",
            ),
        ),
    ]
