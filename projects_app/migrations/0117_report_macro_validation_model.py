from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0116_report_skill_processing_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="validation_model_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Модель валидации",
            ),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="validation_reasoning_effort",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="Уровень рассуждений валидации",
            ),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="validation_temperature",
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
                verbose_name="Температура валидации",
            ),
        ),
    ]
