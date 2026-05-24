from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0045_typicalsection_is_system_dsc"),
    ]

    operations = [
        migrations.AlterField(
            model_name="typicalsection",
            name="is_system",
            field=models.BooleanField(db_index=True, default=False, verbose_name="Системный раздел"),
        ),
    ]
