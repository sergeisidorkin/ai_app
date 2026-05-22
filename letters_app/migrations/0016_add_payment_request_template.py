from django.db import migrations, models


PAYMENT_REQUEST_SUBJECT = "Заявка на оплату по проекту {project_label}"
PAYMENT_REQUEST_HTML = (
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
)


def create_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    if not LetterTemplate.objects.filter(template_type="payment_request", is_default=True).exists():
        LetterTemplate.objects.create(
            template_type="payment_request",
            user=None,
            subject_template=PAYMENT_REQUEST_SUBJECT,
            body_html=PAYMENT_REQUEST_HTML,
            is_default=True,
        )


def remove_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0015_update_participation_project_stages_template"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lettertemplate",
            name="template_type",
            field=models.CharField(
                "Тип шаблона",
                max_length=64,
                choices=[
                    ("participation_confirmation", "Подтверждение участия эксперта"),
                    ("direction_confirmation", "Подтверждение по направлению"),
                    ("contract_sending", "Отправка проекта договора"),
                    ("proposal_sending", "Отправка ТКП"),
                    ("scan_sending", "Отправка скана сотрудника"),
                    ("project_start", "Начало проекта"),
                    ("request_approval", "Согласование запроса"),
                    ("payment_request", "Заявка на оплату"),
                ],
                db_index=True,
            ),
        ),
        migrations.RunPython(create_template, remove_template),
    ]
