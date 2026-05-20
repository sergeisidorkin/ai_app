from django.db import migrations


PARTICIPATION_CONFIRMATION_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Приглашаем вас принять участие в новом проекте IMC Montan Group — {project_label}.</p>'
    '<p>Руководитель проекта: [project_manager]</p>'
    '<p>Срок завершения проекта: [project_deadline]</p>'
    '<p>Этапы проекта и продукты:</p>'
    '[project_stages]'
    '<p>Предлагаемый состав услуг (разделов):</p>'
    '[services_list]'
    '<p>Предлагаемая оплата услуг: {agreed_amount} {currency_code}.</p>'
    '<p>Принять решение об участии в проекте, кликнув на кнопку '
    '«Подтвердить участие» или «Отклонить», необходимо в течение {duration_hours} '
    'часов с момента отправки данного сообщения — до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)


def _confirmation_html():
    return PARTICIPATION_CONFIRMATION_HTML


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    for template_type in ("participation_confirmation", "direction_confirmation"):
        LetterTemplate.objects.filter(
            template_type=template_type,
            is_default=True,
            user__isnull=True,
        ).update(body_html=_confirmation_html())


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0014_update_contract_sending_document_links"),
    ]

    operations = [
        migrations.RunPython(update_template, migrations.RunPython.noop),
    ]
