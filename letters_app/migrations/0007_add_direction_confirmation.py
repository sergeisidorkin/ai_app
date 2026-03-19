from django.db import migrations


DIRECTION_CONFIRMATION_HTML = (
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


def forwards(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.update_or_create(
        template_type="direction_confirmation",
        user=None,
        defaults={
            "body_html": DIRECTION_CONFIRMATION_HTML,
            "is_default": True,
        },
    )


def backwards(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="direction_confirmation",
        user__isnull=True,
        is_default=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("letters_app", "0006_update_participation_template_currency"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
