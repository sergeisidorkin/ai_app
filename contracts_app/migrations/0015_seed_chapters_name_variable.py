from django.db import migrations
from django.db.models import Max


def seed_chapters_var(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    if not ContractVariable.objects.filter(key="[[chapters_name]]").exists():
        mx_pos = ContractVariable.objects.aggregate(m=Max("position"))["m"] or 0
        ContractVariable.objects.create(
            key="[[chapters_name]]",
            description="Многоуровневый список: активы, разделы, подразделы",
            is_computed=True,
            source_section="",
            source_table="",
            source_column="",
            position=mx_pos + 1,
        )


def remove_chapters_var(apps, schema_editor):
    ContractVariable = apps.get_model("contracts_app", "ContractVariable")
    ContractVariable.objects.filter(key="[[chapters_name]]").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("contracts_app", "0014_seed_actives_name_list_variable"),
    ]

    operations = [
        migrations.RunPython(seed_chapters_var, remove_chapters_var),
    ]
