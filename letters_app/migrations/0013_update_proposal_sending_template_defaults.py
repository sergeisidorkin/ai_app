from django.db import migrations


PROPOSAL_SENDING_SUBJECT = "Технико-коммерческое предложение IMC Montan {{tkp_id}}"
PROPOSAL_SENDING_HTML = "<p>Направляем проект ТКП {{tkp_id}}</p>"


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="proposal_sending",
        is_default=True,
    ).update(
        subject_template=PROPOSAL_SENDING_SUBJECT,
        body_html=PROPOSAL_SENDING_HTML,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0012_add_proposal_sending_template"),
    ]

    operations = [
        migrations.RunPython(update_template, noop),
    ]
