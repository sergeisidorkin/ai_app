from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0085_report_macro"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcheckrule",
            name="is_full_report",
            field=models.BooleanField(db_index=True, default=False, verbose_name="Весь отчет"),
        ),
    ]
