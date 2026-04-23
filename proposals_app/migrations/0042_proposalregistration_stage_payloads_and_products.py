from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0040_backfill_consulting_catalog_refs"),
        ("proposals_app", "0041_proposalregistration_workspace_file_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="stage_payloads_json",
            field=models.JSONField(blank=True, default=list, verbose_name="Данные этапов ТКП"),
        ),
        migrations.CreateModel(
            name="ProposalRegistrationProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(default=1, verbose_name="Ранг")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="proposal_registration_links",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_links",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП",
                    ),
                ),
            ],
            options={
                "verbose_name": "Продукт ТКП",
                "verbose_name_plural": "Продукты ТКП",
                "ordering": ["rank", "id"],
                "unique_together": {("proposal", "product")},
            },
        ),
    ]
