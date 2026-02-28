from django.db import migrations

ROLE_NAME = "Руководитель направления"


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ROLE_NAME)


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=ROLE_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0006_sectionstructure"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
