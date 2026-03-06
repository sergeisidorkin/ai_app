from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0015_alter_projectregistration_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="work_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="performers",
                to="projects_app.workvolume",
                verbose_name="Строка объема услуг",
            ),
        ),
    ]
