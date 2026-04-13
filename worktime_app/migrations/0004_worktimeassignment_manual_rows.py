import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("worktime_app", "0003_worktimeassignment_record_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worktimeassignment",
            name="registration",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="worktime_assignments",
                to="projects_app.projectregistration",
                verbose_name="Проект",
            ),
        ),
        migrations.AddConstraint(
            model_name="worktimeassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(registration__isnull=True),
                fields=("executor_name", "record_type"),
                name="worktime_assignment_manual_record_type_unique",
            ),
        ),
    ]
