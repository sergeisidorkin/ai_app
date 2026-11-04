from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0052_production_calendar_day_details"),
        ("proposals_app", "0057_proposal_product_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="customer_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_customer_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор заказчика",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="asset_owner_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_asset_owner_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор владельца активов",
            ),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="recipient_identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_recipient_registrations",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор получателя",
            ),
        ),
        migrations.AddField(
            model_name="proposalasset",
            name="identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_asset_identifier_links",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор бизнес-сущности",
            ),
        ),
        migrations.AddField(
            model_name="proposallegalentity",
            name="identifier_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_legal_entity_identifier_links",
                to="classifiers_app.businessentityidentifierrecord",
                verbose_name="Идентификатор бизнес-сущности",
            ),
        ),
    ]
