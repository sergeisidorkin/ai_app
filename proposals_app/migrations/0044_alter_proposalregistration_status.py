from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0043_alter_proposalregistration_number_range"),
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
                    ("not_held", "Несостоявшееся"),
                ],
                db_index=True,
                default="final",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
    ]
