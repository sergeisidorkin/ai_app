from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0089_report_upload_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcheckrule",
            name="finding_threshold",
            field=models.PositiveIntegerField(default=0, verbose_name="Число замечаний"),
        ),
    ]
