import uuid

from django.db import migrations


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


def convert_existing_registrations():
    from projects_app.models import ProjectRegistration, RegistrationGroupSummaryState

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
        label = pending[start].group_display
        end = start + 1
        while (
            end < len(pending)
            and pending[end].number == number
            and pending[end].group_display == label
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

    ProjectRegistration.refresh_number_sequences({row.number for row in pending})
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
        ProjectRegistration._refresh_stage_codes([item[0].pk for item in restore])



def migrate_project_stages(apps, schema_editor):
    convert_existing_registrations()


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0121_project_stage_link"),
    ]

    operations = [
        migrations.RunPython(migrate_project_stages, migrations.RunPython.noop),
    ]
