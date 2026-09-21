import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0049_reportstructure"),
        ("projects_app", "0091_report_upload_sent_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcheckrule",
            name="expertise_dir",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="report_check_rules",
                to="policy_app.expertisedirection",
                verbose_name="Экспертиза",
            ),
        ),
    ]
