from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0047_projectregistration_group_member_and_sequence"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workvolume",
            name="manager",
            field=models.CharField(
                blank=True, max_length=255, verbose_name="Менеджер проекта"
            ),
        ),
    ]
