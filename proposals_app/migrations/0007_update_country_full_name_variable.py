from django.db import migrations


def ensure_country_full_name_variable(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")

    defaults = {
        "description": "Наименование страны (полное)",
        "position": 2,
        "source_section": "proposals",
        "source_table": "registry",
        "source_column": "country_full_name",
    }

    existing = ProposalVariable.objects.filter(key="{{country_full_name}}").order_by("id")
    variable = existing.first()
    if variable:
        for field, value in defaults.items():
            setattr(variable, field, value)
        variable.save(update_fields=list(defaults.keys()))
        existing.exclude(pk=variable.pk).delete()
        return

    ProposalVariable.objects.create(
        key="{{country_full_name}}",
        **defaults,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0006_proposalregistration_contract_fields"),
    ]

    operations = [
        migrations.RunPython(ensure_country_full_name_variable, migrations.RunPython.noop),
    ]
