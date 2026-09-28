from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0104_report_check_launch_and_macro_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcheckline",
            name="is_enabled",
            field=models.BooleanField(default=True, verbose_name="Участвует в запуске"),
        ),
    ]
