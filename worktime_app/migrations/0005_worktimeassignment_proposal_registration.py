import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0039_seed_budget_table_variable"),
        ("worktime_app", "0004_worktimeassignment_manual_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="worktimeassignment",
            name="proposal_registration",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="worktime_assignments",
                to="proposals_app.proposalregistration",
                verbose_name="ТКП",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="worktimeassignment",
            name="worktime_assignment_manual_record_type_unique",
        ),
        migrations.AddConstraint(
            model_name="worktimeassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(proposal_registration__isnull=True, registration__isnull=True),
                fields=("executor_name", "record_type"),
                name="worktime_assignment_manual_record_type_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="worktimeassignment",
            constraint=models.UniqueConstraint(
                fields=("proposal_registration", "executor_name"),
                name="worktime_assignment_tkp_executor_unique",
            ),
        ),
    ]
