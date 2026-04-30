import django.db.models.deletion
from django.db import migrations, models


def copy_contract_template_products(apps, schema_editor):
    ContractTemplate = apps.get_model("contracts_app", "ContractTemplate")
    through_model = ContractTemplate.products.through
    rows = []
    for template_id, product_id in (
        ContractTemplate.objects
        .exclude(product_id__isnull=True)
        .values_list("pk", "product_id")
    ):
        rows.append(
            through_model(
                contracttemplate_id=template_id,
                product_id=product_id,
            )
        )
    if rows:
        through_model.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0022_contracttemplate_group_members"),
        ("policy_app", "0042_servicegoalreport_product_name_and_report_title_label"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contracttemplate",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contract_templates",
                to="policy_app.product",
                verbose_name="Продукт",
            ),
        ),
        migrations.AddField(
            model_name="contracttemplate",
            name="products",
            field=models.ManyToManyField(
                blank=True,
                related_name="contract_template_sets",
                to="policy_app.product",
                verbose_name="Продукты",
            ),
        ),
        migrations.RunPython(copy_contract_template_products, migrations.RunPython.noop),
    ]
