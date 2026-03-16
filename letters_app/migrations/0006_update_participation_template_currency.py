from django.db import migrations

NEW_BODY = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Приглашаем вас принять участие в новом проекте IMC Montan Group — {project_label}.</p>'
    '<p>Руководитель проекта: {project_manager}.</p>'
    '<p>Срок завершения проекта: {project_deadline}.</p>'
    '<p>Тип проекта: {project_type}.</p>'
    '<p>Предлагаемый состав услуг (разделов):</p>'
    '{services_list}'
    '<p>Предлагаемая оплата услуг: {agreed_amount} {currency_code}.</p>'
    '<p>Принять решение об участии в проекте, кликнув на кнопку '
    '«Подтвердить участие» или «Отклонить», необходимо в течение '
    '{duration_hours} часов с момента отправки данного сообщения — '
    'до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

OLD_BODY = (
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


def forwards(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="participation_confirmation",
        is_default=True,
        user__isnull=True,
    ).update(body_html=NEW_BODY)


def backwards(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="participation_confirmation",
        is_default=True,
        user__isnull=True,
    ).update(body_html=OLD_BODY)


class Migration(migrations.Migration):
    dependencies = [
        ("letters_app", "0005_add_cc_recipients"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
