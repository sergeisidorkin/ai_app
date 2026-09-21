from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0093_report_check_clear_comments"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="course",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Курс"),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="section",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Секция"),
        ),
    ]
