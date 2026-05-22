from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications_app", "0006_add_employee_scan_sent_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    (
                        "project_participation_confirmation",
                        "Запрос подтверждения участия в проекте",
                    ),
                    (
                        "project_info_request_approval",
                        "Согласование запроса информации",
                    ),
                    (
                        "project_contract_conclusion",
                        "Отправлен проект договора",
                    ),
                    (
                        "employee_scan_sent",
                        "Отправлен скан сотрудника",
                    ),
                    (
                        "project_payment_request",
                        "Заявка на оплату",
                    ),
                ],
                db_index=True,
                max_length=64,
                verbose_name="Тип уведомления",
            ),
        ),
    ]
