from django.db import migrations


REPORT_REMARKS_SUBJECT = "Замечания по проекту {project_label}"
REPORT_REMARKS_HTML = (
    "<p>Добрый день, {recipient_name}</p>"
    "<p>Направляю замечания к следующим отчетам:</p>"
    "<ul>"
    "<li>проект: {project_label}</li>"
    "<li>этапы проекта и продукты:"
    "[project_stages]</li>"
    "<li>блоки услуг (разделы):"
    "[services_list]</li>"
    "</ul>"
    "<p>Все изменения необходимо вносить в отправленный текст отчета с замечаниями (см. ссылку ниже), "
    "в том числе все дополнения и доработки, сдаленные вами до получения настоящих замечений.</p>"
    "<p>Прошу замечания (примечания в тексте) не удалять, можно комментировать в ответ, "
    "однако просто об исправлении замечания сообщать не нужно.</p>"
    "<p>Текст отчета с замечаниями доступен для скачивания по ссылке: {report_docx_link}</p>"
    "<p>Тот же текст отчета с замечаниями также можно скачать в разделе «Проекты» "
    "в подразделе «Сдача отчетов» в таблице «Отчеты» в соответствующей строке столбца «Результаты проверки».</p>"
    "<p>С уважением,<br>{sender}</p>"
)

PREVIOUS_SUBJECT = "Замечания по {project_label}"
PREVIOUS_HTML = (
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


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="report_remarks",
        is_default=True,
        user__isnull=True,
    ).update(
        subject_template=REPORT_REMARKS_SUBJECT,
        body_html=REPORT_REMARKS_HTML,
    )


def restore_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="report_remarks",
        is_default=True,
        user__isnull=True,
    ).update(
        subject_template=PREVIOUS_SUBJECT,
        body_html=PREVIOUS_HTML,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0021_add_report_remarks_template"),
    ]

    operations = [
        migrations.RunPython(update_template, restore_template),
    ]
