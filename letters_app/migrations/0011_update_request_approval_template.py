from django.db import migrations


REQUEST_APPROVAL_HTML = (
    '<p>Добрый день, {recipient_name}!</p>'
    '<p>Прошу согласовать информационный запрос по проекту {project_label} '
    'по следующим разделам:</p>'
    '{services_list}'
    '<p>Для согласования информационного запроса необходимо изучить сформированный '
    'типовой чек-лист по проекту {project_label} в разделе «Чек-листы», '
    'при необходимости внести изменения и согласовать все разделы итогового чек-листа, '
    'кликнув на кнопку «Согласовать запрос (чек-лист)» в разделе «Чек-листы» внизу страницы '
    'или согласовать запрос по отдельным разделам, кликая на кнопки '
    '«Согласовать раздел чек-листа» в каждом выбранном в фильтре разделе.</p>'
    '<p>Согласовать запрос необходимо в течение {duration_hours} '
    'часов с момента отправки данного сообщения\u00a0— до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

REQUEST_APPROVAL_SUBJECT = "Согласование запроса по проекту {project_label}"


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="request_approval", is_default=True
    ).update(
        body_html=REQUEST_APPROVAL_HTML,
        subject_template=REQUEST_APPROVAL_SUBJECT,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0010_add_scan_sending_template"),
    ]

    operations = [
        migrations.RunPython(update_template, noop),
    ]
