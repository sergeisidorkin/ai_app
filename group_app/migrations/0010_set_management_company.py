from django.db import migrations

DIRECTOR_ROLE = "Директор"


def set_management_company(apps, schema_editor):
    """Включает УК у компании, чьё подразделение уровня 1 уже стоит у направления и имеет директора.

    Если такая компания не одна, галочку не ставим.
    """
    GroupMember = apps.get_model("group_app", "GroupMember")
    OrgUnit = apps.get_model("group_app", "OrgUnit")
    ExpertiseDirection = apps.get_model("policy_app", "ExpertiseDirection")
    Employee = apps.get_model("users_app", "Employee")

    company_ids = set()
    department_ids = ExpertiseDirection.objects.exclude(department_id=None).values_list(
        "department_id", flat=True
    )
    for unit in OrgUnit.objects.filter(pk__in=department_ids, level=1):
        if Employee.objects.filter(department_id=unit.pk, role=DIRECTOR_ROLE).exists():
            company_ids.add(unit.company_id)
    if len(company_ids) == 1:
        GroupMember.objects.filter(pk=company_ids.pop()).update(is_management_company=True)


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0009_groupmember_is_management_company"),
        ("policy_app", "0053_expertisedirection_department"),
        ("users_app", "0009_demote_lawyer_superusers"),
    ]

    operations = [
        migrations.RunPython(set_management_company, migrations.RunPython.noop),
    ]
