from django.db import migrations, models
from django.db.models import Max


DEFAULT_PERMISSIONS = {
    "Координатор": [
        "view_project",
        "view_reports",
        "upload_full_report",
        "upload_free_sections",
        "review_kp",
        "executor_lock",
    ],
    "Руководитель проекта": [
        "view_project",
        "view_reports",
        "upload_full_report",
        "review_rp",
        "checklist_approve",
        "nextcloud_editor",
        "worktime_auto",
        "executor_lock",
    ],
}


def seed_project_permissions(apps, schema_editor):
    ExpertSpecialty = apps.get_model("experts_app", "ExpertSpecialty")
    for name, permissions in DEFAULT_PERMISSIONS.items():
        specialty = ExpertSpecialty.objects.filter(specialty=name).first()
        if specialty is None:
            last_position = ExpertSpecialty.objects.aggregate(value=Max("position"))["value"] or 0
            ExpertSpecialty.objects.create(
                specialty=name,
                grants_project_rights=True,
                project_permissions=permissions,
                is_group_owner=True,
                position=last_position + 1,
            )
            continue
        specialty.grants_project_rights = True
        if not specialty.project_permissions:
            specialty.project_permissions = permissions
        specialty.save(update_fields=["grants_project_rights", "project_permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0025_expertspecialty_grants_project_rights"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertspecialty",
            name="project_permissions",
            field=models.JSONField(blank=True, db_default=[], default=list, verbose_name="Права и доступы в проекте"),
        ),
        migrations.RunPython(seed_project_permissions, migrations.RunPython.noop),
    ]
