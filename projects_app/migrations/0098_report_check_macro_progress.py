from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0097_sync_tpgr_macro_matched_angles"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="check_macro_index",
            field=models.PositiveIntegerField(default=0, verbose_name="Текущий макрос"),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_macro_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Текущий макрос",
            ),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_macro_total",
            field=models.PositiveIntegerField(default=0, verbose_name="Макросов в проверке"),
        ),
    ]
