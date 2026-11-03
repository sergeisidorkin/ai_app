from django.db import migrations, models


def backfill_service_scopes(apps, schema_editor):
    from projects_app.service_scope import backfill_service_scopes as backfill

    backfill()


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0123_projectregistration_status_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="workvolume",
            name="scope_key",
            field=models.UUIDField(blank=True, null=True, verbose_name="Ключ набора"),
        ),
        migrations.AddField(
            model_name="legalentity",
            name="scope_key",
            field=models.UUIDField(blank=True, null=True, verbose_name="Ключ набора"),
        ),
        migrations.RunPython(backfill_service_scopes, migrations.RunPython.noop),
    ]
