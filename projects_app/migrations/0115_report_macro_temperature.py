from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0114_report_macro_processing_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="temperature",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "По умолчанию"),
                    ("0", "0"),
                    ("0.1", "0.1"),
                    ("0.2", "0.2"),
                    ("0.3", "0.3"),
                    ("0.5", "0.5"),
                    ("0.7", "0.7"),
                    ("1", "1"),
                ],
                default="",
                max_length=8,
                verbose_name="Температура",
            ),
        ),
    ]
