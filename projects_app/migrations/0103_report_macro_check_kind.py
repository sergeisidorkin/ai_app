from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0102_sync_tpgr_dash_abbr_word"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="check_kind",
            field=models.CharField(
                choices=[("macro", "Макрос"), ("skill", "Навык")],
                db_index=True,
                default="macro",
                max_length=16,
                verbose_name="Вид проверки",
            ),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="model_id",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Модель"),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="skill_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Наименование навыка DHS",
            ),
        ),
        migrations.AlterField(
            model_name="reportmacro",
            name="code",
            field=models.TextField(blank=True, default="", verbose_name="Код"),
        ),
    ]
