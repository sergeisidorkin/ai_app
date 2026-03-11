from django.db import migrations

ADMIN_ROLE = "Администратор"
EXPERT_ROLE = "Эксперт"


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ADMIN_ROLE)
    Group.objects.get_or_create(name=EXPERT_ROLE)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=[ADMIN_ROLE, EXPERT_ROLE]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0015_typicalsection_expertise_direction"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
