import uuid
from itertools import groupby
from operator import attrgetter

from django.db import migrations


def backfill_batch_ids(apps, schema_editor):
    Performer = apps.get_model("projects_app", "Performer")
    performers = (
        Performer.objects
        .filter(contract_sent_at__isnull=False, contract_batch_id__isnull=True)
        .order_by("registration_id", "executor", "contract_sent_at")
    )

    key_func = attrgetter("registration_id", "executor", "contract_sent_at")
    for _key, group in groupby(performers, key=key_func):
        batch_id = uuid.uuid4()
        ids = [p.pk for p in group]
        Performer.objects.filter(pk__in=ids).update(contract_batch_id=batch_id)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0030_performer_contract_batch_id"),
    ]

    operations = [
        migrations.RunPython(backfill_batch_ids, migrations.RunPython.noop),
    ]
