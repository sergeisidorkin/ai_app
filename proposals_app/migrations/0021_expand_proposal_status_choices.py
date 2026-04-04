from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0020_proposalregistration_proposal_workspace_public_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposalregistration",
            name="status",
            field=models.CharField(
                choices=[
                    ("preliminary", "Предварительное"),
                    ("final", "Итоговое"),
                    ("sent", "Отправленное"),
                    ("completed", "Завершённое"),
                ],
                db_index=True,
                default="final",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
    ]
