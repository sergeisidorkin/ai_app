import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0059_product_group"),
        ("contracts_app", "0046_update_deadline_ru_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="contractprojectregistrationproduct",
            name="product_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_project_registration_member_links",
                to="policy_app.product",
                verbose_name="Групповой продукт",
            ),
        ),
    ]
