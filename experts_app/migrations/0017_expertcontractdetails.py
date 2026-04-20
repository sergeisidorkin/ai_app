from django.db import migrations, models
import django.db.models.deletion

import experts_app.models


def copy_contract_details_to_ctz(apps, schema_editor):
    ExpertProfile = apps.get_model("experts_app", "ExpertProfile")
    ExpertContractDetails = apps.get_model("experts_app", "ExpertContractDetails")
    CitizenshipRecord = apps.get_model("contacts_app", "CitizenshipRecord")

    contract_field_names = [
        "full_name_genitive",
        "self_employed",
        "tax_rate",
        "citizenship",
        "gender",
        "inn",
        "snils",
        "birth_date",
        "passport_series",
        "passport_number",
        "passport_issued_by",
        "passport_issue_date",
        "passport_expiry_date",
        "passport_division_code",
        "registration_address",
        "bank_name",
        "bank_swift",
        "bank_inn",
        "bank_bik",
        "settlement_account",
        "corr_account",
        "bank_address",
        "corr_bank_name",
        "corr_bank_address",
        "corr_bank_bik",
        "corr_bank_swift",
        "corr_bank_settlement_account",
        "corr_bank_corr_account",
        "facsimile_file",
    ]

    citizenships_by_person = {}
    for citizenship in CitizenshipRecord.objects.order_by("position", "id").all():
        citizenships_by_person.setdefault(citizenship.person_id, []).append(citizenship)

    to_create = []
    for profile in ExpertProfile.objects.order_by("position", "id").all():
        employee = getattr(profile, "employee", None)
        person_id = getattr(employee, "person_record_id", None) if employee else None
        if not person_id:
            continue
        citizenships = citizenships_by_person.get(person_id) or []
        if not citizenships:
            continue
        values = {name: getattr(profile, name) for name in contract_field_names}
        for citizenship in citizenships:
            to_create.append(
                ExpertContractDetails(
                    expert_profile_id=profile.pk,
                    citizenship_record_id=citizenship.pk,
                    **values,
                )
            )

    if to_create:
        ExpertContractDetails.objects.bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ("contacts_app", "0016_backfill_person_residence_addresses"),
        ("experts_app", "0016_remove_expertprofile_yandex_mail"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpertContractDetails",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name_genitive", models.CharField(blank=True, default="", max_length=512, verbose_name="ФИО (полное) родительный падеж")),
                ("self_employed", models.DateField(blank=True, null=True, verbose_name="Самозанятость (дата постановки на учет)")),
                ("tax_rate", models.PositiveIntegerField(blank=True, null=True, verbose_name="Ставка налога, %")),
                ("citizenship", models.CharField(blank=True, default="", max_length=255, verbose_name="Гражданство")),
                ("gender", models.CharField(blank=True, choices=[("male", "Мужской"), ("female", "Женский")], default="", max_length=10, verbose_name="Пол")),
                ("inn", models.CharField(blank=True, default="", max_length=50, verbose_name="ИНН")),
                ("snils", models.CharField(blank=True, default="", max_length=14, verbose_name="СНИЛС")),
                ("birth_date", models.DateField(blank=True, null=True, verbose_name="Дата рождения")),
                ("passport_series", models.CharField(blank=True, default="", max_length=50, verbose_name="Паспорт: серия")),
                ("passport_number", models.CharField(blank=True, default="", max_length=50, verbose_name="Паспорт: номер")),
                ("passport_issued_by", models.CharField(blank=True, default="", max_length=512, verbose_name="Паспорт: кем выдан")),
                ("passport_issue_date", models.DateField(blank=True, null=True, verbose_name="Паспорт: дата выдачи")),
                ("passport_expiry_date", models.DateField(blank=True, null=True, verbose_name="Паспорт: срок действия")),
                ("passport_division_code", models.CharField(blank=True, default="", max_length=50, verbose_name="Паспорт: код подразделения")),
                ("registration_address", models.CharField(blank=True, default="", max_length=512, verbose_name="Регистрация: адрес")),
                ("bank_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование банка")),
                ("bank_swift", models.CharField(blank=True, default="", max_length=50, verbose_name="SWIFT")),
                ("bank_inn", models.CharField(blank=True, default="", max_length=50, verbose_name="ИНН банка")),
                ("bank_bik", models.CharField(blank=True, default="", max_length=50, verbose_name="БИК")),
                ("settlement_account", models.CharField(blank=True, default="", max_length=50, verbose_name="Рас. счет")),
                ("corr_account", models.CharField(blank=True, default="", max_length=50, verbose_name="Кор. счет")),
                ("bank_address", models.CharField(blank=True, default="", max_length=512, verbose_name="Адрес банка")),
                ("corr_bank_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование банка-корреспондента")),
                ("corr_bank_address", models.CharField(blank=True, default="", max_length=512, verbose_name="Адрес банка-корреспондента")),
                ("corr_bank_bik", models.CharField(blank=True, default="", max_length=50, verbose_name="БИК банка-корреспондента")),
                ("corr_bank_swift", models.CharField(blank=True, default="", max_length=50, verbose_name="SWIFT банка-корреспондента")),
                ("corr_bank_settlement_account", models.CharField(blank=True, default="", max_length=50, verbose_name="Рас. счет банка-корреспондента")),
                ("corr_bank_corr_account", models.CharField(blank=True, default="", max_length=50, verbose_name="Кор. счет банка-корреспондента")),
                ("facsimile_file", models.FileField(blank=True, default="", upload_to=experts_app.models.expert_facsimile_upload_to, verbose_name="Факсимиле")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("citizenship_record", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="expert_contract_details", to="contacts_app.citizenshiprecord", verbose_name="ID-CTZ")),
                ("expert_profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contract_details_records", to="experts_app.expertprofile", verbose_name="Профиль эксперта")),
            ],
            options={
                "verbose_name": "Реквизиты физлица-исполнителя",
                "verbose_name_plural": "Реквизиты физлиц-исполнителей",
                "ordering": ["expert_profile__position", "citizenship_record__position", "citizenship_record_id", "id"],
            },
        ),
        migrations.RunPython(copy_contract_details_to_ctz, migrations.RunPython.noop),
        migrations.RemoveField(model_name="expertprofile", name="bank_address"),
        migrations.RemoveField(model_name="expertprofile", name="bank_bik"),
        migrations.RemoveField(model_name="expertprofile", name="bank_inn"),
        migrations.RemoveField(model_name="expertprofile", name="bank_name"),
        migrations.RemoveField(model_name="expertprofile", name="bank_swift"),
        migrations.RemoveField(model_name="expertprofile", name="birth_date"),
        migrations.RemoveField(model_name="expertprofile", name="citizenship"),
        migrations.RemoveField(model_name="expertprofile", name="corr_account"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_address"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_bik"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_corr_account"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_name"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_settlement_account"),
        migrations.RemoveField(model_name="expertprofile", name="corr_bank_swift"),
        migrations.RemoveField(model_name="expertprofile", name="facsimile_file"),
        migrations.RemoveField(model_name="expertprofile", name="full_name_genitive"),
        migrations.RemoveField(model_name="expertprofile", name="gender"),
        migrations.RemoveField(model_name="expertprofile", name="inn"),
        migrations.RemoveField(model_name="expertprofile", name="passport_division_code"),
        migrations.RemoveField(model_name="expertprofile", name="passport_expiry_date"),
        migrations.RemoveField(model_name="expertprofile", name="passport_issue_date"),
        migrations.RemoveField(model_name="expertprofile", name="passport_issued_by"),
        migrations.RemoveField(model_name="expertprofile", name="passport_number"),
        migrations.RemoveField(model_name="expertprofile", name="passport_series"),
        migrations.RemoveField(model_name="expertprofile", name="registration_address"),
        migrations.RemoveField(model_name="expertprofile", name="self_employed"),
        migrations.RemoveField(model_name="expertprofile", name="settlement_account"),
        migrations.RemoveField(model_name="expertprofile", name="snils"),
        migrations.RemoveField(model_name="expertprofile", name="tax_rate"),
    ]
