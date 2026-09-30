from pathlib import Path

import yaml
from django.db import migrations


def chunk_compatible_skill_names() -> set[str]:
    """Навыки с реализованным pipeline.yaml. Остальные раньше шли целиком через агента."""
    root = Path(__file__).resolve().parents[2] / "deploy" / "dsh" / "skills"
    names = set()
    if not root.is_dir():
        return names
    for path in root.glob("*/pipeline.yaml"):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        if str(raw.get("execution_mode") or "").strip() == "local_chunks":
            names.add(path.parent.name)
    return names


def assign_existing_skill_processing_modes(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    ReportMacro.objects.filter(check_kind="skill").exclude(
        skill_name__in=chunk_compatible_skill_names()
    ).update(processing_mode="agent")


def restore_chunk_processing_mode(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    ReportMacro.objects.filter(check_kind="skill").exclude(
        skill_name__in=chunk_compatible_skill_names()
    ).update(processing_mode="chunks")


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0115_report_macro_temperature"),
    ]

    operations = [
        migrations.RunPython(
            assign_existing_skill_processing_modes,
            restore_chunk_processing_mode,
        ),
    ]
