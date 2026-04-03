from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0032_alter_tariff_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalsection",
            name="exclude_from_tkp_autofill",
            field=models.BooleanField(
                default=False,
                verbose_name="Исключить из автозаполнения в ТКП",
            ),
        ),
    ]
