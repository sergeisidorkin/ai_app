from django.db import migrations, models


def migrate_contract_notifications_forward(apps, schema_editor):
    Notification = apps.get_model("notifications_app", "Notification")
    Notification.objects.filter(
        notification_type="project_contract_conclusion",
        related_section="projects",
    ).update(related_section="contracts")


def migrate_contract_notifications_backward(apps, schema_editor):
    Notification = apps.get_model("notifications_app", "Notification")
    Notification.objects.filter(
        notification_type="project_contract_conclusion",
        related_section="contracts",
    ).update(related_section="projects")


class Migration(migrations.Migration):

    dependencies = [
        ("notifications_app", "0004_add_contract_conclusion_notification_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="related_section",
            field=models.CharField(
                choices=[
                    ("none", "Не указан"),
                    ("projects", "Проекты"),
                    ("checklists", "Чек-листы"),
                    ("contracts", "Договоры"),
                ],
                db_index=True,
                default="none",
                max_length=32,
                verbose_name="Раздел",
            ),
        ),
        migrations.RunPython(
            migrate_contract_notifications_forward,
            migrate_contract_notifications_backward,
        ),
    ]
