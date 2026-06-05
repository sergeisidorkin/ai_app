from django.db import migrations


CONTRACT_SENDING_HTML = (
    '<p>Добрый день, {recipient_name}</p>'
    '<p>В связи с вашим подтверждением готовности принять участие в проекте '
    '{project_label} направляем проект договора.</p>'
    '<p>Проект: {project_label}</p>'
    '<p>Этапы проекта и продукты:</p>'
    '[project_stages]'
    '<p>Срок завершения проекта: [project_deadline]</p>'
    '<p>Исполнитель: {executor}<br>'
    'Оплата услуг без учета налогов: {agreed_amount}<br>'
    'Порядок оплаты: {prepayment_percent} аванс, {final_payment_percent} окончательный платёж<br>'
    'Срок исполнения: до {project_deadline}</p>'
    '<p>DOCX доступен для скачивания по ссылке: {document_docx_link}</p>'
    '<p>PDF доступен для скачивания по ссылке: {document_pdf_link}</p>'
    '<p>Подписать договор в разделе «Договоры» на сайте imcmontanai.ru '
    'необходимо в течение {duration_hours} часов с момента отправки данного '
    'сообщения — до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="contract_sending",
        is_default=True,
        user__isnull=True,
    ).update(body_html=CONTRACT_SENDING_HTML)


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0019_payment_request_number_subject"),
    ]

    operations = [
        migrations.RunPython(update_template, migrations.RunPython.noop),
    ]
