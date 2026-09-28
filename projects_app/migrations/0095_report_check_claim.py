from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0094_report_macro_course_section"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="check_attempts",
            field=models.PositiveIntegerField(default=0, verbose_name="Попытки проверки"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_claim",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Владелец проверки",
            ),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_heartbeat_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Пульс проверки",
            ),
        ),
    ]
