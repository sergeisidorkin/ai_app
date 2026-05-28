from __future__ import annotations


PROPOSAL_REGISTRY_COLUMNS = [
    {
        "picker_value": "number",
        "data_col": "number",
        "source_column": "number",
        "label": "Номер",
        "variable_available": True,
    },
    {
        "picker_value": "sub-number",
        "data_col": "sub-number",
        "source_column": "sub_number",
        "label": "№",
        "variable_available": True,
    },
    {
        "picker_value": "group",
        "data_col": "group",
        "source_column": "group",
        "label": "Группа",
        "variable_available": True,
    },
    {
        "picker_value": "tkp-id",
        "data_col": "tkp-id",
        "source_column": "tkp_id",
        "label": "ТКП ID",
        "variable_available": True,
    },
    {
        "picker_value": "type",
        "data_col": "type",
        "source_column": "type",
        "label": "Тип",
        "variable_available": True,
    },
    {
        "picker_value": "name",
        "data_col": "name",
        "source_column": "name",
        "label": "Название",
        "variable_available": True,
    },
    {
        "picker_value": "kind",
        "data_col": "kind",
        "source_column": "kind",
        "label": "Вид",
        "variable_available": True,
    },
    {
        "picker_value": "status",
        "data_col": "status",
        "source_column": "status",
        "label": "Статус",
        "variable_available": True,
    },
    {
        "picker_value": "year",
        "data_col": "year",
        "source_column": "year",
        "label": "Год",
        "variable_available": True,
    },
    {
        "picker_value": "customer",
        "data_col": "customer",
        "source_column": "customer",
        "label": "Заказчик: наименование",
        "split_prefix": "Заказчик: ",
        "split_suffix": "наименование",
        "split_inline": True,
        "variable_available": True,
    },
    {
        "picker_value": "country",
        "data_col": "country",
        "source_column": "country",
        "label": "Заказчик: страна",
        "split_prefix": "Заказчик: ",
        "split_suffix": "страна",
        "variable_available": True,
    },
    {
        "picker_value": "identifier",
        "data_col": "identifier",
        "source_column": "identifier",
        "label": "Заказчик: идент.",
        "split_prefix": "Заказчик: ",
        "split_suffix": "идент.",
        "variable_available": True,
    },
    {
        "picker_value": "reg-number",
        "data_col": "reg-number",
        "source_column": "registration_number",
        "label": "Заказчик: регистр. номер",
        "split_prefix": "Заказчик: ",
        "split_suffix": "регистр. номер",
        "variable_available": True,
    },
    {
        "picker_value": "region",
        "data_col": "region",
        "source_column": "registration_region",
        "label": "Заказчик: регион",
        "split_prefix": "Заказчик: ",
        "split_suffix": "регион",
        "split_inline": True,
        "variable_available": True,
    },
    {
        "picker_value": "date",
        "data_col": "date",
        "source_column": "date",
        "label": "Заказчик: дата регистр.",
        "split_prefix": "Заказчик: ",
        "split_suffix": "дата регистр.",
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner",
        "data_col": "asset-owner",
        "source_column": "asset_owner",
        "label": "Владелец: наименование",
        "split_prefix": "Владелец: ",
        "split_suffix": "наименование",
        "split_inline": True,
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner-country",
        "data_col": "asset-owner-country",
        "source_column": "asset_owner_country",
        "label": "Владелец: страна",
        "split_prefix": "Владелец: ",
        "split_suffix": "страна",
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner-identifier",
        "data_col": "asset-owner-identifier",
        "source_column": "asset_owner_identifier",
        "label": "Владелец: идент.",
        "split_prefix": "Владелец: ",
        "split_suffix": "идент.",
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner-reg-number",
        "data_col": "asset-owner-reg-number",
        "source_column": "asset_owner_registration_number",
        "label": "Владелец: регистр. номер",
        "split_prefix": "Владелец: ",
        "split_suffix": "регистр. номер",
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner-region",
        "data_col": "asset-owner-region",
        "source_column": "asset_owner_region",
        "label": "Владелец: регион",
        "split_prefix": "Владелец: ",
        "split_suffix": "регион",
        "split_inline": True,
        "variable_available": True,
    },
    {
        "picker_value": "asset-owner-date",
        "data_col": "asset-owner-date",
        "source_column": "asset_owner_registration_date",
        "label": "Владелец: дата регистр.",
        "split_prefix": "Владелец: ",
        "split_suffix": "дата регистр.",
        "variable_available": True,
    },
    {
        "picker_value": "proposal-project-name",
        "data_col": "proposal-project-name",
        "source_column": "proposal_project_name",
        "label": "Наименование ТКП (проекта)",
        "variable_available": True,
    },
    {
        "picker_value": "purpose",
        "data_col": "purpose",
        "source_column": "purpose",
        "label": "Цель",
        "variable_available": True,
    },
    {
        "picker_value": "service-composition",
        "data_col": "service-composition",
        "source_column": "service_composition",
        "label": "Состав услуг",
        "variable_available": True,
    },
    {
        "picker_value": "evaluation-date",
        "data_col": "evaluation-date",
        "source_column": "evaluation_date",
        "label": "Дата оценки",
        "variable_available": True,
    },
    {
        "picker_value": "term",
        "data_col": "term",
        "source_column": "term",
        "label": "Срок предв. отчёта, мес.",
        "variable_available": True,
    },
    {
        "picker_value": "preliminary-report-date",
        "data_col": "preliminary-report-date",
        "source_column": "preliminary_report_date",
        "label": "Дата предв. отчёта",
        "variable_available": True,
    },
    {
        "picker_value": "final-report-weeks",
        "data_col": "final-report-weeks",
        "source_column": "final_report_term_weeks",
        "label": "Срок итог. отчёта, нед.",
        "variable_available": True,
    },
    {
        "picker_value": "final-report-date",
        "data_col": "final-report-date",
        "source_column": "final_report_date",
        "label": "Дата итог. отчёта",
        "variable_available": True,
    },
    {
        "picker_value": "report-languages",
        "data_col": "report-languages",
        "source_column": "report_languages",
        "label": "Языки отчёта",
        "variable_available": True,
    },
    {
        "picker_value": "service-cost",
        "data_col": "service-cost",
        "source_column": "service_cost",
        "label": "Стоимость услуг",
        "variable_available": True,
    },
    {
        "picker_value": "currency",
        "data_col": "currency",
        "source_column": "currency",
        "label": "Валюта",
        "variable_available": True,
    },
    {
        "picker_value": "advance-percent",
        "data_col": "advance-percent",
        "source_column": "advance_percent",
        "label": "Предоплата, проц.",
        "variable_available": True,
    },
    {
        "picker_value": "advance-term",
        "data_col": "advance-term",
        "source_column": "advance_term",
        "label": "Предоплата, срок дн.",
        "variable_available": True,
    },
    {
        "picker_value": "preliminary-report-percent",
        "data_col": "preliminary-report-percent",
        "source_column": "preliminary_report_percent",
        "label": "Предв. отчёт, проц.",
        "variable_available": True,
    },
    {
        "picker_value": "preliminary-report-term",
        "data_col": "preliminary-report-term",
        "source_column": "preliminary_report_term",
        "label": "Предв. отчёт, срок дн.",
        "variable_available": True,
    },
    {
        "picker_value": "final-report-percent",
        "data_col": "final-report-percent",
        "source_column": "final_report_percent",
        "label": "Итог. отчёт, проц.",
        "variable_available": True,
    },
    {
        "picker_value": "final-report-term",
        "data_col": "final-report-term",
        "source_column": "final_report_term",
        "label": "Итог. отчёт, срок дн.",
        "variable_available": True,
    },
]


PROPOSAL_REGISTRY_TRANSFERRED_SOURCE_COLUMNS = {
    "evaluation_date",
    "term",
    "preliminary_report_date",
    "final_report_term_weeks",
    "final_report_date",
    "advance_percent",
    "advance_term",
    "preliminary_report_percent",
    "preliminary_report_term",
    "final_report_percent",
    "final_report_term",
}


PROPOSAL_REGISTRY_DEFAULT_HIDDEN_SOURCE_COLUMNS = {
    "country",
    "identifier",
    "registration_number",
    "date",
    "asset_owner_country",
    "asset_owner_identifier",
    "asset_owner_registration_number",
    "asset_owner_registration_date",
    "proposal_project_name",
    "purpose",
    "service_composition",
    "report_languages",
}


PROPOSAL_PAYMENT_SCHEDULE_UI_COLUMNS = [
    {
        "picker_value": "number",
        "data_col": "number",
        "source_column": "number",
        "label": "Номер",
    },
    {
        "picker_value": "sub-number",
        "data_col": "sub-number",
        "source_column": "sub_number",
        "label": "№",
    },
    {
        "picker_value": "group",
        "data_col": "group",
        "source_column": "group",
        "label": "Группа",
    },
    {
        "picker_value": "tkp-id",
        "data_col": "tkp-id",
        "source_column": "tkp_id",
        "label": "ТКП ID",
    },
    {
        "picker_value": "type",
        "data_col": "type",
        "source_column": "type",
        "label": "Тип",
    },
    {
        "picker_value": "name",
        "data_col": "name",
        "source_column": "name",
        "label": "Название",
    },
    {
        "picker_value": "stage",
        "data_col": "stage",
        "source_column": "stage",
        "label": "Этап",
    },
    {
        "picker_value": "evaluation-date",
        "data_col": "evaluation-date",
        "source_column": "evaluation_date",
        "label": "Дата оценки",
    },
    {
        "picker_value": "start-date",
        "data_col": "start-date",
        "source_column": "start_date",
        "label": "Дата начала",
    },
    {
        "picker_value": "term",
        "data_col": "term",
        "source_column": "term",
        "label": "Срок предв. отчёта, мес.",
    },
    {
        "picker_value": "preliminary-report-date",
        "data_col": "preliminary-report-date",
        "source_column": "preliminary_report_date",
        "label": "Дата предв. отчёта",
    },
    {
        "picker_value": "final-report-weeks",
        "data_col": "final-report-weeks",
        "source_column": "final_report_term_weeks",
        "label": "Срок итог. отчёта, нед.",
    },
    {
        "picker_value": "final-report-date",
        "data_col": "final-report-date",
        "source_column": "final_report_date",
        "label": "Дата итог. отчёта",
    },
    {
        "picker_value": "advance-percent",
        "data_col": "advance-percent",
        "source_column": "advance_percent",
        "label": "Предоплата, проц.",
    },
    {
        "picker_value": "advance-term",
        "data_col": "advance-term",
        "source_column": "advance_term",
        "label": "Предоплата, срок дн.",
    },
    {
        "picker_value": "preliminary-report-percent",
        "data_col": "preliminary-report-percent",
        "source_column": "preliminary_report_percent",
        "label": "Предв. отчёт, проц.",
    },
    {
        "picker_value": "preliminary-report-term",
        "data_col": "preliminary-report-term",
        "source_column": "preliminary_report_term",
        "label": "Предв. отчёт, срок дн.",
    },
    {
        "picker_value": "final-report-percent",
        "data_col": "final-report-percent",
        "source_column": "final_report_percent",
        "label": "Итог. отчёт, проц.",
    },
    {
        "picker_value": "final-report-term",
        "data_col": "final-report-term",
        "source_column": "final_report_term",
        "label": "Итог. отчёт, срок дн.",
    },
]


PROPOSAL_PAYMENT_SCHEDULE_DEFAULT_HIDDEN_SOURCE_COLUMNS = {
    "advance_percent",
    "preliminary_report_percent",
    "final_report_percent",
}


PROPOSAL_DISPATCH_UI_COLUMNS = [
    {
        "picker_value": "number",
        "data_col": "number",
        "source_column": "number",
        "label": "Номер",
    },
    {
        "picker_value": "sub-number",
        "data_col": "sub-number",
        "source_column": "sub_number",
        "label": "№",
    },
    {
        "picker_value": "group",
        "data_col": "group",
        "source_column": "group",
        "label": "Группа",
    },
    {
        "picker_value": "tkp-id",
        "data_col": "tkp-id",
        "source_column": "tkp_id",
        "label": "ТКП ID",
    },
    {
        "picker_value": "type",
        "data_col": "type",
        "source_column": "type",
        "label": "Тип",
    },
    {
        "picker_value": "name",
        "data_col": "name",
        "source_column": "name",
        "label": "Название",
    },
    {
        "picker_value": "cloud",
        "data_col": "cloud",
        "source_column": "cloud",
        "label": "Облако",
    },
    {
        "picker_value": "docx-name",
        "data_col": "docx-name",
        "source_column": "docx_file_name",
        "label": "Наименование файла DOCX",
    },
    {
        "picker_value": "pdf-name",
        "data_col": "pdf-name",
        "source_column": "pdf_file_name",
        "label": "Наименование файла PDF",
    },
    {
        "picker_value": "sent-date",
        "data_col": "sent-date",
        "source_column": "sent_date",
        "label": "Дата отправки",
    },
    {
        "picker_value": "contact-name",
        "data_col": "contact-name",
        "source_column": "contact_name",
        "label": "ФИО",
    },
    {
        "picker_value": "contact-email",
        "data_col": "contact-email",
        "source_column": "contact_email",
        "label": "Эл. почта",
    },
    {
        "picker_value": "job-title",
        "data_col": "job-title",
        "source_column": "job_title",
        "label": "Должность",
    },
    {
        "picker_value": "organization",
        "data_col": "organization",
        "source_column": "organization",
        "label": "Организация",
    },
    {
        "picker_value": "transfer-date",
        "data_col": "transfer-date",
        "source_column": "transfer_to_contract_date",
        "label": "Передано",
    },
]


PROPOSAL_DISPATCH_DEFAULT_HIDDEN_SOURCE_COLUMNS: set[str] = set()


def _with_default_hidden(item, default_hidden_source_columns):
    column = dict(item)
    if column["source_column"] in default_hidden_source_columns:
        column["default_hidden"] = True
    return column


def get_proposal_registry_ui_columns():
    return [
        _with_default_hidden(item, PROPOSAL_REGISTRY_DEFAULT_HIDDEN_SOURCE_COLUMNS)
        for item in PROPOSAL_REGISTRY_COLUMNS
        if item["source_column"] not in PROPOSAL_REGISTRY_TRANSFERRED_SOURCE_COLUMNS
    ]


def get_proposal_payment_schedule_ui_columns():
    return [
        _with_default_hidden(item, PROPOSAL_PAYMENT_SCHEDULE_DEFAULT_HIDDEN_SOURCE_COLUMNS)
        for item in PROPOSAL_PAYMENT_SCHEDULE_UI_COLUMNS
    ]


def get_proposal_dispatch_ui_columns():
    return [
        _with_default_hidden(item, PROPOSAL_DISPATCH_DEFAULT_HIDDEN_SOURCE_COLUMNS)
        for item in PROPOSAL_DISPATCH_UI_COLUMNS
    ]


def get_proposal_registry_variable_columns():
    columns = {
        item["source_column"]: item["label"]
        for item in PROPOSAL_REGISTRY_COLUMNS
        if item.get("variable_available", True)
    }
    # Keep the legacy source column available so old non-computed variables
    # bound before the computed-variable migration can still be edited/saved.
    columns.setdefault("country_full_name", "Наименование страны (полное)")
    return columns
