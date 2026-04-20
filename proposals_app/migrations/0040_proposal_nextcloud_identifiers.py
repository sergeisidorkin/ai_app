from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0039_seed_budget_table_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="docx_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор DOCX в Nextcloud",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="pdf_file_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Идентификатор PDF в Nextcloud",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="proposal_workspace_target_path",
            field=models.CharField(
                blank=True,
                default="",
                max_length=1024,
                verbose_name="Путь к рабочей папке ТКП у пользователя в Nextcloud",
            ),
        ),
    ]
