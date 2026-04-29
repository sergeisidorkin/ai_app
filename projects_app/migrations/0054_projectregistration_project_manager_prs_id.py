from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0053_remove_project_registration_identity_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="project_manager_prs_id",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="ID-PRS руководителя проекта"),
        ),
    ]
