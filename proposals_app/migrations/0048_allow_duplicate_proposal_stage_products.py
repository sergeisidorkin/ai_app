from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0047_seed_facsimile_variable"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="proposalregistrationproduct",
            unique_together=set(),
        ),
    ]
