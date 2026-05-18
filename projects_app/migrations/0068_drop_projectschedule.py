from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0067_projectregistration_gantt"),
    ]

    operations = [
        migrations.DeleteModel(name="ProjectSchedule"),
    ]
