from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0082_report_submission"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="is_full_report",
            field=models.BooleanField("Весь отчет", default=False, db_index=True),
        ),
        migrations.RemoveConstraint(
            model_name="performerreportupload",
            name="uniq_report_upload_all_sections",
        ),
        migrations.RemoveConstraint(
            model_name="performerreportupload",
            name="uniq_report_upload_section",
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_all_sections", True), ("is_full_report", False)),
                fields=("registration", "executor", "asset_name"),
                name="uniq_report_upload_all_sections",
            ),
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("is_all_sections", False),
                    ("is_full_report", False),
                    ("performer__isnull", False),
                ),
                fields=("performer",),
                name="uniq_report_upload_section",
            ),
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_full_report", True)),
                fields=("registration", "asset_name"),
                name="uniq_report_upload_full_report",
            ),
        ),
    ]
