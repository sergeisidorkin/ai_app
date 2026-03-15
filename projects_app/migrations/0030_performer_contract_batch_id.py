from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0029_seed_workspace_folders"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_batch_id",
            field=models.UUIDField(
                verbose_name="ID батча договора",
                null=True,
                blank=True,
                db_index=True,
            ),
        ),
    ]
