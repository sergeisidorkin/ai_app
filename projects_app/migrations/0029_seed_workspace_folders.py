from django.db import migrations


DEFAULT_FOLDERS = [
    (1, "00 Документы"),
    (1, "01 Командировки"),
    (1, "02 Письма"),
    (1, "03 Протоколы"),
    (1, "04 Запросы"),
    (1, "05 Исходные данные"),
    (1, "06 Отчеты"),
    (1, "07 Комментарии"),
    (1, "08 Результат"),
]


def seed(apps, schema_editor):
    Folder = apps.get_model("projects_app", "RegistrationWorkspaceFolder")
    if not Folder.objects.exists():
        Folder.objects.bulk_create(
            [Folder(level=lvl, name=name, position=i) for i, (lvl, name) in enumerate(DEFAULT_FOLDERS)]
        )


def unseed(apps, schema_editor):
    Folder = apps.get_model("projects_app", "RegistrationWorkspaceFolder")
    Folder.objects.filter(name__in=[n for _, n in DEFAULT_FOLDERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0028_registration_workspace_folder"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
