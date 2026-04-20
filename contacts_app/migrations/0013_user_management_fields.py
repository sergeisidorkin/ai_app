from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0012_backfill_email_valid_from"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailrecord",
            name="is_user_managed",
            field=models.BooleanField(default=False, verbose_name="Управляется пользователем"),
        ),
        migrations.AddField(
            model_name="emailrecord",
            name="user_kind",
            field=models.CharField(
                blank=True,
                choices=[("employee", "Сотрудник"), ("external", "Внешний пользователь")],
                default="",
                max_length=16,
                verbose_name="Пользователь",
            ),
        ),
        migrations.AddField(
            model_name="personrecord",
            name="user_kind",
            field=models.CharField(
                blank=True,
                choices=[("employee", "Сотрудник"), ("external", "Внешний пользователь")],
                default="",
                max_length=16,
                verbose_name="Пользователь",
            ),
        ),
        migrations.AddField(
            model_name="positionrecord",
            name="is_user_managed",
            field=models.BooleanField(default=False, verbose_name="Управляется пользователем"),
        ),
    ]
