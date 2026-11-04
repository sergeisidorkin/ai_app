from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0132_sync_tpgr_superscript_angles"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportreviewentry",
            name="appealed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Апелляция замечаний ИИ"),
        ),
    ]
