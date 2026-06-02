import uuid

from django.db import migrations, transaction


def _contract_project_sequence(contract_short_uid):
    digits = "".join(ch for ch in (contract_short_uid or "").strip().upper() if ch.isdigit())
    if len(digits) >= 6:
        return digits[4:6]
    return "00"


def _project_short_uid(registration, sequence, group_order_map, group_alpha2_map, contract_uid_map):
    alpha2 = (
        group_alpha2_map.get(registration.group_member_id)
        or (registration.group or "").strip().upper()
    )
    group_order_number = group_order_map.get(registration.group_member_id, 0)
    contract_sequence = _contract_project_sequence(
        contract_uid_map.get(registration.contract_project_registration_id, "")
    )
    return (
        f"{int(registration.number or 0):04d}"
        f"{contract_sequence}"
        f"{int(sequence or 0)}"
        f"{group_order_number}"
        f"{alpha2}"
    )


def forward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    GroupMember = apps.get_model("group_app", "GroupMember")
    ContractProjectRegistration = apps.get_model("contracts_app", "ContractProjectRegistration")

    group_order_map = {
        member.pk: int(member.country_order_number or 0)
        for member in GroupMember.objects.only("id", "country_order_number")
    }
    group_alpha2_map = {
        member.pk: (member.country_alpha2 or "").strip().upper()
        for member in GroupMember.objects.only("id", "country_alpha2")
    }
    contract_uid_map = {
        contract.pk: (contract.short_uid or "").strip().upper()
        for contract in ContractProjectRegistration.objects.only("id", "short_uid")
    }

    registrations = list(
        ProjectRegistration.objects
        .order_by("number", "position", "id")
        .only(
            "id",
            "number",
            "agreement_sequence",
            "group",
            "group_member_id",
            "contract_project_registration_id",
            "short_uid",
        )
    )
    if not registrations:
        return

    by_number = {}
    for registration in registrations:
        by_number.setdefault(registration.number, []).append(registration)

    pending = []
    for group in by_number.values():
        total_for_number = len(group)
        sequence_by_contract = {}
        for registration in group:
            if total_for_number == 1:
                sequence = 0
            else:
                contract_key = registration.contract_project_registration_id
                sequence_by_contract[contract_key] = sequence_by_contract.get(contract_key, 0) + 1
                sequence = sequence_by_contract[contract_key]

            new_uid = _project_short_uid(
                registration,
                sequence,
                group_order_map,
                group_alpha2_map,
                contract_uid_map,
            )
            if int(registration.agreement_sequence or 0) == sequence and registration.short_uid == new_uid:
                continue
            registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
            pending.append((registration, sequence, new_uid))

    if not pending:
        return

    with transaction.atomic():
        ProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])
        for registration, sequence, new_uid in pending:
            registration.agreement_sequence = sequence
            registration.short_uid = new_uid
        ProjectRegistration.objects.bulk_update(
            [item[0] for item in pending],
            ["agreement_sequence", "short_uid"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0080_backfill_contract_project_sequence_project_uids"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
