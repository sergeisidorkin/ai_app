import uuid

from django.db import migrations, models


REGISTRATION_COPY_FIELDS = [
    "number",
    "group",
    "group_member_id",
    "agreement_type",
    "agreement_number",
    "name",
    "status",
    "contract_start",
    "contract_end",
    "completion_calc",
    "input_data",
    "stage1_weeks",
    "stage1_end",
    "stage2_weeks",
    "stage2_end",
    "stage3_weeks",
    "term_weeks",
    "deadline",
    "year",
    "country_id",
    "customer",
    "identifier",
    "registration_number",
    "registration_date",
    "project_manager",
    "project_manager_prs_id",
    "contract_subject",
]


def _short_uid_for(registration, sequence):
    group_member = getattr(registration, "group_member", None)
    if group_member:
        alpha2 = (group_member.country_alpha2 or "").strip().upper()
        group_order = int(group_member.country_order_number or 0)
    else:
        alpha2 = (registration.group or "").strip().upper()
        group_order = 0
    return f"{int(registration.number or 0):04d}{sequence}{group_order}{alpha2}"


def _refresh_registration_sequences(ProjectRegistration):
    registrations = list(
        ProjectRegistration.objects
        .select_related("group_member")
        .order_by("number", "position", "id")
    )
    by_number = {}
    for registration in registrations:
        by_number.setdefault(registration.number, []).append(registration)

    pending = []
    for group in by_number.values():
        total = len(group)
        for index, registration in enumerate(group, start=1):
            sequence = 0 if total == 1 else index
            new_uid = _short_uid_for(registration, sequence)
            if registration.agreement_sequence == sequence and registration.short_uid == new_uid:
                continue
            registration.agreement_sequence = sequence
            registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
            pending.append((registration, new_uid))

    if not pending:
        return

    ProjectRegistration.objects.bulk_update([item[0] for item in pending], ["short_uid"])
    for registration, new_uid in pending:
        registration.short_uid = new_uid
    ProjectRegistration.objects.bulk_update(
        [item[0] for item in pending],
        ["agreement_sequence", "short_uid"],
    )


def split_project_registration_products(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    ProjectRegistrationProduct = apps.get_model("projects_app", "ProjectRegistrationProduct")

    position = 1
    registrations = list(ProjectRegistration.objects.order_by("position", "id"))
    for registration in registrations:
        links = list(
            ProjectRegistrationProduct.objects
            .filter(registration_id=registration.pk)
            .order_by("rank", "id")
        )

        registration.position = position
        update_fields = ["position"]
        if links:
            registration.type_id = links[0].product_id
            update_fields.append("type_id")
        registration.save(update_fields=update_fields)
        position += 1

        if not links:
            continue

        first_link = links[0]
        if first_link.rank != 1:
            first_link.rank = 1
            first_link.save(update_fields=["rank"])

        for link in links[1:]:
            clone_values = {
                field_name: getattr(registration, field_name)
                for field_name in REGISTRATION_COPY_FIELDS
            }
            clone = ProjectRegistration(
                **clone_values,
                position=position,
                agreement_sequence=0,
                type_id=link.product_id,
                short_uid=f"tmp{registration.pk}{link.product_id}{uuid.uuid4().hex[:8]}",
            )
            clone.save()
            ProjectRegistrationProduct.objects.create(
                registration_id=clone.pk,
                product_id=link.product_id,
                rank=1,
            )
            position += 1

        ProjectRegistrationProduct.objects.filter(
            registration_id=registration.pk,
        ).exclude(pk=first_link.pk).delete()

    _refresh_registration_sequences(ProjectRegistration)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0060_alter_performer_contract_signing_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectregistration",
            name="agreement_sequence",
            field=models.PositiveIntegerField(
                db_index=True,
                default=0,
                editable=False,
                verbose_name="№ этапа-продукта",
            ),
        ),
        migrations.RunPython(split_project_registration_products, noop_reverse),
    ]
