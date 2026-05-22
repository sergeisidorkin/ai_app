from django.db import migrations


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ).update(subject_template="Заявка на оплату №{number_of_request}")


def revert_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ).update(subject_template="Заявка на оплату")


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0018_payment_request_list_variable_brackets"),
    ]

    operations = [
        migrations.RunPython(update_template, revert_template),
    ]
