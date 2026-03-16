from django.db import migrations

DEFAULT_SUBJECTS = {
    "participation_confirmation": "Запрос подтверждения участия в проекте {project_label}",
    "contract_sending": "Проект договора по проекту {project_label}",
    "project_start": "Начало работ по проекту {project_label}",
    "request_approval": "Согласование запроса по проекту {project_label}",
}


def populate_subjects(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    for ttype, subject in DEFAULT_SUBJECTS.items():
        LetterTemplate.objects.filter(
            template_type=ttype, is_default=True
        ).update(subject_template=subject)


def clear_subjects(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(is_default=True).update(subject_template="")


class Migration(migrations.Migration):
    dependencies = [
        ("letters_app", "0003_add_subject_template"),
    ]

    operations = [
        migrations.RunPython(populate_subjects, clear_subjects),
    ]
