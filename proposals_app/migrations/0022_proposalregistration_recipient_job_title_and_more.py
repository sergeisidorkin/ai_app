from django.db import migrations, models


def _backfill_recipient_job_title(apps, schema_editor):
    ProposalRegistration = apps.get_model("proposals_app", "ProposalRegistration")
    (
        ProposalRegistration.objects
        .exclude(recipient="")
        .update(recipient_job_title=models.F("recipient"))
    )


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0021_expand_proposal_status_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_job_title",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Должность"),
        ),
        migrations.RunPython(_backfill_recipient_job_title, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="proposalregistration",
            name="recipient",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Организация"),
        ),
    ]
