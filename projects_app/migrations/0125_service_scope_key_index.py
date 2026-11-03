from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0124_service_scope_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workvolume",
            name="scope_key",
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Ключ набора"),
        ),
        migrations.AlterField(
            model_name="legalentity",
            name="scope_key",
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Ключ набора"),
        ),
    ]
