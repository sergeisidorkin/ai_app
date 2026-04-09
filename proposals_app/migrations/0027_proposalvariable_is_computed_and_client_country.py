from django.db import migrations, models
from django.db.models import Max


def _upsert_computed_variable(ProposalVariable, *, keys, target_key, description, fallback_position):
    existing = list(
        ProposalVariable.objects.filter(key__in=keys).order_by("position", "id")
    )
    variable = existing[0] if existing else None

    if variable is None:
        max_position = ProposalVariable.objects.aggregate(m=Max("position"))["m"] or 0
        ProposalVariable.objects.create(
            key=target_key,
            description=description,
            is_computed=True,
            position=max_position + 1,
            source_section="",
            source_table="",
            source_column="",
        )
        return

    variable.key = target_key
    variable.description = description
    variable.is_computed = True
    variable.source_section = ""
    variable.source_table = ""
    variable.source_column = ""
    if not variable.position:
        variable.position = fallback_position
    variable.save(
        update_fields=[
            "key",
            "description",
            "is_computed",
            "source_section",
            "source_table",
            "source_column",
            "position",
        ]
    )

    duplicate_ids = [item.pk for item in existing[1:]]
    if duplicate_ids:
        ProposalVariable.objects.filter(pk__in=duplicate_ids).delete()


def migrate_proposal_variables(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")

    _upsert_computed_variable(
        ProposalVariable,
        keys=["{{year}}"],
        target_key="{{year}}",
        description="Текущий год (гггг)",
        fallback_position=1000,
    )
    _upsert_computed_variable(
        ProposalVariable,
        keys=["{{day}}"],
        target_key="{{day}}",
        description="Текущий день (дд)",
        fallback_position=1001,
    )
    _upsert_computed_variable(
        ProposalVariable,
        keys=["{{month}}"],
        target_key="{{month}}",
        description="Текущий месяц на русском языке",
        fallback_position=1002,
    )
    _upsert_computed_variable(
        ProposalVariable,
        keys=["{{client_country_full_name}}", "{{country_full_name}}"],
        target_key="{{client_country_full_name}}",
        description="Наименование страны Заказчика (полное)",
        fallback_position=2,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0026_seed_computed_proposal_variables"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalvariable",
            name="is_computed",
            field=models.BooleanField(default=False, verbose_name="Расчётное поле"),
        ),
        migrations.RunPython(
            migrate_proposal_variables,
            migrations.RunPython.noop,
        ),
    ]
