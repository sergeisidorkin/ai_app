from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0088_seed_tpgr_macros"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="version",
            field=models.PositiveIntegerField("Версия", db_index=True, default=0),
        ),
        migrations.RemoveConstraint(
            model_name="performerreportupload",
            name="uniq_report_upload_all_sections",
        ),
        migrations.RemoveConstraint(
            model_name="performerreportupload",
            name="uniq_report_upload_section",
        ),
        migrations.RemoveConstraint(
            model_name="performerreportupload",
            name="uniq_report_upload_full_report",
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_all_sections", True), ("is_full_report", False)),
                fields=("registration", "executor", "asset_name", "version"),
                name="uniq_report_upload_all_sections_version",
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
                fields=("performer", "version"),
                name="uniq_report_upload_section_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="performerreportupload",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_full_report", True)),
                fields=("registration", "asset_name", "version"),
                name="uniq_report_upload_full_report_version",
            ),
        ),
    ]
