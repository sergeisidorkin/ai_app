from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0033_typicalsection_exclude_from_tkp_autofill"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="typicalsection",
            name="executor",
        ),
    ]
