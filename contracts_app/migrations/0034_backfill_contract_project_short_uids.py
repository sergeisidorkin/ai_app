import uuid
from collections import Counter

from django.db import migrations, transaction


def _contract_project_uid(registration, *, group_order_map, group_alpha2_map, proposal_sub_number_map):
    alpha2 = group_alpha2_map.get(registration.group_member_id) or (registration.group or "").strip().upper()
    group_order_number = group_order_map.get(registration.group_member_id, 0)
    proposal_sequence = proposal_sub_number_map.get(registration.proposal_registration_id, 0)
    formatted_number = f"{int(registration.number or 0):04d}"
    return f"{formatted_number}{int(proposal_sequence or 0)}{int(registration.sub_number or 0)}{group_order_number}{alpha2}"


def forward(apps, schema_editor):
    ContractProjectRegistration = apps.get_model("contracts_app", "ContractProjectRegistration")
    GroupMember = apps.get_model("group_app", "GroupMember")
    ProposalRegistration = apps.get_model("proposals_app", "ProposalRegistration")

    group_order_map = {
        member.pk: int(member.country_order_number or 0)
        for member in GroupMember.objects.only("id", "country_order_number")
    }
    group_alpha2_map = {
        member.pk: (member.country_alpha2 or "").strip().upper()
        for member in GroupMember.objects.only("id", "country_alpha2")
    }
    proposal_sub_number_map = {
        proposal.pk: int(proposal.sub_number or 0)
        for proposal in ProposalRegistration.objects.only("id", "sub_number")
    }

    registrations = list(
        ContractProjectRegistration.objects
        .order_by("id")
        .only(
            "id",
            "number",
            "sub_number",
            "group",
            "group_member_id",
            "proposal_registration_id",
            "short_uid",
        )
    )
    if not registrations:
        return

    new_uid_by_pk = {
        registration.pk: _contract_project_uid(
            registration,
            group_order_map=group_order_map,
            group_alpha2_map=group_alpha2_map,
            proposal_sub_number_map=proposal_sub_number_map,
        )
        for registration in registrations
    }
    duplicate_uids = sorted(
        uid
        for uid, count in Counter(new_uid_by_pk.values()).items()
        if count > 1
    )
    if duplicate_uids:
        raise ValueError(
            "Cannot backfill contract project IDs because the new format would create duplicates: "
            + ", ".join(duplicate_uids[:20])
        )

    pending = []
    for registration in registrations:
        new_uid = new_uid_by_pk[registration.pk]
        if registration.short_uid == new_uid:
            continue
        registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
        pending.append((registration, new_uid))

    if not pending:
        return

    with transaction.atomic():
        ContractProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])
        for registration, new_uid in pending:
            registration.short_uid = new_uid
        ContractProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0033_contract_project_registration_stage_payloads_json"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
