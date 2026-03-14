from django.db import migrations

DIRECTOR_ROLE = "Директор"


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=DIRECTOR_ROLE)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=DIRECTOR_ROLE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0016_create_groups_admin_expert"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
