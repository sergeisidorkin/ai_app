from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0026_service_goal_report"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="servicegoalreport",
            options={
                "ordering": ["position", "id"],
                "verbose_name": "Цель услуги и название отчета",
                "verbose_name_plural": "Цели услуг и названия отчетов",
            },
        ),
    ]
