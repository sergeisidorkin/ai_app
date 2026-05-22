from django.db import migrations


PAYMENT_REQUEST_SUBJECT = "Заявка на оплату №{number_of_request}"
PAYMENT_REQUEST_HTML = (
    "<p>Добрый день, {recipient_name_lawer}</p>"
    "<p>Просим произвести оплату в {payment_date}.</p>"
    "<p>[payment_request]</p>"
    "<p>С уважением,<br>IMC Montan AI</p>"
)


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ).update(
        subject_template=PAYMENT_REQUEST_SUBJECT,
        body_html=PAYMENT_REQUEST_HTML,
    )


def revert_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ).update(
        subject_template="Заявка на оплату по проекту {project_label}",
        body_html=(
            '<p>Добрый день, {recipient_name}!</p>'
            '<p>Направляем заявку на оплату по проекту {project_label}.</p>'
            '<p>Руководитель проекта: {project_manager}.</p>'
            '<p>Срок завершения проекта: {project_deadline}.</p>'
            '<p>Этапы проекта и продукты:</p>'
            '{project_stages}'
            '<p>Предлагаемый состав услуг (разделов):</p>'
            '{services_list}'
            '<p>Сумма к оплате: {agreed_amount} {currency_code}.</p>'
            '<p>С уважением,<br>IMC Montan AI</p>'
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0016_add_payment_request_template"),
    ]

    operations = [
        migrations.RunPython(update_template, revert_template),
    ]
