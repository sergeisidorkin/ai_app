from django.db import migrations, models


REPORT_REMARKS_SUBJECT = "Замечания по {project_label}"
REPORT_REMARKS_HTML = (
    "<p>Добрый день, {recipient_name}</p>"
    "<p>Направляю замечания к следующим отчетам:</p>"
    "<p>Проект: {project_label}</p>"
    "<p>Этапы проекта и продукты:</p>"
    "[project_stages]"
    "<p>Блоки услуг (разделы):</p>"
    "[services_list]"
    "<p>Все изменения необходимо вносить в отправленный файл, в том числе все дополнения "
    "и доработки, сдаленные вами до получения настоящих замечений.</p>"
    "<p>Замечания (примечания в тексте) не удалять, можно комментировать в ответ, "
    "однако просто об исправлении замечания сообщать не нужно.</p>"
    "<p>С уважением,<br>IMC Montan AI</p>"
)


def create_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    if not LetterTemplate.objects.filter(template_type="report_remarks", is_default=True).exists():
        LetterTemplate.objects.create(
            template_type="report_remarks",
            user=None,
            subject_template=REPORT_REMARKS_SUBJECT,
            body_html=REPORT_REMARKS_HTML,
            is_default=True,
        )


def remove_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="report_remarks",
        is_default=True,
        user__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0020_update_contract_sending_multistage_template"),
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
                    ("report_remarks", "Отправка замечаний"),
                    ("payment_request", "Заявка на оплату"),
                ],
                db_index=True,
            ),
        ),
        migrations.RunPython(create_template, remove_template),
    ]
