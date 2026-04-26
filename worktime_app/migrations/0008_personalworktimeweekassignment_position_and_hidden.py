from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("worktime_app", "0007_alter_worktimeassignment_record_type_add_vacation"),
    ]

    operations = [
        migrations.AddField(
            model_name="personalworktimeweekassignment",
            name="is_hidden",
            field=models.BooleanField(default=False, verbose_name="Скрыта в личном табеле"),
        ),
        migrations.AddField(
            model_name="personalworktimeweekassignment",
            name="position",
            field=models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция"),
        ),
        migrations.AlterModelOptions(
            name="personalworktimeweekassignment",
            options={
                "ordering": ["week_start", "position", "id"],
                "verbose_name": "Недельная строка личного табеля",
                "verbose_name_plural": "Недельные строки личного табеля",
            },
        ),
    ]
