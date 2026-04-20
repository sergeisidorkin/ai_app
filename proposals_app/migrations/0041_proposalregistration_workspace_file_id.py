from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0040_proposal_nextcloud_identifiers"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="proposal_workspace_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор рабочей папки ТКП в Nextcloud",
            ),
        ),
    ]
