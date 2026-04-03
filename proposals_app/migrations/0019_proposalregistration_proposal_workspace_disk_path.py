from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0018_proposalregistration_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="proposal_workspace_disk_path",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1024,
                verbose_name="Путь к рабочей папке ТКП в облаке",
            ),
        ),
    ]
