import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0059_product_group"),
        ("proposals_app", "0056_proposalregistration_term_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistrationproduct",
            name="product_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_registration_member_links",
                to="policy_app.product",
                verbose_name="Групповой продукт",
            ),
        ),
    ]
