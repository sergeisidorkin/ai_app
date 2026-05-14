from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0061_split_project_registration_products"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="registration_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регион"),
        ),
    ]
