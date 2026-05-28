import uuid

from django.db import migrations, transaction


PROPOSAL_IDENTIFIER_FIELDS = (
    "proposal_workspace_disk_path",
    "proposal_workspace_target_path",
    "docx_file_link",
    "pdf_file_link",
    "docx_file_name",
    "pdf_file_name",
)


def _proposal_uid(registration, *, group_order_map, group_alpha2_map, include_sub_number):
    alpha2 = group_alpha2_map.get(registration.group_member_id) or (registration.group or "").strip().upper()
    group_order_number = group_order_map.get(registration.group_member_id, 0)
    formatted_number = f"{int(registration.number or 0):04d}"
    if include_sub_number:
        return f"{formatted_number}{int(registration.sub_number or 0)}{group_order_number}{alpha2}"
    return f"{formatted_number}{group_order_number}{alpha2}"


def _replace_identifier(value, identifiers, new_uid):
    text = str(value or "")
    if not text:
        return text
    result = text
    for identifier in sorted(identifiers, key=len, reverse=True):
        if identifier and identifier != new_uid:
            result = result.replace(identifier, new_uid)
    return result


def forward(apps, schema_editor):
    ProposalRegistration = apps.get_model("proposals_app", "ProposalRegistration")
    GroupMember = apps.get_model("group_app", "GroupMember")

    group_order_map = {
        member.pk: int(member.country_order_number or 0)
        for member in GroupMember.objects.only("id", "country_order_number")
    }
    group_alpha2_map = {
        member.pk: (member.country_alpha2 or "").strip().upper()
        for member in GroupMember.objects.only("id", "country_alpha2")
    }

    proposals = list(
        ProposalRegistration.objects
        .order_by("id")
        .only(
            "id",
            "number",
            "sub_number",
            "group",
            "group_member_id",
            "short_uid",
            *PROPOSAL_IDENTIFIER_FIELDS,
        )
    )
    if not proposals:
        return

    pending = []
    temp_uid_updates = []
    for proposal in proposals:
        legacy_uid = _proposal_uid(
            proposal,
            group_order_map=group_order_map,
            group_alpha2_map=group_alpha2_map,
            include_sub_number=False,
        )
        new_uid = _proposal_uid(
            proposal,
            group_order_map=group_order_map,
            group_alpha2_map=group_alpha2_map,
            include_sub_number=True,
        )
        current_uid = str(proposal.short_uid or "").strip()
        identifiers = {legacy_uid, current_uid}
        field_updates = {
            field: _replace_identifier(getattr(proposal, field), identifiers, new_uid)
            for field in PROPOSAL_IDENTIFIER_FIELDS
        }
        needs_uid_update = current_uid != new_uid
        needs_field_update = any(getattr(proposal, field) != value for field, value in field_updates.items())
        if not needs_uid_update and not needs_field_update:
            continue

        if needs_uid_update:
            proposal.short_uid = f"tmp{proposal.pk}{uuid.uuid4().hex[:8]}"
            temp_uid_updates.append(proposal)
        pending.append((proposal, new_uid, field_updates))

    if not pending:
        return

    with transaction.atomic():
        if temp_uid_updates:
            ProposalRegistration.objects.bulk_update(temp_uid_updates, ["short_uid"])
        for proposal, new_uid, field_updates in pending:
            proposal.short_uid = new_uid
            for field, value in field_updates.items():
                setattr(proposal, field, value)
        ProposalRegistration.objects.bulk_update(
            [item[0] for item in pending],
            ["short_uid", *PROPOSAL_IDENTIFIER_FIELDS],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("group_app", "0008_groupmember_seal_file"),
        ("proposals_app", "0053_proposalregistration_sub_number"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
