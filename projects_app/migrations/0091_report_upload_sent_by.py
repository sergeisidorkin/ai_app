from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects_app", "0090_report_check_finding_threshold"),
    ]

    operations = [
        migrations.AddField(
            model_name="performerreportupload",
            name="sent_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="performer_report_sends",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Отправил",
            ),
        ),
        migrations.AlterField(
            model_name="performerreportupload",
            name="uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="performer_report_uploads",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Загрузил",
            ),
        ),
    ]
