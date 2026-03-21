from django.db import migrations


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Юрист")


def remove_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Юрист").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0024_add_expertise_dir_to_typical_section"),
    ]

    operations = [
        migrations.RunPython(create_group, remove_group),
    ]
