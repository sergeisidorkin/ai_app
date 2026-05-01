from django.db import migrations
from django.db.models import Max


def seed_facsimile_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    variable = ProposalVariable.objects.filter(key="[[facsimile]]").first()
    if variable:
        variable.description = "Подпись пользователя"
        variable.is_computed = True
        variable.source_section = ""
        variable.source_table = ""
        variable.source_column = ""
        variable.save(
            update_fields=[
                "description",
                "is_computed",
                "source_section",
                "source_table",
                "source_column",
            ]
        )
        return

    max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
    ProposalVariable.objects.create(
        key="[[facsimile]]",
        description="Подпись пользователя",
        is_computed=True,
        position=max_position + 1,
        source_section="",
        source_table="",
        source_column="",
    )


def remove_facsimile_variable(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0046_proposaltemplate_multiselect_scope"),
    ]

    operations = [
        migrations.RunPython(
            seed_facsimile_variable,
            remove_facsimile_variable,
        ),
    ]
