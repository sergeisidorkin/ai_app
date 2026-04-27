from django.db import migrations


CONTRACT_DETAILS_BINDINGS = {
    "{{full_name}}": "full_name",
    "{{full_name_genitive}}": "full_name_genitive",
    "{{citizenship_country}}": "citizenship_country",
    "{{citizenship_status}}": "citizenship_status",
    "{{citizenship_identifier}}": "citizenship_identifier",
    "{{citizenship_number}}": "citizenship_number",
    "{{self_employed}}": "self_employed",
    "{{tax_rate}}": "tax_rate",
    "{{citizenship}}": "citizenship",
    "{{gender}}": "gender",
    "{{inn}}": "inn",
    "{{snils}}": "snils",
    "{{birth_date}}": "birth_date",
    "{{passport_series}}": "passport_series",
    "{{passport_number}}": "passport_number",
    "{{passport_issued_by}}": "passport_issued_by",
    "{{passport_issue_date}}": "passport_issue_date",
    "{{passport_expiry}}": "passport_expiry",
    "{{passport_expiry_date}}": "passport_expiry",
    "{{passport_division_code}}": "passport_division_code",
    "{{registration_address}}": "registration_address",
    "{{bank_name}}": "bank_name",
    "{{swift}}": "swift",
    "{{bank_swift}}": "swift",
    "{{bank_inn}}": "bank_inn",
    "{{bik}}": "bik",
    "{{bank_bik}}": "bik",
    "{{settlement_account}}": "settlement_account",
    "{{correspondent_account}}": "correspondent_account",
    "{{corr_account}}": "correspondent_account",
    "{{bank_address}}": "bank_address",
    "{{corr_bank_name}}": "corr_bank_name",
    "{{corr_bank_address}}": "corr_bank_address",
    "{{corr_bank_bik}}": "corr_bank_bik",
    "{{corr_bank_swift}}": "corr_bank_swift",
    "{{corr_bank_settlement}}": "corr_bank_settlement",
    "{{corr_bank_settlement_account}}": "corr_bank_settlement",
    "{{corr_bank_correspondent}}": "corr_bank_correspondent",
    "{{corr_bank_corr_account}}": "corr_bank_correspondent",
}


def bind_contract_details_variables(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    for key, source_column in CONTRACT_DETAILS_BINDINGS.items():
        ContractVariable.objects.filter(key=key, is_computed=False).update(
            source_section="experts",
            source_table="contract_details",
            source_column=source_column,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0018_add_contract_proxy_models"),
    ]

    operations = [
        migrations.RunPython(bind_contract_details_variables, migrations.RunPython.noop),
    ]
