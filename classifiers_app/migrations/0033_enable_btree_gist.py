from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0032_backfill_legal_address_valid_from"),
    ]

    operations = [
        BtreeGistExtension(),
    ]
