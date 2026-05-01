from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0008_groupmember_seal_file"),
        ("projects_app", "0057_performer_contract_pdf_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="contract_group_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_performers",
                to="group_app.groupmember",
                verbose_name="Группа договора",
            ),
        ),
    ]
