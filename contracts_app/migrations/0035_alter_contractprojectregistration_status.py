from django.db import migrations, models


DEFAULT_CONTRACT_PROJECT_STATUS = "Разрабатывается проект договора"


def migrate_contract_project_statuses(apps, schema_editor):
    ContractProjectRegistration = apps.get_model("contracts_app", "ContractProjectRegistration")
    ContractProjectRegistration.objects.exclude(
        status__in={
            DEFAULT_CONTRACT_PROJECT_STATUS,
            "Отправлен проект договора",
            "Договор подписан факсимиле",
            "Договор подписан ЭЦП",
            "Договор в 2 экз. отправлен почтой",
            "Договор в 2 экз. получен клиентом",
            "Договор с экз. IMCM отправлен почтой",
            "Договор с экз. IMCM получен",
        }
    ).update(status=DEFAULT_CONTRACT_PROJECT_STATUS)


class Migration(migrations.Migration):
    dependencies = [
        ("contracts_app", "0034_backfill_contract_project_short_uids"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contractprojectregistration",
            name="status",
            field=models.CharField(
                choices=[
                    ("Не начат", "Не начат"),
                    ("В работе", "В работе"),
                    ("На проверке", "На проверке"),
                    ("Завершён", "Завершён"),
                    ("Отложен", "Отложен"),
                ],
                default="Не начат",
                max_length=50,
                verbose_name="Статус",
            ),
        ),
        migrations.RunPython(migrate_contract_project_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contractprojectregistration",
            name="status",
            field=models.CharField(
                choices=[
                    ("Разрабатывается проект договора", "Разрабатывается проект договора"),
                    ("Отправлен проект договора", "Отправлен проект договора"),
                    ("Договор подписан факсимиле", "Договор подписан факсимиле"),
                    ("Договор подписан ЭЦП", "Договор подписан ЭЦП"),
                    ("Договор в 2 экз. отправлен почтой", "Договор в 2 экз. отправлен почтой"),
                    ("Договор в 2 экз. получен клиентом", "Договор в 2 экз. получен клиентом"),
                    ("Договор с экз. IMCM отправлен почтой", "Договор с экз. IMCM отправлен почтой"),
                    ("Договор с экз. IMCM получен", "Договор с экз. IMCM получен"),
                ],
                default="Разрабатывается проект договора",
                max_length=50,
                verbose_name="Статус",
            ),
        ),
    ]
