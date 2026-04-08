from django.db import migrations, models


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
        migrations.AlterField(
            model_name="proposalregistration",
            name="recipient",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Организация"),
        ),
    ]
