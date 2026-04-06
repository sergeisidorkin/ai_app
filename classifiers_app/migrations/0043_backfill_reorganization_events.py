from django.db import migrations


def _unique_event_uid(candidate, relation_pk, seen):
    value = (candidate or "").strip()
    if not value:
        value = f"{relation_pk:05d}-REO"
    if value not in seen:
        seen.add(value)
        return value

    fallback = f"{relation_pk:05d}-REO"
    if fallback not in seen:
        seen.add(fallback)
        return fallback

    suffix = relation_pk + 1
    while True:
        fallback = f"{suffix:05d}-REO"
        if fallback not in seen:
            seen.add(fallback)
            return fallback
        suffix += 1


def forwards_backfill_reorganization_events(apps, schema_editor):
    BusinessEntityRelationRecord = apps.get_model("classifiers_app", "BusinessEntityRelationRecord")
    BusinessEntityReorganizationEvent = apps.get_model("classifiers_app", "BusinessEntityReorganizationEvent")
    db_alias = schema_editor.connection.alias

    seen_uids = set()
    for relation in (
        BusinessEntityRelationRecord.objects.using(db_alias)
        .order_by("position", "id")
        .iterator()
    ):
        candidate_uid = relation.reorganization_event_uid or f"{relation.pk:05d}-REO"
        event = BusinessEntityReorganizationEvent.objects.using(db_alias).create(
            reorganization_event_uid=_unique_event_uid(candidate_uid, relation.pk, seen_uids),
            relation_type=relation.relation_type or "",
            event_date=relation.event_date,
            comment=relation.comment or "",
            position=relation.position,
        )
        relation.event_id = event.pk
        relation.save(update_fields=["event"])


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0042_businessentityreorganizationevent_and_relation_event"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_reorganization_events, migrations.RunPython.noop),
    ]
