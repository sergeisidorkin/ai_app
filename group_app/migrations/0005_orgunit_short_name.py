from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0004_orgunit_unit_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="orgunit",
            name="short_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=128,
                verbose_name="Краткое имя",
            ),
        ),
    ]
