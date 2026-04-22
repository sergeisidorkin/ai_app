"""
Registry of all UI sections, tables, and columns.

Used by ContractVariable to structurally link a template variable
to a specific column in a specific table of a specific section.
"""

import json

from core.proposal_registry_columns import get_proposal_registry_variable_columns


COLUMN_REGISTRY = {
    "users": {
        "label": "Пользователи",
        "tables": {
            "staff": {
                "label": "Сотрудники",
                "columns": {
                    "last_name": "Фамилия",
                    "first_name": "Имя",
                    "patronymic": "Отчество",
                    "email": "Эл. почта (логин)",
                    "phone": "Телефон",
                    "employment": "Трудоустройство",
                    "department": "Подразделение",
                    "position": "Должность",
                    "role": "Роль",
                },
            },
            "external": {
                "label": "Внешние пользователи",
                "columns": {
                    "last_name": "Фамилия",
                    "first_name": "Имя",
                    "patronymic": "Отчество",
                    "email": "Эл. почта (логин)",
                    "phone": "Телефон",
                    "organization": "Организация",
                    "position": "Должность",
                },
            },
        },
    },
    "products": {
        "label": "Продукты",
        "tables": {
            "expertise_directions": {
                "label": "Направления экспертизы",
                "columns": {
                    "short_name": "Краткое имя",
                    "direction_name": "Наименование направления",
                    "cost_calculation": "Расчет стоимости услуг",
                    "owner": "Владелец",
                },
            },
            "consulting_directions": {
                "label": "Направления консалтинга",
                "columns": {
                    "consulting_type": "Вид консалтинга",
                    "service_category": "Тип услуг",
                    "service_code": "Код",
                    "service_subtype": "Подтип услуги",
                },
            },
            "typical_products": {
                "label": "Типовые продукты",
                "columns": {
                    "short_name": "Краткое имя",
                    "name_en": "Наименование на английском языке",
                    "name_ru": "Наименование на русском языке",
                    "display_name": "Отображаемое в системе имя",
                    "consulting_type": "Вид консалтинга",
                    "service_category": "Тип услуг",
                    "service_code": "Код",
                    "service_subtype": "Подтип услуги",
                    "owner": "Владелец",
                },
            },
            "typical_sections": {
                "label": "Типовые разделы (услуги)",
                "columns": {
                    "product": "Продукт",
                    "code": "Код",
                    "short_name_en": "Краткое имя EN",
                    "short_name_ru": "Краткое имя RU",
                    "section_name_en": "Наименование раздела (услуги) EN",
                    "section_name_ru": "Наименование раздела (услуги) RU",
                    "accounting_type": "Тип учета",
                    "performer": "Исполнитель",
                    "expertise": "Экспертиза",
                    "department": "Подразделение",
                },
            },
            "service_goals_and_report_titles": {
                "label": "Цели услуг и названия отчетов",
                "columns": {
                    "product": "Продукт",
                    "service_goal": "Цели оказания услуг",
                    "service_goal_genitive": "Цели оказания услуг в родительном падеже",
                    "report_title": "Название отчета",
                },
            },
            "section_structure": {
                "label": "Типовая структура раздела (состава услуг)",
                "columns": {
                    "product": "Продукт",
                    "section": "Раздел (услуга)",
                    "subsections": "Подразделы",
                },
            },
            "typical_service_composition": {
                "label": "Типовой состав услуг",
                "columns": {
                    "product": "Продукт",
                    "section": "Раздел (услуга)",
                    "service_composition": "Состав услуг",
                },
            },
            "typical_service_terms": {
                "label": "Типовые сроки оказания услуг",
                "columns": {
                    "product": "Продукт",
                    "preliminary_report_months": "Срок подготовки Предварительного отчёта, мес.",
                    "final_report_weeks": "Срок подготовки Итогового отчёта, нед.",
                },
            },
            "grades": {
                "label": "Грейды",
                "columns": {
                    "grade_en": "Грейд на английском языке",
                    "grade_ru": "Грейд на русском языке",
                    "grade_level": "Грейд (уровень)",
                    "base_rate": "Базовая ставка",
                    "hourly_rate": "Часовая ставка",
                    "base_rate_share": "Доля базовой ставки",
                    "direction_head": "Руководитель направления",
                },
            },
            "specialty_tariffs": {
                "label": "Тарифы специальностей",
                "columns": {
                    "specialty_group": "Группа специальностей",
                    "specialties": "Специальности",
                    "expertise_direction": "Направления экспертизы",
                    "daily_rate_tkp_eur": "Дневная ставка оплаты в евро для ТКП",
                    "daily_rate_ss": "Дневная ставка оплаты для с/с",
                    "currency": "Валюта",
                    "direction_head": "Руководитель направления",
                },
            },
            "tariffs": {
                "label": "Тарифы разделов (услуг)",
                "columns": {
                    "product": "Продукт",
                    "section": "Раздел (услуга)",
                    "base_rate_vpm": "Базовая ставка в ВПМ",
                    "service_volume_hours": "Объем услуг в часах",
                    "service_volume_days_tkp": "Объем услуг в днях для ТКП",
                    "direction_head": "Руководитель направления",
                },
            },
        },
    },
    "experts": {
        "label": "Эксперты",
        "tables": {
            "specialties": {
                "label": "Специальности экспертов",
                "columns": {
                    "specialty": "Специальность",
                    "specialty_en": "Специальность на англ. языке",
                    "owner": "Владелец",
                    "expertise_direction": "Направление экспертизы",
                    "department": "Подразделение",
                    "direction_head": "Руководитель направления",
                },
            },
            "experts_base": {
                "label": "База экспертов",
                "columns": {
                    "full_name": "ФИО",
                    "email": "Эл. почта (логин)",
                    "extra_email": "Дополнительная эл. почта",
                    "phone": "Телефон",
                    "extra_phone": "Дополнительный телефон",
                    "expertise_direction": "Направление экспертизы",
                    "specialty": "Специальность",
                    "professional_status": "Профессиональный статус",
                    "professional_status_short": "Профессиональный статус (кратко)",
                    "grade": "Грейд",
                    "country": "Страна",
                    "region": "Регион проживания",
                    "status": "Статус",
                    "date": "Дата",
                },
            },
            "contract_details": {
                "label": "Реквизиты для договора",
                "columns": {
                    "full_name": "ФИО",
                    "full_name_genitive": "ФИО (полное) род. падеж",
                    "citizenship_country": "Страна гражданства",
                    "citizenship_status": "Статус",
                    "birth_date": "Дата рожд.",
                    "gender": "Пол",
                    "citizenship": "Гражданство",
                    "citizenship_identifier": "Идентификатор",
                    "citizenship_number": "Номер",
                    "snils": "СНИЛС",
                    "self_employed": "Самозан.",
                    "tax_rate": "Налог",
                    "passport_series": "Паспорт: серия",
                    "passport_number": "номер",
                    "passport_issued_by": "кем выдан",
                    "passport_issue_date": "дата выдачи",
                    "passport_expiry": "срок действия",
                    "passport_division_code": "код подразд.",
                    "registration_address": "адрес регистрации",
                    "bank_name": "Наименование банка",
                    "swift": "SWIFT",
                    "bank_inn": "ИНН банка",
                    "bik": "БИК",
                    "settlement_account": "Рас. счет",
                    "correspondent_account": "Кор. счет",
                    "bank_address": "Адрес банка",
                    "corr_bank_name": "Наим. банка-корр.",
                    "corr_bank_address": "Адрес банка-корр.",
                    "corr_bank_bik": "БИК банка-корр.",
                    "corr_bank_swift": "SWIFT банка-корр.",
                    "corr_bank_settlement": "Рас. счет банка-корр.",
                    "corr_bank_correspondent": "Кор. счет банка-корр.",
                },
            },
        },
    },
    "contacts": {
        "label": "Контакты",
        "tables": {
            "persons": {
                "label": "Реестр лиц",
                "columns": {
                    "last_name": "Фамилия",
                    "first_name": "Имя",
                    "middle_name": "Отчество",
                    "full_name_genitive": "ФИО (полное) в родительном падеже",
                    "gender": "Пол",
                    "birth_date": "Дата рождения",
                    "user_kind": "Пользователь",
                },
            },
        },
    },
    "projects": {
        "label": "Проекты",
        "tables": {
            "registration": {
                "label": "Регистрация проекта",
                "columns": {
                    "number": "Номер",
                    "group": "Группа",
                    "agreement_type": "Вид соглашения",
                    "project_id": "Проект ID",
                    "type": "Тип",
                    "name": "Название",
                    "status": "Статус",
                    "deadline": "Дедлайн",
                    "year": "Год",
                    "project_manager": "Руководитель проекта",
                    "customer": "Заказчик",
                    "country": "Страна",
                    "identifier": "Идент.",
                    "registration_number": "Регистр. номер",
                    "date": "Дата",
                },
            },
            "contract_terms": {
                "label": "Сроки проекта по договору",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "agreement_type": "Вид соглашения",
                    "agreement_number": "№ соглашения",
                    "start_date": "Начало",
                    "end_date": "Оконч.",
                    "end_date_locked": "Оконч. (замок)",
                    "source_data": "Исх. данные",
                    "stage1_weeks": "Этап 1, нед.",
                    "stage1_end": "Этап 1, ок.",
                    "stage2_weeks": "Этап 2, нед.",
                    "stage2_end": "Этап 2, ок.",
                    "stage3_weeks": "Этап 3, нед.",
                    "total_weeks": "Срок, нед.",
                    "contract_subject": "Предмет договора",
                },
            },
            "work_assets": {
                "label": "Объем услуг: активы",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "asset_name": "Наименование актива",
                    "country": "Страна",
                    "identifier": "Идент.",
                    "registration_number": "Регистр. номер",
                    "date": "Дата",
                    "manager": "Менеджер проекта",
                },
            },
            "work_legal_entities": {
                "label": "Объем услуг: юрлица",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "asset_name": "Наименование актива",
                    "legal_entity_name": "Наименование юридического лица",
                    "country": "Страна",
                    "identifier": "Идент.",
                    "registration_number": "Регистр. номер",
                    "date": "Дата",
                },
            },
            "performers": {
                "label": "Исполнители",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "asset_name": "Наименование актива",
                    "performer": "Исполнитель",
                    "grade": "Грейд",
                    "typical_section": "Типовой раздел",
                    "adjusted_costs": "Скоррект. затраты",
                    "calculated_costs": "Расч. затраты",
                    "approved": "Согласовано",
                    "advance": "Аванс",
                    "final_payment": "Окон. платёж",
                    "contract_number": "№ договора",
                },
            },
            "participation_confirmation": {
                "label": "Подтверждение участия",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "performer": "Исполнитель",
                    "grade": "Грейд",
                    "asset_name": "Наименование актива",
                    "typical_section": "Типовой раздел",
                    "send_date": "Дата отправки",
                    "deadline": "Срок",
                    "request_response": "Ответ на запрос",
                    "response_date": "Дата ответа",
                    "response_status": "Статус ответа",
                },
            },
            "contract_conclusion": {
                "label": "Заключение договора",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "performer": "Исполнитель",
                    "grade": "Грейд",
                    "asset_name": "Наименование актива",
                    "typical_section": "Типовой раздел",
                    "send_date": "Дата отправки",
                    "deadline": "Срок",
                    "signing_date": "Дата подписания",
                    "status": "Статус",
                    "signing": "Подписание",
                },
            },
            "request_approval": {
                "label": "Согласование запроса",
                "columns": {
                    "project": "Проект",
                    "type": "Тип",
                    "name": "Название",
                    "performer": "Исполнитель",
                    "grade": "Грейд",
                    "asset_name": "Наименование актива",
                    "typical_section": "Типовой раздел",
                    "send_date": "Дата отправки",
                    "deadline": "Срок",
                    "approval_status": "Статус согласования",
                    "response_date": "Дата ответа",
                    "response_status": "Статус ответа",
                },
            },
        },
    },
    "contracts": {
        "label": "Договоры",
        "tables": {
            "contract_subject": {
                "label": "Предмет договора",
                "columns": {
                    "product": "Продукт",
                    "subject_text": "Предмет договора",
                },
            },
        },
    },
    "proposals": {
        "label": "ТКП",
        "tables": {
            "registry": {
                "label": "Реестр ТКП",
                "columns": get_proposal_registry_variable_columns(),
            },
        },
    },
}


def get_section_choices():
    return [("", "---")] + [
        (key, sec["label"]) for key, sec in COLUMN_REGISTRY.items()
    ]


def get_table_choices(section_key):
    sec = COLUMN_REGISTRY.get(section_key)
    if not sec:
        return [("", "---")]
    return [("", "---")] + [
        (key, tbl["label"]) for key, tbl in sec["tables"].items()
    ]


def get_column_choices(section_key, table_key):
    sec = COLUMN_REGISTRY.get(section_key)
    if not sec:
        return [("", "---")]
    tbl = sec["tables"].get(table_key)
    if not tbl:
        return [("", "---")]
    return [("", "---")] + list(tbl["columns"].items())


def validate_column_ref(section_key, table_key, column_key):
    sec = COLUMN_REGISTRY.get(section_key)
    if not sec:
        return False
    tbl = sec["tables"].get(table_key)
    if not tbl:
        return False
    return column_key in tbl["columns"]


def get_registry_json():
    return json.dumps(COLUMN_REGISTRY, ensure_ascii=False)
