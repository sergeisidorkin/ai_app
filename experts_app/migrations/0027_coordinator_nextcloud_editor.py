from django.db import migrations


COORDINATOR_SPECIALTY = "Координатор"
NEXTCLOUD_EDITOR = "nextcloud_editor"
PREVIOUS_PERMISSIONS = [
    "view_project",
    "view_reports",
    "upload_full_report",
    "upload_free_sections",
    "review_kp",
    "executor_lock",
]
DEFAULT_PERMISSIONS = [
    "view_project",
    "view_reports",
    "upload_full_report",
    "upload_free_sections",
    "review_kp",
    "nextcloud_editor",
    "executor_lock",
]


def grant_coordinator_nextcloud_editor(apps, schema_editor):
    ExpertSpecialty = apps.get_model("experts_app", "ExpertSpecialty")
    for specialty in ExpertSpecialty.objects.filter(specialty=COORDINATOR_SPECIALTY):
        current = list(specialty.project_permissions or [])
        if current == PREVIOUS_PERMISSIONS or not current:
            updated = DEFAULT_PERMISSIONS
        elif NEXTCLOUD_EDITOR not in current:
            updated = list(current)
            if "executor_lock" in updated:
                updated.insert(updated.index("executor_lock"), NEXTCLOUD_EDITOR)
            else:
                updated.append(NEXTCLOUD_EDITOR)
        else:
            continue
        specialty.project_permissions = updated
        specialty.save(update_fields=["project_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0026_expertspecialty_project_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_coordinator_nextcloud_editor, migrations.RunPython.noop),
    ]
