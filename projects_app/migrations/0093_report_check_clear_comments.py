from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0092_report_check_expertise_dir"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcheckrule",
            name="clear_comments",
            field=models.BooleanField(default=False, verbose_name="Очистка"),
        ),
    ]
