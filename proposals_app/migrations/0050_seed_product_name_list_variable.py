from django.db import migrations
from django.db.models import Max


def seed_product_name_list_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="[[product_name]]").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[product_name]]",
        description="Наименование продукта",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_product_name_list_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0049_seed_stages_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_product_name_list_variable,
            remove_product_name_list_variable,
        ),
    ]
