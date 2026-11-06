from django.db import migrations


ROLE_NAME = "Координатор проектов"


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
        ("policy_app", "0061_alter_typicalsection_name_en_and_more"),
        ("users_app", "0009_demote_lawyer_superusers"),
    ]

    operations = [
        migrations.RunPython(delete_group, restore_group),
    ]
