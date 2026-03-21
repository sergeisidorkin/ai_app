from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications_app", "0005_add_contracts_related_section"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                "Тип уведомления",
                max_length=64,
                choices=[
                    ("project_participation_confirmation", "Запрос подтверждения участия в проекте"),
                    ("project_info_request_approval", "Согласование запроса информации"),
                    ("project_contract_conclusion", "Отправлен проект договора"),
                    ("employee_scan_sent", "Отправлен скан сотрудника"),
                ],
                db_index=True,
            ),
        ),
    ]
