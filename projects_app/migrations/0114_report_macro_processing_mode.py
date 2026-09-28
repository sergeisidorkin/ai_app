from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0113_report_macro_disable_tools"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="processing_mode",
            field=models.CharField(
                choices=[("chunks", "Фрагменты"), ("agent", "Агент")],
                default="chunks",
                max_length=32,
                verbose_name="Режим обработки",
            ),
        ),
    ]
