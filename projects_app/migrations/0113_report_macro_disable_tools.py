from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0112_report_macro_reasoning_effort"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="disable_tools",
            field=models.BooleanField(default=False, verbose_name="Без инструментов"),
        ),
    ]
