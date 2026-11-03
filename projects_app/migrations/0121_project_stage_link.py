from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0120_projectregistration_stage_terms"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="stage_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="stages",
                to="projects_app.projectregistration",
                verbose_name="Проект этапа",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="summary_deferred",
            field=models.BooleanField(default=False, verbose_name="Отложен"),
        ),
    ]
