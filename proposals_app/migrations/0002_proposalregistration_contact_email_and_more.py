from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="contact_email",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Эл. почта"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="contact_full_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="ФИО"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="docx_file_link",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="Ссылка на DOCX"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="docx_file_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование файла DOCX"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="pdf_file_link",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="Ссылка на PDF"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="pdf_file_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование файла PDF"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Получатель"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="sent_date",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Дата отправки"),
        ),
    ]
