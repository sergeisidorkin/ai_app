import uuid

from django.db import migrations, transaction


SHARED_ATTNAMES = (
    "position",
    "number",
    "sub_number",
    "proposal_registration_id",
    "group",
    "group_member_id",
    "agreement_sequence",
    "agreement_type",
    "agreement_number",
    "name",
    "year",
    "country_id",
    "customer",
    "identifier",
    "registration_number",
    "registration_region",
    "registration_date",
    "asset_owner",
    "asset_owner_matches_customer",
    "asset_owner_country_id",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_region",
    "asset_owner_registration_date",
    "project_manager",
    "project_manager_prs_id",
    "project_coordinator",
    "project_coordinator_prs_id",
    "deadline",
    "evaluation_date",
    "contract_subject",
    "project_start_date",
)

MAX_PROJECT_STAGES = 9


def _stage_code(project_uid, digit):
    uid = str(project_uid or "")
    if len(uid) < 8:
        return uid
    return f"{uid[:7]}{digit}{uid[7:]}"


def _historical_group_label(row):
    member = row.group_member if row.group_member_id else None
    if member is not None:
        alpha2 = (member.country_alpha2 or "").strip().upper()
        if not alpha2:
            return ""
        if int(member.country_order_number or 0) == 0:
            return alpha2
        return f"{int(member.country_order_number or 0)}-{alpha2}"
    return (row.group or "").strip().upper()


def _historical_alpha2(row):
    member = row.group_member if row.group_member_id else None
    if member is not None:
        return (member.country_alpha2 or "").strip().upper()
    return (row.group or "").strip().upper()


def _historical_order(row):
    member = row.group_member if row.group_member_id else None
    if member is not None:
        return int(member.country_order_number or 0)
    return 0


def _historical_contract_sequence(row):
    if not row.contract_project_registration_id:
        return "00"
    contract = row.contract_project_registration
    short_uid = (getattr(contract, "short_uid", "") or "").strip().upper()
    digits = "".join(ch for ch in short_uid if ch.isdigit())
    if len(digits) >= 6:
        return digits[4:6]
    return "00"


def _historical_build_short_uid(row):
    return (
        f"{int(row.number or 0):04d}"
        f"{_historical_contract_sequence(row)}"
        f"{int(row.agreement_sequence or 0)}"
        f"{_historical_order(row)}"
        f"{_historical_alpha2(row)}"
    )


def _historical_refresh_stage_codes(model, project_ids):
    ids = []
    for project_id in project_ids:
        if project_id and project_id not in ids:
            ids.append(project_id)
    if not ids:
        return
    parents = {
        row.pk: row.short_uid
        for row in model.objects.filter(pk__in=ids, stage_project__isnull=True).only("id", "short_uid")
    }
    if not parents:
        return
    stages = list(
        model.objects.filter(stage_project_id__in=parents.keys())
        .order_by("stage_project_id", "position", "id")
        .only("id", "short_uid", "stage_project_id")
    )
    grouped = {}
    for stage in stages:
        grouped.setdefault(stage.stage_project_id, []).append(stage)
    pending = []
    for project_id, rows in grouped.items():
        uid = parents.get(project_id) or ""
        if len(uid) < 10:
            continue
        single = len(rows) == 1
        for index, stage in enumerate(rows, start=1):
            if not single and index > MAX_PROJECT_STAGES:
                continue
            digit = "0" if single else str(index)
            new_uid = _stage_code(uid, digit)
            if stage.short_uid == new_uid:
                continue
            stage.short_uid = f"tmp{stage.pk}{uuid.uuid4().hex[:8]}"
            pending.append((stage, new_uid))
    if not pending:
        return
    with transaction.atomic():
        model.objects.bulk_update([item[0] for item in pending], ["short_uid"])
        for stage, new_uid in pending:
            stage.short_uid = new_uid
        model.objects.bulk_update([item[0] for item in pending], ["short_uid"])


def _historical_refresh_number_sequences(model, numbers):
    normalized_numbers = []
    for number in numbers:
        if number is None:
            continue
        try:
            normalized_numbers.append(int(number))
        except (TypeError, ValueError):
            continue
    if not normalized_numbers:
        return

    registrations = list(
        model.objects
        .select_related("group_member", "contract_project_registration")
        .filter(number__in=set(normalized_numbers), stage_project__isnull=True)
        .order_by("number", "position", "id")
    )
    if not registrations:
        return

    by_number = {}
    for registration in registrations:
        by_number.setdefault(registration.number, []).append(registration)

    to_refresh = []
    for group in by_number.values():
        total_for_number = len(group)
        by_contract = {}
        for registration in group:
            by_contract.setdefault(registration.contract_project_registration_id, []).append(registration)
        for contract_group in by_contract.values():
            for index, registration in enumerate(contract_group, start=1):
                sequence = 0 if total_for_number == 1 else index
                current_sequence = int(registration.agreement_sequence or 0)
                registration.agreement_sequence = sequence
                new_uid = _historical_build_short_uid(registration)
                if current_sequence == sequence and registration.short_uid == new_uid:
                    continue
                registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
                to_refresh.append((registration, sequence, new_uid))

    if to_refresh:
        with transaction.atomic():
            model.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])
            for registration, sequence, new_uid in to_refresh:
                registration.agreement_sequence = sequence
                registration.short_uid = new_uid
            model.objects.bulk_update(
                [item[0] for item in to_refresh],
                ["agreement_sequence", "short_uid"],
            )
    _historical_refresh_stage_codes(model, [item.pk for item in registrations])


def convert_existing_registrations(apps=None):
    if apps is None:
        from projects_app.models import ProjectRegistration, RegistrationGroupSummaryState

        def row_group_label(row):
            return row.group_display

        def refresh_sequences(numbers):
            ProjectRegistration.refresh_number_sequences(numbers)

        def refresh_codes(parent_ids):
            ProjectRegistration._refresh_stage_codes(parent_ids)
    else:
        ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
        RegistrationGroupSummaryState = apps.get_model("projects_app", "RegistrationGroupSummaryState")

        def row_group_label(row):
            return _historical_group_label(row)

        def refresh_sequences(numbers):
            _historical_refresh_number_sequences(ProjectRegistration, numbers)

        def refresh_codes(parent_ids):
            _historical_refresh_stage_codes(ProjectRegistration, parent_ids)

    rows = list(
        ProjectRegistration.objects.select_related("group_member").order_by("position", "id")
    )
    pending = [row for row in rows if row.stage_project_id is None and not row.stages.exists()]
    if not pending:
        return

    originals = {row.pk: row.short_uid for row in pending}
    for row in pending:
        row.short_uid = f"tmp{row.pk}{uuid.uuid4().hex[:8]}"
    ProjectRegistration.objects.bulk_update(pending, ["short_uid"])

    groups = []
    singles = []
    start = 0
    while start < len(pending):
        number = pending[start].number
        label = row_group_label(pending[start])
        end = start + 1
        while (
            end < len(pending)
            and pending[end].number == number
            and row_group_label(pending[end]) == label
        ):
            end += 1
        block = pending[start:end]
        if len(block) >= 2:
            groups.append((block, label))
        else:
            singles.append(block[0])
        start = end

    deferred_keys = set(
        RegistrationGroupSummaryState.objects.filter(deferred=True).values_list("number", "group_label")
    )

    def make_parent(source, short_uid, contract_id, deferred):
        parent = ProjectRegistration(status="Не начат", summary_deferred=deferred)
        for name in SHARED_ATTNAMES:
            setattr(parent, name, getattr(source, name))
        parent.contract_project_registration_id = contract_id
        parent.short_uid = short_uid
        parent.type_id = None
        parent.position = source.position
        parent.save_base(raw=True)
        return parent

    single_parents = []
    for block, label in groups:
        contract_ids = {item.contract_project_registration_id for item in block}
        contract_id = next(iter(contract_ids)) if len(contract_ids) == 1 else None
        parent = make_parent(
            block[0],
            f"mig{uuid.uuid4().hex[:16]}",
            contract_id,
            (block[0].number, label) in deferred_keys,
        )
        ProjectRegistration.objects.filter(pk__in=[item.pk for item in block]).update(stage_project_id=parent.pk)

    for row in singles:
        parent = make_parent(row, originals[row.pk], row.contract_project_registration_id, False)
        ProjectRegistration.objects.filter(pk=row.pk).update(stage_project_id=parent.pk)
        single_parents.append((parent.pk, originals[row.pk]))

    refresh_sequences({row.number for row in pending})
    restore = []
    for parent_id, original_uid in single_parents:
        parent = ProjectRegistration.objects.get(pk=parent_id)
        if parent.short_uid == original_uid:
            continue
        parent.short_uid = f"tmp{parent.pk}{uuid.uuid4().hex[:8]}"
        restore.append((parent, original_uid))
    if restore:
        ProjectRegistration.objects.bulk_update([item[0] for item in restore], ["short_uid"])
        for parent, original_uid in restore:
            parent.short_uid = original_uid
        ProjectRegistration.objects.bulk_update([item[0] for item in restore], ["short_uid"])
        refresh_codes([item[0].pk for item in restore])


def migrate_project_stages(apps, schema_editor):
    convert_existing_registrations(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0121_project_stage_link"),
    ]

    operations = [
        migrations.RunPython(migrate_project_stages, migrations.RunPython.noop),
    ]
