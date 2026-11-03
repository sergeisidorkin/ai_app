import uuid
from collections import defaultdict

from django.db import migrations, models, transaction
from django.db.models import Max, Q


def _normalize_label(value):
    return " ".join(str(value or "").split()).strip().casefold()


def _prefer_first(rows, targets):
    order = {target.pk: index for index, target in enumerate(targets)}
    return min(
        rows,
        key=lambda row: (
            order.get(getattr(row, "project_id", None), 9999),
            getattr(row, "position", 0) or 0,
            row.pk or 0,
        ),
    )


def _assign_work_scope_keys(work_model, volumes):
    pending = [volume for volume in volumes if not volume.scope_key]
    buckets = defaultdict(list)
    for volume in pending:
        label = _normalize_label(volume.asset_name or volume.name)
        buckets[(label, volume.position or 0)].append(volume)
    for rows in buckets.values():
        while rows:
            cluster = []
            seen_projects = set()
            rest = []
            for row in rows:
                if row.project_id in seen_projects:
                    rest.append(row)
                    continue
                seen_projects.add(row.project_id)
                cluster.append(row)
            scope_key = uuid.uuid4()
            work_model.objects.filter(pk__in=[row.pk for row in cluster]).update(scope_key=scope_key)
            for row in cluster:
                row.scope_key = scope_key
            rows = rest


def _assign_legal_scope_keys(legal_model, entities):
    pending = [entity for entity in entities if not entity.scope_key and entity.work_item_id]
    buckets = defaultdict(list)
    for entity in pending:
        work_scope = entity.work_item.scope_key or ("work", entity.work_item_id)
        label = _normalize_label(entity.legal_name)
        buckets[(work_scope, label, entity.position or 0)].append(entity)
    for rows in buckets.values():
        while rows:
            cluster = []
            seen_items = set()
            rest = []
            for row in rows:
                if row.work_item_id in seen_items:
                    rest.append(row)
                    continue
                seen_items.add(row.work_item_id)
                cluster.append(row)
            scope_key = uuid.uuid4()
            legal_model.objects.filter(pk__in=[row.pk for row in cluster]).update(scope_key=scope_key)
            for row in cluster:
                row.scope_key = scope_key
            rows = rest


def _copy_legal_entities(work_model, legal_model, scope_key, targets):
    volumes = list(work_model.objects.filter(scope_key=scope_key))
    if not volumes:
        return
    legals = list(
        legal_model.objects.filter(work_item__scope_key=scope_key).select_related("work_item")
    )
    if not legals:
        key = uuid.uuid4()
        source = _prefer_first(volumes, targets)
        project_ids = [volume.project_id for volume in volumes]
        last = legal_model.objects.filter(project_id__in=project_ids).aggregate(mx=Max("position")).get("mx") or 0
        position = last + 1
        for volume in volumes:
            if legal_model.objects.filter(work_item_id=volume.pk).exists():
                continue
            legal_model.objects.create(
                project_id=volume.project_id,
                work_item_id=volume.pk,
                work_type=volume.type or "",
                work_name=volume.name or "",
                legal_name=source.asset_name or source.name or "",
                country_id=source.country_id,
                identifier=source.identifier or "",
                registration_number=source.registration_number or "",
                registration_date=source.registration_date,
                scope_key=key,
                position=position,
            )
        return
    _assign_legal_scope_keys(legal_model, legals)
    grouped = defaultdict(list)
    for entity in legal_model.objects.filter(work_item__scope_key=scope_key).select_related("work_item"):
        if entity.scope_key:
            grouped[entity.scope_key].append(entity)
    for copies in grouped.values():
        canonical = _prefer_first(copies, targets)
        present = {entity.work_item_id for entity in copies}
        for volume in volumes:
            if volume.pk in present:
                continue
            legal_model.objects.create(
                project_id=volume.project_id,
                work_item_id=volume.pk,
                work_type=volume.type or "",
                work_name=volume.name or "",
                legal_name=canonical.legal_name or "",
                country_id=canonical.country_id,
                identifier=canonical.identifier or "",
                registration_number=canonical.registration_number or "",
                registration_date=canonical.registration_date,
                scope_key=canonical.scope_key,
                position=canonical.position or 0,
            )


def _delete_work_volume(work_model, performer_model, item):
    asset_name = (item.asset_name or item.name or "").strip()
    filters = Q(work_item_id=item.pk)
    if asset_name:
        filters |= Q(work_item__isnull=True, registration_id=item.project_id, asset_name=asset_name)
    performer_model.objects.filter(filters).delete()
    work_model.objects.filter(pk=item.pk).delete()


def _align_owner(project_model, work_model, legal_model, performer_model, owner):
    if owner is None or not getattr(owner, "pk", None):
        return
    if owner.stage_project_id:
        parent = project_model.objects.filter(pk=owner.stage_project_id).first()
        owner = parent or owner
    stages = list(
        project_model.objects.filter(stage_project_id=owner.pk).order_by("position", "id")
    )
    targets = stages or [owner]
    project_ids = {target.pk for target in targets}
    project_ids.add(owner.pk)
    volumes = list(work_model.objects.filter(project_id__in=project_ids).order_by("position", "id"))
    if not volumes and not legal_model.objects.filter(project_id__in=project_ids).exists():
        return
    names = {target.pk: getattr(target, "name", "") or "" for target in targets}
    _assign_work_scope_keys(work_model, volumes)
    grouped = defaultdict(list)
    for volume in volumes:
        if volume.scope_key:
            grouped[volume.scope_key].append(volume)
    for scope_key, copies in grouped.items():
        canonical = _prefer_first(copies, targets)
        by_project = {volume.project_id: volume for volume in copies}
        for target in targets:
            volume = by_project.get(target.pk)
            fields = {
                "asset_name": canonical.asset_name or "",
                "country_id": canonical.country_id,
                "identifier": canonical.identifier or "",
                "registration_number": canonical.registration_number or "",
                "registration_date": canonical.registration_date,
                "manager": canonical.manager or "",
                "position": canonical.position or 0,
                "scope_key": scope_key,
                "name": names.get(target.pk) or canonical.name or "",
            }
            if volume is None:
                sample_type = (
                    work_model.objects.filter(project_id=target.pk)
                    .exclude(type="")
                    .values_list("type", flat=True)
                    .first()
                    or ""
                )
                work_model.objects.create(project_id=target.pk, type=sample_type, **fields)
                continue
            unchanged = (
                (volume.asset_name or "") == fields["asset_name"]
                and volume.country_id == fields["country_id"]
                and (volume.identifier or "") == fields["identifier"]
                and (volume.registration_number or "") == fields["registration_number"]
                and volume.registration_date == fields["registration_date"]
                and (volume.manager or "") == fields["manager"]
                and (volume.position or 0) == fields["position"]
                and volume.scope_key == scope_key
            )
            if unchanged:
                continue
            work_model.objects.filter(pk=volume.pk).update(**fields)
            for name, value in fields.items():
                setattr(volume, name, value)
        _copy_legal_entities(work_model, legal_model, scope_key, targets)
    if owner.pk not in {target.pk for target in targets}:
        for volume in list(work_model.objects.filter(project_id=owner.pk, scope_key__isnull=False)):
            if work_model.objects.filter(scope_key=volume.scope_key).exclude(project_id=owner.pk).exists():
                _delete_work_volume(work_model, performer_model, volume)


def backfill_service_scopes(apps, schema_editor):
    project_model = apps.get_model("projects_app", "ProjectRegistration")
    work_model = apps.get_model("projects_app", "WorkVolume")
    legal_model = apps.get_model("projects_app", "LegalEntity")
    performer_model = apps.get_model("projects_app", "Performer")
    owner_ids = []
    seen = set()
    rows = project_model.objects.filter(
        pk__in=work_model.objects.values("project_id")
    ).values_list("pk", "stage_project_id")
    for project_id, parent_id in rows:
        owner_id = parent_id or project_id
        if owner_id in seen:
            continue
        seen.add(owner_id)
        owner_ids.append(owner_id)
    for owner_id in owner_ids:
        owner = project_model.objects.filter(pk=owner_id).first()
        if owner is None:
            continue
        with transaction.atomic():
            _align_owner(project_model, work_model, legal_model, performer_model, owner)


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
