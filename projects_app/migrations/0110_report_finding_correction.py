from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0109_report_review_comment_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="check_finding_correction",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                verbose_name="Корректировка замечаний",
            ),
        ),
    ]
