"""Активы и юрлица задаются на проект и копируются на каждый его этап."""

import uuid
from collections import defaultdict

from django.db import transaction
from django.db.models import Max, Q

from .models import LegalEntity, Performer, ProjectRegistration, WorkVolume


def owning_registration(registration):
    if registration is None:
        return None
    if registration.stage_project_id:
        parent = registration.stage_project
        return parent or registration
    return registration


def service_targets(registration):
    """Этапы проекта по порядку. Если этапов нет, цель — сам проект."""
    owner = owning_registration(registration)
    if owner is None or not getattr(owner, "pk", None):
        return []
    stages = list(
        ProjectRegistration.objects.filter(stage_project_id=owner.pk).order_by("position", "id")
    )
    if stages:
        return stages
    return [owner]


def _normalize_label(value):
    return " ".join(str(value or "").split()).strip().casefold()


def _service_owner(row):
    project = getattr(row, "project", None)
    if project is not None and project.stage_project_id:
        return project.stage_project or project
    return project


def attach_service_owner(row):
    row.service_owner = _service_owner(row)
    return row


def collapse_service_rows(rows):
    """Одна видимая строка на набор. Представитель — копия первого этапа."""
    groups = {}
    order = []
    for row in rows:
        key = getattr(row, "scope_key", None) or ("pk", row.pk)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    chosen = []
    for key in order:
        copies = groups[key]
        chosen.append(attach_service_owner(_prefer_first_target(copies)))
    chosen.sort(
        key=lambda row: (
            getattr(getattr(row, "project", None), "position", 0) or 0,
            row.position or 0,
            row.pk or 0,
        )
    )
    return chosen


def _prefer_first_target(copies):
    def rank(row):
        owner = _service_owner(row)
        stages = []
        if owner is not None and getattr(owner, "pk", None):
            cache = getattr(owner, "_prefetched_objects_cache", {})
            if "stages" in cache:
                stages = list(cache["stages"])
            elif owner.pk:
                stages = list(owner.stages.order_by("position", "id"))
        order = {stage.pk: index for index, stage in enumerate(stages)}
        return (order.get(row.project_id, 0 if not stages else 9999), row.position or 0, row.pk or 0)

    return min(copies, key=rank)


def representative_work_volumes():
    volumes = list(
        WorkVolume.objects.select_related("project", "project__stage_project").order_by(
            "project__position", "position", "id"
        )
    )
    return collapse_service_rows(volumes)


def work_scope_copies(item):
    if item is None:
        return []
    if item.scope_key:
        copies = list(WorkVolume.objects.filter(scope_key=item.scope_key))
        if copies:
            return copies
    return [item]


def legal_scope_copies(entity):
    if entity is None:
        return []
    if entity.scope_key:
        copies = list(LegalEntity.objects.filter(scope_key=entity.scope_key))
        if copies:
            return copies
    return [entity]


def delete_work_volume_row(item):
    asset_name = (item.asset_name or item.name or "").strip()
    filters = Q(work_item=item)
    if asset_name:
        filters |= Q(
            work_item__isnull=True,
            registration_id=item.project_id,
            asset_name=asset_name,
        )
    Performer.objects.filter(filters).delete()
    item.delete()


def delete_work_scope(item):
    """Удаляет все этапные копии. None — удаление запрещено из-за отчёта."""
    from .report_submission import work_item_has_report_uploads

    copies = work_scope_copies(item)
    if any(work_item_has_report_uploads(copy) for copy in copies):
        return None
    project_ids = {copy.project_id for copy in copies if copy.project_id}
    for copy in copies:
        delete_work_volume_row(copy)
    return project_ids


def mirror_work_positions(project_id):
    if not project_id:
        return
    for row in WorkVolume.objects.filter(project_id=project_id).only("id", "position", "scope_key"):
        if not row.scope_key:
            continue
        WorkVolume.objects.filter(scope_key=row.scope_key).exclude(pk=row.pk).update(position=row.position)


def mirror_legal_positions(project_id):
    if not project_id:
        return
    for row in LegalEntity.objects.filter(project_id=project_id).only("id", "position", "scope_key"):
        if not row.scope_key:
            continue
        LegalEntity.objects.filter(scope_key=row.scope_key).exclude(pk=row.pk).update(position=row.position)


def mirror_scoped_row_order(model, result):
    for scope in result.scopes:
        for row in scope.after:
            key = getattr(row, "scope_key", None)
            if not key:
                continue
            model.objects.filter(scope_key=key).exclude(pk=row.pk).update(position=row.position)


def next_work_position(owning):
    target_ids = [target.pk for target in service_targets(owning)]
    if not target_ids:
        return 1
    last = WorkVolume.objects.filter(project_id__in=target_ids).aggregate(mx=Max("position")).get("mx") or 0
    return last + 1


def next_legal_position(work_item):
    if work_item is None or not work_item.scope_key:
        project_id = getattr(work_item, "project_id", None)
        last = LegalEntity.objects.filter(project_id=project_id).aggregate(mx=Max("position")).get("mx") or 0
        return last + 1
    last = (
        LegalEntity.objects.filter(work_item__scope_key=work_item.scope_key)
        .aggregate(mx=Max("position"))
        .get("mx")
        or 0
    )
    return last + 1


def _apply_work_fields(volume, fields):
    volume.asset_name = fields["asset_name"]
    volume.country = fields["country"]
    volume.identifier = fields["identifier"]
    volume.registration_number = fields["registration_number"]
    volume.registration_date = fields["registration_date"]
    volume.manager = fields["manager"]
    volume.position = fields["position"]
    volume.scope_key = fields["scope_key"]


def _work_fields_from_volume(volume, scope_key=None, position=None):
    return {
        "asset_name": volume.asset_name,
        "country": volume.country,
        "identifier": volume.identifier,
        "registration_number": volume.registration_number,
        "registration_date": volume.registration_date,
        "manager": volume.manager,
        "position": volume.position if position is None else position,
        "scope_key": scope_key or volume.scope_key,
    }


@transaction.atomic
def write_work_scope(scope_key, owning, fields, source_pk=None):
    targets = service_targets(owning)
    if not targets:
        return None
    fields = dict(fields)
    fields["scope_key"] = scope_key
    existing = {}
    for volume in WorkVolume.objects.filter(scope_key=scope_key).select_related("project"):
        existing[volume.project_id] = volume
    if source_pk:
        current = WorkVolume.objects.filter(pk=source_pk).select_related("project").first()
        if current is not None:
            existing.setdefault(current.project_id, current)
    representative = None
    created_volumes = []
    for target in targets:
        volume = existing.pop(target.pk, None)
        if volume is None:
            volume = WorkVolume(project=target)
            volume._skip_primary_legal = True
            created = True
        else:
            created = False
        _apply_work_fields(volume, fields)
        volume.project = target
        volume.save()
        if created:
            created_volumes.append(volume)
        if representative is None:
            representative = volume
    for leftover in existing.values():
        delete_work_volume_row(leftover)
    if created_volumes:
        _copy_legal_entities_for_work_scope(scope_key)
    return representative


def save_work_volume_form(form):
    instance = form.instance
    owning = form.cleaned_data["project"]
    original = None
    if instance.pk:
        original = WorkVolume.objects.filter(pk=instance.pk).values("scope_key", "position").first()
    scope_key = (original or {}).get("scope_key") or uuid.uuid4()
    position = (original or {}).get("position") or 0
    if not position:
        position = next_work_position(owning)
    fields = {
        "asset_name": form.cleaned_data.get("asset_name") or "",
        "country": form.cleaned_data.get("country"),
        "identifier": form.cleaned_data.get("identifier") or "",
        "registration_number": form.cleaned_data.get("registration_number") or "",
        "registration_date": form.cleaned_data.get("registration_date"),
        "manager": form.cleaned_data.get("manager") or "",
        "position": position,
        "scope_key": scope_key,
    }
    return write_work_scope(scope_key, owning, fields, source_pk=instance.pk)


def _copy_legal_entities_for_work_scope(scope_key):
    volumes = list(WorkVolume.objects.filter(scope_key=scope_key).select_related("project"))
    if not volumes:
        return
    legals = list(
        LegalEntity.objects.filter(work_item__scope_key=scope_key).select_related("work_item", "country")
    )
    if not legals:
        key = uuid.uuid4()
        source = _prefer_first_target(volumes)
        last = (
            LegalEntity.objects.filter(project_id__in=[volume.project_id for volume in volumes])
            .aggregate(mx=Max("position"))
            .get("mx")
            or 0
        )
        position = last + 1
        for volume in volumes:
            if volume.legal_entities.exists():
                continue
            LegalEntity.objects.create(
                project=volume.project,
                work_item=volume,
                work_type=volume.type or "",
                work_name=volume.name or "",
                legal_name=source.asset_name or source.name or "",
                country=source.country,
                identifier=source.identifier,
                registration_number=source.registration_number,
                registration_date=source.registration_date,
                scope_key=key,
                position=position,
            )
        return
    _assign_legal_scope_keys(legals)
    grouped = defaultdict(list)
    for entity in LegalEntity.objects.filter(work_item__scope_key=scope_key).select_related("work_item"):
        if entity.scope_key:
            grouped[entity.scope_key].append(entity)
    for copies in grouped.values():
        canonical = _prefer_first_target(copies)
        for volume in volumes:
            if any(entity.work_item_id == volume.pk for entity in copies):
                continue
            LegalEntity.objects.create(
                project=volume.project,
                work_item=volume,
                legal_name=canonical.legal_name,
                country=canonical.country,
                identifier=canonical.identifier,
                registration_number=canonical.registration_number,
                registration_date=canonical.registration_date,
                scope_key=canonical.scope_key,
                position=canonical.position,
            )


@transaction.atomic
def write_legal_scope(scope_key, work_scope_key, fields):
    volumes = list(
        WorkVolume.objects.filter(scope_key=work_scope_key).select_related("project").order_by("project__position", "id")
    )
    if not volumes:
        return None
    existing = {
        entity.work_item_id: entity
        for entity in LegalEntity.objects.filter(scope_key=scope_key)
    }
    representative = None
    first_target_id = _prefer_first_target(volumes).project_id
    for volume in volumes:
        entity = existing.pop(volume.pk, None)
        if entity is None:
            entity = LegalEntity(work_item=volume, scope_key=scope_key)
        entity.work_item = volume
        entity.legal_name = fields["legal_name"]
        entity.country = fields["country"]
        entity.identifier = fields["identifier"]
        entity.registration_number = fields["registration_number"]
        entity.registration_date = fields["registration_date"]
        entity.position = fields["position"]
        entity.scope_key = scope_key
        entity.save()
        if volume.project_id == first_target_id:
            representative = entity
    for leftover in existing.values():
        leftover.delete()
    return representative


def save_legal_entity_form(form):
    instance = form.instance
    work = form.cleaned_data["work_item"]
    original = None
    if instance.pk:
        original = LegalEntity.objects.filter(pk=instance.pk).values("scope_key", "position").first()
    if not work.scope_key:
        work.scope_key = uuid.uuid4()
        WorkVolume.objects.filter(pk=work.pk).update(scope_key=work.scope_key)
    work = ensure_work_copies(work) or work
    scope_key = (original or {}).get("scope_key") or uuid.uuid4()
    position = (original or {}).get("position") or 0
    if not position:
        position = next_legal_position(work)
    return write_legal_scope(
        scope_key,
        work.scope_key,
        {
            "legal_name": form.cleaned_data.get("legal_name") or "",
            "country": form.cleaned_data.get("country"),
            "identifier": form.cleaned_data.get("identifier") or "",
            "registration_number": form.cleaned_data.get("registration_number") or "",
            "registration_date": form.cleaned_data.get("registration_date"),
            "position": position,
        },
    )


def ensure_work_copies(work):
    if work is None or not work.pk:
        return work
    if not work.scope_key:
        work.scope_key = uuid.uuid4()
        WorkVolume.objects.filter(pk=work.pk).update(scope_key=work.scope_key)
    owning = owning_registration(work.project)
    targets = service_targets(owning)
    present = set(
        WorkVolume.objects.filter(scope_key=work.scope_key).values_list("project_id", flat=True)
    )
    if targets and all(target.pk in present for target in targets):
        return work
    return write_work_scope(
        work.scope_key,
        owning,
        _work_fields_from_volume(work, scope_key=work.scope_key, position=work.position or next_work_position(owning)),
        source_pk=work.pk,
    )


def _assign_work_scope_keys(volumes):
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
            ids = [row.pk for row in cluster]
            WorkVolume.objects.filter(pk__in=ids).update(scope_key=scope_key)
            for row in cluster:
                row.scope_key = scope_key
            rows = rest


def _assign_legal_scope_keys(entities):
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
            ids = [row.pk for row in cluster]
            LegalEntity.objects.filter(pk__in=ids).update(scope_key=scope_key)
            for row in cluster:
                row.scope_key = scope_key
            rows = rest


def _canonical_work(copies, targets):
    order = {target.pk: index for index, target in enumerate(targets)}
    return min(copies, key=lambda volume: (order.get(volume.project_id, 9999), volume.pk or 0))


@transaction.atomic
def align_project_service_scope(registration):
    """Делает состав активов и юрлиц одинаковым на всех этапах проекта."""
    owner = owning_registration(registration)
    if owner is None or not getattr(owner, "pk", None):
        return
    targets = service_targets(owner)
    if not targets:
        return
    project_ids = {target.pk for target in targets}
    project_ids.add(owner.pk)
    volumes = list(
        WorkVolume.objects.filter(project_id__in=project_ids)
        .select_related("project", "country")
        .order_by("position", "id")
    )
    if not volumes and not LegalEntity.objects.filter(project_id__in=project_ids).exists():
        return
    _assign_work_scope_keys(volumes)
    grouped = defaultdict(list)
    for volume in volumes:
        if volume.scope_key:
            grouped[volume.scope_key].append(volume)
    for scope_key, copies in grouped.items():
        canonical = _canonical_work(copies, targets)
        fields = _work_fields_from_volume(canonical, scope_key=scope_key)
        by_project = {volume.project_id: volume for volume in copies}
        for target in targets:
            volume = by_project.get(target.pk)
            if volume is None:
                volume = WorkVolume(project=target)
                volume._skip_primary_legal = True
                _apply_work_fields(volume, fields)
                volume.project = target
                volume.save()
                continue
            if (
                volume.asset_name == fields["asset_name"]
                and volume.country_id == (fields["country"].pk if fields["country"] else None)
                and (volume.identifier or "") == (fields["identifier"] or "")
                and (volume.registration_number or "") == (fields["registration_number"] or "")
                and volume.registration_date == fields["registration_date"]
                and (volume.manager or "") == (fields["manager"] or "")
                and volume.position == fields["position"]
                and volume.scope_key == scope_key
            ):
                continue
            _apply_work_fields(volume, fields)
            volume.project = target
            volume.save()
        _copy_legal_entities_for_work_scope(scope_key)
    if owner.pk not in {target.pk for target in targets}:
        for volume in list(WorkVolume.objects.filter(project_id=owner.pk, scope_key__isnull=False)):
            if WorkVolume.objects.filter(scope_key=volume.scope_key).exclude(project_id=owner.pk).exists():
                delete_work_volume_row(volume)


def backfill_service_scopes():
    owner_ids = []
    seen = set()
    rows = ProjectRegistration.objects.filter(
        pk__in=WorkVolume.objects.values("project_id")
    ).values_list("pk", "stage_project_id")
    for project_id, parent_id in rows:
        owner_id = parent_id or project_id
        if owner_id in seen:
            continue
        seen.add(owner_id)
        owner_ids.append(owner_id)
    for owner_id in owner_ids:
        owner = ProjectRegistration.objects.filter(pk=owner_id).first()
        if owner is not None:
            align_project_service_scope(owner)
