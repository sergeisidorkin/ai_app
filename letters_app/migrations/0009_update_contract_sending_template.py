from django.db import migrations


CONTRACT_SENDING_HTML = (
    '<p>Добрый день, {recipient_name}</p>'
    '<p>В связи с вашим подтверждением готовности принять участие в проекте '
    '{project_label} направляем проект договора.</p>'
    '<p>Состав активов:</p>'
    '{services_list}'
    '<p>Проект: {project_label}<br>'
    'Исполнитель: {executor}<br>'
    'Оплата услуг без учета налогов: {agreed_amount}<br>'
    'Порядок оплаты: {prepayment_percent} аванс, {final_payment_percent} окончательный платёж<br>'
    'Срок исполнения: до {project_deadline}</p>'
    '<p>Документ доступен для скачивания по ссылке: {document_link}</p>'
    '<p>Подписать договор и загрузить подписанную скан-копию в разделе '
    '«Договоры» на сайте imcmontanai.ru необходимо в течение {duration_hours} '
    'часов с момента отправки данного сообщения — до {deadline_at}.</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)

CONTRACT_SENDING_SUBJECT = "Отправлен проект договора по проекту {project_label}"


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="contract_sending", is_default=True
    ).update(body_html=CONTRACT_SENDING_HTML, subject_template=CONTRACT_SENDING_SUBJECT)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0008_update_template_type_choices"),
    ]

    operations = [
        migrations.RunPython(update_template, noop),
    ]
