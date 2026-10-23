from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0053_expertisedirection_department"),
        ("experts_app", "0024_alter_expertspecialty_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="PolicyExpertSpecialty",
            fields=[],
            options={
                "verbose_name": "Специальность исполнителя",
                "verbose_name_plural": "Специальности исполнителей",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("experts_app.expertspecialty",),
        ),
    ]
