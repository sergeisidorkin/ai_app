# Generated manually

from django.db import migrations, models


SEED_VARIABLES = [
    ("{{full_name}}", "ФИО"),
    ("{{full_name_genitive}}", "ФИО (полное) род. падеж"),
    ("{{self_employed}}", "Самозан."),
    ("{{tax_rate}}", "Налог"),
    ("{{citizenship}}", "Гражданство"),
    ("{{gender}}", "Пол"),
    ("{{inn}}", "ИНН"),
    ("{{snils}}", "СНИЛС"),
    ("{{birth_date}}", "Дата рожд."),
    ("{{passport_series}}", "Паспорт: серия"),
    ("{{passport_number}}", "номер"),
    ("{{passport_issued_by}}", "кем выдан"),
    ("{{passport_issue_date}}", "дата выдачи"),
    ("{{passport_expiry_date}}", "срок действия"),
    ("{{passport_division_code}}", "код подразд."),
    ("{{registration_address}}", "адрес регистрации"),
    ("{{bank_name}}", "Наименование банка"),
    ("{{bank_swift}}", "SWIFT"),
    ("{{bank_inn}}", "ИНН банка"),
    ("{{bank_bik}}", "БИК"),
    ("{{settlement_account}}", "Рас. счет"),
    ("{{corr_account}}", "Кор. счет"),
    ("{{bank_address}}", "Адрес банка"),
    ("{{corr_bank_name}}", "Наим. банка-корр."),
    ("{{corr_bank_address}}", "Адрес банка-корр."),
    ("{{corr_bank_bik}}", "БИК банка-корр."),
    ("{{corr_bank_swift}}", "SWIFT банка-корр."),
    ("{{corr_bank_settlement_account}}", "Рас. счет банка-корр."),
    ("{{corr_bank_corr_account}}", "Кор. счет банка-корр."),
]


def seed_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    for idx, (key, desc) in enumerate(SEED_VARIABLES):
        ContractVariable.objects.create(key=key, description=desc, position=idx)


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=255, verbose_name="Переменная")),
                ("description", models.CharField(blank=True, default="", max_length=512, verbose_name="Описание")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Переменная шаблона",
                "verbose_name_plural": "Переменные шаблонов",
                "ordering": ["position", "id"],
            },
        ),
        migrations.RunPython(seed_variables, migrations.RunPython.noop),
    ]
