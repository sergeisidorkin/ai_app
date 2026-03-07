from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0016_performer_work_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="participation_deadline_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Срок подтверждения"),
        ),
        migrations.AddField(
            model_name="performer",
            name="participation_request_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата отправки запроса"),
        ),
        migrations.AddField(
            model_name="performer",
            name="participation_response",
            field=models.CharField(
                blank=True,
                choices=[
                    ("confirmed", "Подтверждаю участие"),
                    ("declined", "Не готов(а) участвовать"),
                ],
                default="",
                max_length=20,
                verbose_name="Ответ на запрос",
            ),
        ),
        migrations.AddField(
            model_name="performer",
            name="participation_response_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Дата ответа на запрос"),
        ),
    ]
