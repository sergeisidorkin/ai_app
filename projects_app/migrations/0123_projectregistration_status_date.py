from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0122_convert_project_stages"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="status_date",
            field=models.DateField(
                blank=True,
                help_text="Заполняется автоматически при смене статуса. В админке можно изменить вручную.",
                null=True,
                verbose_name="Дата статуса",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="summary_status_date",
            field=models.DateField(
                blank=True,
                help_text="Заполняется автоматически, когда меняется статус сводной строки реестра.",
                null=True,
                verbose_name="Дата статуса сводной строки",
            ),
        ),
        migrations.AddField(
            model_name="registrationgroupsummarystate",
            name="status_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата статуса"),
        ),
    ]
