from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0118_sync_tpgr_dash_suspended_hyphen"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrationGroupSummaryState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "number",
                    models.PositiveIntegerField(
                        validators=[MinValueValidator(0), MaxValueValidator(9999)],
                        verbose_name="Номер",
                    ),
                ),
                (
                    "group_label",
                    models.CharField(blank=True, default="", max_length=64, verbose_name="Группа"),
                ),
                (
                    "deferred",
                    models.BooleanField(default=False, verbose_name="Отложен"),
                ),
            ],
            options={
                "verbose_name": "Статус сводной строки реестра",
                "verbose_name_plural": "Статусы сводных строк реестра",
            },
        ),
        migrations.AddConstraint(
            model_name="registrationgroupsummarystate",
            constraint=models.UniqueConstraint(
                fields=("number", "group_label"),
                name="uniq_registration_group_summary_state",
            ),
        ),
    ]
