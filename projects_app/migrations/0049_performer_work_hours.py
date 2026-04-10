from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0048_alter_workvolume_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="work_hours",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Количество часов работы",
            ),
        ),
    ]
