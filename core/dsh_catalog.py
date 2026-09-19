from __future__ import annotations

from pathlib import Path

import yaml
from django.conf import settings


def _dsh_home() -> Path | None:
    raw = (getattr(settings, "DSH_HOME", "") or "").strip()
    return Path(raw).expanduser() if raw else None


def _bundled_skills_root() -> Path:
    return Path(settings.BASE_DIR) / "deploy" / "dsh" / "skills"


def _skill_roots() -> list[Path]:
    roots = [_bundled_skills_root()]
    home = _dsh_home()
    if home is not None:
        roots.append(home / "skills")
    return roots


def _model_yaml_paths() -> list[Path]:
    paths = []
    home = _dsh_home()
    if home is not None:
        paths.append(home / "settings.yaml")
    paths.append(Path(settings.BASE_DIR) / "deploy" / "dsh" / "settings.yaml.example")
    return paths


def _parse_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def list_dsh_skills() -> list[tuple[str, str]]:
    """Return unique (id, label) pairs from SKILL.md trees, later roots override."""
    skills: dict[str, str] = {}
    for root in _skill_roots():
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            data = _parse_frontmatter(skill_md)
            name = str(data.get("name") or "").strip() or skill_md.parent.name
            skills[name] = name
    return [(name, name) for name in sorted(skills)]


def _provider_label(provider_id, provider: dict) -> str:
    name = str(provider.get("displayName") or "").strip()
    if name:
        return name
    return str(provider_id or "").strip() or "Other"


def _models_from_yaml(path: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    if not path.is_file():
        return []
    data = _load_yaml(path)
    providers = ((data.get("llm-pi-ai") or {}).get("providers") or {})
    if not isinstance(providers, dict):
        return []
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    seen: set[str] = set()
    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        items: list[tuple[str, str]] = []
        for item in provider.get("models") or []:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            label = str(item.get("name") or model_id).strip() or model_id
            items.append((model_id, label))
        if items:
            groups.append((_provider_label(provider_id, provider), items))
    return groups


def list_dsh_model_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    """Prefer live DSH settings.yaml; fall back to the bundled SiliconFlow catalog."""
    for path in _model_yaml_paths():
        groups = _models_from_yaml(path)
        if groups:
            return groups
    return []


def list_dsh_models() -> list[tuple[str, str]]:
    """Flat (id, label) pairs in catalog order, grouped by provider in the form."""
    return [
        (model_id, label)
        for _provider, models in list_dsh_model_groups()
        for model_id, label in models
    ]


def dsh_model_labels() -> dict[str, str]:
    return {model_id: label for model_id, label in list_dsh_models()}
