from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0066_projectschedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="launched_at",
            field=models.DateField(blank=True, null=True, verbose_name="Дата запуска"),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="gantt_data",
            field=models.JSONField(blank=True, default=dict, verbose_name="Диаграмма Ганта"),
        ),
    ]
