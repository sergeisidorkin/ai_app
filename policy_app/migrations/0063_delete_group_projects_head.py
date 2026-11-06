from django.db import migrations


ROLE_NAME = "Руководитель проектов"


def delete_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Employee = apps.get_model("users_app", "Employee")
    Employee.objects.filter(role=ROLE_NAME).update(role="")
    Group.objects.filter(name=ROLE_NAME).delete()


def restore_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ROLE_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0062_delete_group_projects_coordinator"),
    ]

    operations = [
        migrations.RunPython(delete_group, restore_group),
    ]
