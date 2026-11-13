from django.db import migrations, models


def copy_preliminary_status_to_document_kind(apps, schema_editor):
    ProposalRegistration = apps.get_model("proposals_app", "ProposalRegistration")
    ProposalRegistration.objects.filter(status="preliminary").update(document_kind="preliminary")


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0060_proposalregistration_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="document_kind",
            field=models.CharField(
                choices=[("final", "Итоговое"), ("preliminary", "Предварительное")],
                db_index=True,
                default="final",
                max_length=20,
                verbose_name="Вид",
            ),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="kind",
            field=models.CharField(
                choices=[("regular", "Обычные"), ("owed_to_us", "Должны нам")],
                db_index=True,
                default="regular",
                max_length=20,
                verbose_name="Категория",
            ),
        ),
        migrations.RunPython(copy_preliminary_status_to_document_kind, migrations.RunPython.noop),
    ]
