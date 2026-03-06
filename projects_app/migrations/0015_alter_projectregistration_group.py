from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0014_alter_projectregistration_short_uid_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectregistration",
            name="group",
            field=models.CharField(db_index=True, default="RU", max_length=2, verbose_name="Группа"),
        ),
    ]
