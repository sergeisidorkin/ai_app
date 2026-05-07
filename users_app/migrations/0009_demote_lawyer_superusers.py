from django.db import migrations


LAWYER_GROUP = "Юрист"
SUPERUSER_GROUPS = (
    "Администратор",
    "Директор",
    "Директор направления",
)


def demote_lawyer_superusers(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Employee = apps.get_model("users_app", "Employee")

    lawyer_user_ids = set(
        Employee.objects.filter(role=LAWYER_GROUP).values_list("user_id", flat=True)
    )
    lawyer_user_ids.update(
        User.objects.filter(groups__name=LAWYER_GROUP).values_list("pk", flat=True)
    )
    if not lawyer_user_ids:
        return

    keep_superuser_ids = set(
        Employee.objects.filter(
            user_id__in=lawyer_user_ids,
            role__in=SUPERUSER_GROUPS,
        ).values_list("user_id", flat=True)
    )
    keep_superuser_ids.update(
        User.objects.filter(
            pk__in=lawyer_user_ids,
            groups__name__in=SUPERUSER_GROUPS,
        ).values_list("pk", flat=True)
    )

    demote_user_ids = lawyer_user_ids - keep_superuser_ids
    if demote_user_ids:
        User.objects.filter(pk__in=demote_user_ids).update(is_superuser=False)


class Migration(migrations.Migration):

    dependencies = [
        ("users_app", "0008_employee_person_record_many_to_one"),
        ("policy_app", "0042_servicegoalreport_product_name_and_report_title_label"),
    ]

    operations = [
        migrations.RunPython(demote_lawyer_superusers, migrations.RunPython.noop),
    ]
