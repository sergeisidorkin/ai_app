from django.db import migrations, models
import django.db.models.deletion


def forward(apps, schema_editor):
    GroupMember = apps.get_model("group_app", "GroupMember")
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")

    country_counters = {}
    members_to_update = []
    first_member_by_alpha2 = {}

    for member in GroupMember.objects.order_by("position", "id"):
        country_key = (member.country_code or member.country_name or "").strip()
        next_number = country_counters.get(country_key, 0)
        if member.country_order_number != next_number:
            member.country_order_number = next_number
            members_to_update.append(member)
        country_counters[country_key] = next_number + 1
        alpha2 = (member.country_alpha2 or "").strip().upper()
        if alpha2 and alpha2 not in first_member_by_alpha2:
            first_member_by_alpha2[alpha2] = member

    if members_to_update:
        GroupMember.objects.bulk_update(members_to_update, ["country_order_number"])

    sequence_by_number = {}
    registrations_to_update = []
    pending_short_uids = {}

    for registration in ProjectRegistration.objects.order_by("number", "position", "id"):
        number_key = registration.number
        agreement_sequence = sequence_by_number.get(number_key, 0)
        sequence_by_number[number_key] = agreement_sequence + 1

        alpha2 = (registration.group or "").strip().upper()
        group_member = first_member_by_alpha2.get(alpha2)
        group_order_number = int(getattr(group_member, "country_order_number", 0) or 0)
        short_uid = f"{registration.number}{agreement_sequence}{group_order_number}{alpha2}"

        changed = False
        if registration.agreement_sequence != agreement_sequence:
            registration.agreement_sequence = agreement_sequence
            changed = True
        if registration.group_member_id != getattr(group_member, "pk", None):
            registration.group_member_id = getattr(group_member, "pk", None)
            changed = True
        if registration.short_uid != short_uid:
            pending_short_uids[registration.pk] = short_uid
            registration.short_uid = f"tmp{registration.pk}"
            changed = True

        if changed:
            registrations_to_update.append(registration)

    if registrations_to_update:
        ProjectRegistration.objects.bulk_update(
            registrations_to_update,
            ["group_member", "agreement_sequence", "short_uid"],
        )
        if pending_short_uids:
            for registration in registrations_to_update:
                if registration.pk in pending_short_uids:
                    registration.short_uid = pending_short_uids[registration.pk]
            ProjectRegistration.objects.bulk_update(registrations_to_update, ["short_uid"])


def backward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    seen = {}
    to_update = []
    pending_short_uids = {}

    for registration in ProjectRegistration.objects.order_by("number", "group", "position", "id"):
        key = (registration.number, registration.group)
        idx = seen.get(key, 0)
        seen[key] = idx + 1
        old_uid = f"{registration.number}{idx}{registration.group}"
        changed = False
        if registration.agreement_sequence != 0:
            registration.agreement_sequence = 0
            changed = True
        if registration.group_member_id is not None:
            registration.group_member_id = None
            changed = True
        if registration.short_uid != old_uid:
            pending_short_uids[registration.pk] = old_uid
            registration.short_uid = f"old{registration.pk}"
            changed = True
        if changed:
            to_update.append(registration)

    if to_update:
        ProjectRegistration.objects.bulk_update(
            to_update,
            ["group_member", "agreement_sequence", "short_uid"],
        )
        if pending_short_uids:
            for registration in to_update:
                if registration.pk in pending_short_uids:
                    registration.short_uid = pending_short_uids[registration.pk]
            ProjectRegistration.objects.bulk_update(to_update, ["short_uid"])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("group_app", "0007_groupmember_country_order_number"),
        ("projects_app", "0046_add_signed_scan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="agreement_sequence",
            field=models.PositiveIntegerField(db_index=True, default=0, editable=False, verbose_name="№ соглашения в проекте"),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="group_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="project_registrations",
                to="group_app.groupmember",
                verbose_name="Группа",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="projectregistration",
            name="project_registration_identity_unique",
        ),
        migrations.RunPython(forward, backward),
        migrations.AddConstraint(
            model_name="projectregistration",
            constraint=models.UniqueConstraint(
                fields=("number", "group_member", "agreement_type", "agreement_number"),
                name="project_registration_identity_unique",
            ),
        ),
    ]
