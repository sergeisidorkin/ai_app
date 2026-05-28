import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0076_projectregistration_sub_number"),
        ("proposals_app", "0054_backfill_sub_number_proposal_short_uids"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="proposal_registration",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_project_registrations",
                to="proposals_app.proposalregistration",
                verbose_name="ТКП ID",
            ),
        ),
    ]
