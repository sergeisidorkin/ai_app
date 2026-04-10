from django.db import migrations
from django.db.models import Max


def seed_service_type_short_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    if ProposalVariable.objects.filter(key="{{service_type_short}}").exists():
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="{{service_type_short}}",
        description="Наименование ТКП (проекта) (краткое)",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_service_type_short_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.filter(key="{{service_type_short}}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0029_seed_client_owner_name_variable"),
    ]

    operations = [
        migrations.RunPython(
            seed_service_type_short_variable,
            remove_service_type_short_variable,
        ),
    ]
