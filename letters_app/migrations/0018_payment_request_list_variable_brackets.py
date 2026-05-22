from django.db import migrations


def update_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    for template in LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ):
        if "{payment_request}" in template.body_html:
            template.body_html = template.body_html.replace("{payment_request}", "[payment_request]")
            template.save(update_fields=["body_html"])


def revert_template(apps, schema_editor):
    LetterTemplate = apps.get_model("letters_app", "LetterTemplate")
    for template in LetterTemplate.objects.filter(
        template_type="payment_request",
        is_default=True,
        user__isnull=True,
    ):
        if "[payment_request]" in template.body_html:
            template.body_html = template.body_html.replace("[payment_request]", "{payment_request}")
            template.save(update_fields=["body_html"])


class Migration(migrations.Migration):

    dependencies = [
        ("letters_app", "0017_update_payment_request_template"),
    ]

    operations = [
        migrations.RunPython(update_template, revert_template),
    ]
