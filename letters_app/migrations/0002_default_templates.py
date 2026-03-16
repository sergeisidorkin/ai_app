from django.db import migrations


PARTICIPATION_CONFIRMATION_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Приглашаем вас принять участие в новом проекте IMC Montan Group — {project_label}.</p>'
    '<p>Руководитель проекта: {project_manager}.</p>'
    '<p>Срок завершения проекта: {project_deadline}.</p>'
    '<p>Тип проекта: {project_type}.</p>'
    '<p>Предлагаемый состав услуг (разделов):</p>'
    '{services_list}'
    '<p>Предлагаемая оплата услуг: {agreed_amount}.</p>'
    '<p>Принять решение об участии в проекте, кликнув на кнопку '
    '«Подтвердить участие» или «Отклонить», необходимо в течение '
    '{duration_hours} часов с момента отправки данного сообщения — '
    'до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

CONTRACT_SENDING_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>В связи с вашим подтверждением готовности принять участие в проекте '
    '{project_label} направляем проект договора.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

PROJECT_START_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Информируем вас о начале работ по проекту {project_label}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

REQUEST_APPROVAL_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Просим вас согласовать запрос информации по проекту {project_label}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

DEFAULTS = [
    ("participation_confirmation", PARTICIPATION_CONFIRMATION_HTML),
    ("contract_sending", CONTRACT_SENDING_HTML),
    ("project_start", PROJECT_START_HTML),
    ("request_approval", REQUEST_APPROVAL_HTML),
]


def create_defaults(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    for ttype, body in DEFAULTS:
        LetterTemplate.objects.update_or_create(
            template_type=ttype,
            user=None,
            defaults={"body_html": body, "is_default": True},
        )


def remove_defaults(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(user__isnull=True, is_default=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("letters_app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_defaults, remove_defaults),
    ]
