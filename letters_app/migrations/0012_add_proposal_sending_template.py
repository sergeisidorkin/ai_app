from django.db import migrations, models


PROPOSAL_SENDING_SUBJECT = "Технико-коммерческое предложение IMC Montan {{tkp_id}}"
PROPOSAL_SENDING_HTML = "<p>Направляем проект ТКП {{tkp_id}}</p>"


def create_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    if not LetterTemplate.objects.filter(template_type="proposal_sending", is_default=True).exists():
        LetterTemplate.objects.create(
            template_type="proposal_sending",
            user=None,
            subject_template=PROPOSAL_SENDING_SUBJECT,
            body_html=PROPOSAL_SENDING_HTML,
            is_default=True,
        )


def remove_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="proposal_sending",
        is_default=True,
        user__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0011_update_request_approval_template"),
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
                ],
                db_index=True,
            ),
        ),
        migrations.RunPython(create_template, remove_template),
    ]
