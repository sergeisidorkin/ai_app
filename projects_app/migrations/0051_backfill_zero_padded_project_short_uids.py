from django.db import migrations, transaction
import uuid


def forward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    GroupMember = apps.get_model("group_app", "GroupMember")

    group_order_map = {
        member.pk: int(member.country_order_number or 0)
        for member in GroupMember.objects.only("id", "country_order_number")
    }
    group_alpha2_map = {
        member.pk: (member.country_alpha2 or "").strip().upper()
        for member in GroupMember.objects.only("id", "country_alpha2")
    }

    registrations = list(
        ProjectRegistration.objects
        .order_by("id")
        .only("id", "number", "agreement_sequence", "group", "group_member_id")
    )
    if not registrations:
        return

    pending = []
    for registration in registrations:
        alpha2 = group_alpha2_map.get(registration.group_member_id) or (registration.group or "").strip().upper()
        group_order_number = group_order_map.get(registration.group_member_id, 0)
        new_uid = f"{int(registration.number or 0):04d}{registration.agreement_sequence}{group_order_number}{alpha2}"
        if registration.short_uid == new_uid:
            continue
        registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
        pending.append((registration, new_uid))

    if not pending:
        return

    with transaction.atomic():
        ProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])
        for registration, new_uid in pending:
            registration.short_uid = new_uid
        ProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])


class Migration(migrations.Migration):
    dependencies = [
        ("group_app", "0007_groupmember_country_order_number"),
        ("projects_app", "0050_alter_projectregistration_number_range"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
