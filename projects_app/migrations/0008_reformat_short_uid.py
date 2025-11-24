from django.db import migrations


def forward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    seen = {}
    to_update = []

    for pr in ProjectRegistration.objects.order_by("number", "group", "position", "id"):
        key = (pr.number, pr.group)
        idx = seen.get(key, 0)
        new_uid = f"{pr.number}{idx}{pr.group}"
        if pr.short_uid != new_uid:
            pr.short_uid = new_uid
            to_update.append(pr)
        seen[key] = idx + 1

    if to_update:
        ProjectRegistration.objects.bulk_update(to_update, ["short_uid"])


def backward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    seen = {}
    to_update = []

    for pr in ProjectRegistration.objects.order_by("number", "group", "position", "id"):
        key = (pr.number, pr.group)
        idx = seen.get(key, 0)
        old_uid = f"{pr.number}{pr.group}-{idx}"
        if pr.short_uid != old_uid:
            pr.short_uid = old_uid
            to_update.append(pr)
        seen[key] = idx + 1

    if to_update:
        ProjectRegistration.objects.bulk_update(to_update, ["short_uid"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0007_projectregistration_short_uid"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]