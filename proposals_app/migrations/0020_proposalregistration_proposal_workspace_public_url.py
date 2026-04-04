from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0019_proposalregistration_proposal_workspace_disk_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="proposal_workspace_public_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Публичная ссылка на рабочую папку ТКП",
            ),
        ),
    ]
