from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0003_orgunit"),
    ]

    operations = [
        migrations.AddField(
            model_name="orgunit",
            name="unit_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("administrative", "Административное подразделение"),
                    ("expertise", "Направление экспертизы"),
                    ("project_roles", "Группа проектных ролей"),
                ],
                default="",
                max_length=32,
                verbose_name="Тип подразделения",
            ),
        ),
    ]
