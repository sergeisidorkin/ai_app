from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0110_report_finding_correction"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportreviewentry",
            name="remarks_notice_pending",
            field=models.BooleanField(
                default=False,
                verbose_name="Замечания ещё не отправлены",
            ),
        ),
    ]
