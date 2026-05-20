from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0069_migrate_stage1_weeks_to_months"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="participation_batch_id",
            field=models.UUIDField(
                verbose_name="ID батча подтверждения участия",
                null=True,
                blank=True,
                db_index=True,
            ),
        ),
    ]
