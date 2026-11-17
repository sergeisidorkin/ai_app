from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0062_proposal_status_draft"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="dispatch_email_subject",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Заголовок письма",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="dispatch_email_body_html",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Текст письма (уведомления)",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="dispatch_email_customized",
            field=models.BooleanField(
                default=False,
                verbose_name="Письмо отредактировано вручную",
            ),
        ),
    ]
