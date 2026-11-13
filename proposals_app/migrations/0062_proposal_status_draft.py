from django.db import migrations, models


def move_legacy_statuses_to_draft(apps, schema_editor):
    ProposalRegistration = apps.get_model("proposals_app", "ProposalRegistration")
    ProposalRegistration.objects.filter(status__in=["preliminary", "final"]).update(status="draft")


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0061_proposalregistration_document_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposalregistration",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Черновик"),
                    ("sent", "Отправленное"),
                    ("completed", "Завершённое"),
                    ("postponed", "Отложенное"),
                    ("not_held", "Несостоявшееся"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.RunPython(move_legacy_statuses_to_draft, migrations.RunPython.noop),
    ]
