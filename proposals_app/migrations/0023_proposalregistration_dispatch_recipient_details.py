from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("classifiers_app", "0046_businessentityrecord_record_author_and_source"),
        ("proposals_app", "0022_proposalregistration_recipient_job_title_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_dispatch_recipients",
                to="classifiers_app.oksmcountry",
                verbose_name="Страна",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_identifier",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Идентификатор"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_registration_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата регистрации"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_registration_number",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Регистрационный номер"),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="recipient",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Наименование организации (краткое)",
            ),
        ),
    ]
