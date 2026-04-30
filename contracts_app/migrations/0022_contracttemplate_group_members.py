from django.db import migrations, models


def copy_contract_template_group_members(apps, schema_editor):
    ContractTemplate = apps.get_model("contracts_app", "ContractTemplate")
    through_model = ContractTemplate.group_members.through
    rows = []
    for template_id, group_member_id in (
        ContractTemplate.objects
        .exclude(group_member_id__isnull=True)
        .values_list("pk", "group_member_id")
    ):
        rows.append(
            through_model(
                contracttemplate_id=template_id,
                groupmember_id=group_member_id,
            )
        )
    if rows:
        through_model.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0021_correct_legacy_contract_variable_bindings"),
        ("group_app", "0007_groupmember_country_order_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="contracttemplate",
            name="group_members",
            field=models.ManyToManyField(
                blank=True,
                related_name="contract_template_sets",
                to="group_app.groupmember",
                verbose_name="Группы",
            ),
        ),
        migrations.RunPython(copy_contract_template_group_members, migrations.RunPython.noop),
    ]
