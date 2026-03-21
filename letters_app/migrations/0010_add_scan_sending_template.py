from django.db import migrations, models


SCAN_SENDING_SUBJECT = "Исполнитель ({executor}) отправил скан договора по проекту {project_label}"

SCAN_SENDING_HTML = (
    '<p>Добрый день, {recipient_name_lawer}</p>'
    '<p>Вам отправлена подписанная исполнителем скан-копия договора '
    'по проекту {project_label}.</p>'
    '<p>Проект: {project_label}<br>'
    'Исполнитель: {executor}<br>'
    'Оплата услуг без учета налогов: {agreed_amount}<br>'
    'Порядок оплаты: {prepayment_percent} аванс, {final_payment_percent} окончательный платёж<br>'
    'Срок исполнения: до {project_deadline}</p>'
    '<p>Документ доступен для скачивания по ссылке: {document_link_scan}</p>'
    '<p>Необходимо подписать договор и загрузить скан-копию итогового варианта '
    'договора, подписанного двумя сторонами, на сайт imcmontanai.ru '
    'в таблицу «Договоры» раздела «Договоры».</p>'
    '<p>С уважением,<br>IMC Montan AI</p>'
)


def create_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    if not LetterTemplate.objects.filter(template_type="scan_sending", is_default=True).exists():
        LetterTemplate.objects.create(
            template_type="scan_sending",
            user=None,
            subject_template=SCAN_SENDING_SUBJECT,
            body_html=SCAN_SENDING_HTML,
            is_default=True,
        )


def remove_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(template_type="scan_sending", is_default=True, user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0009_update_contract_sending_template"),
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
                    ("scan_sending", "Отправка скана сотрудника"),
                    ("project_start", "Начало проекта"),
                    ("request_approval", "Согласование запроса"),
                ],
                db_index=True,
            ),
        ),
        migrations.RunPython(create_template, remove_template),
    ]
