from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0027_coordinator_nextcloud_editor"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertspecialty",
            name="upload_expertise_direction_ids",
            field=models.JSONField(
                blank=True,
                db_default=[],
                default=list,
                verbose_name="Направления экспертизы для загрузки разделов",
            ),
        ),
    ]
