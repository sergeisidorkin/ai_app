from __future__ import annotations

import json
from functools import lru_cache
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


REASONING_LEVEL_ORDER = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
REASONING_LEVEL_LABELS = {
    "off": "Выкл.",
    "minimal": "Минимальный",
    "low": "Низкий",
    "medium": "Средний",
    "high": "Высокий",
    "xhigh": "Очень высокий",
    "max": "Максимальный",
}
_QWEN_THINKING_FORMATS = {"qwen", "qwen-chat-template"}
_CATALOG_PROVIDER_PRIORITY = (
    "qwen-token-plan",
    "qwen-token-plan-cn",
    "qwen-token-plan-individual",
    "zai",
    "zai-coding-cn",
    "deepseek",
    "moonshotai",
    "moonshotai-cn",
    "minimax",
    "minimax-cn",
    "huggingface",
    "together",
    "groq",
    "fireworks",
    "openrouter",
    "nvidia",
)


def _pi_ai_catalog_dir() -> Path:
    return (
        Path(settings.BASE_DIR)
        / "deploy"
        / "dsh"
        / "data"
        / "npm"
        / "node_modules"
        / "@earendil-works"
        / "pi-ai"
        / "dist"
        / "providers"
        / "data"
    )


def _supported_reasoning_levels(thinking_map: dict) -> tuple[tuple[str, str], ...]:
    """Levels pi-ai would offer, with the wire value sent for each.

    A null map entry means the level is not supported. A missing entry is
    supported for the base levels and unsupported for xhigh and max. The wire
    string is what the provider expects; when the map omits it, the level name
    itself is sent.
    """
    levels = []
    for level in REASONING_LEVEL_ORDER:
        if level not in thinking_map:
            if level in {"xhigh", "max"}:
                continue
            levels.append((level, level))
            continue
        mapped = thinking_map[level]
        if mapped is None:
            continue
        wire = mapped if isinstance(mapped, str) and mapped else level
        levels.append((level, wire))
    return tuple(levels)


def _walk_catalog_models(node):
    if isinstance(node, dict):
        model_id = node.get("id")
        thinking_map = node.get("thinkingLevelMap")
        if isinstance(model_id, str) and isinstance(thinking_map, dict):
            yield model_id, thinking_map
        for value in node.values():
            yield from _walk_catalog_models(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_catalog_models(value)


@lru_cache(maxsize=1)
def _catalog_reasoning_index() -> tuple[dict[str, tuple[tuple[str, str], ...]], dict[str, tuple[tuple[str, str], ...]]]:
    exact: dict[str, tuple[int, tuple[tuple[str, str], ...]]] = {}
    tails: dict[str, tuple[int, tuple[tuple[str, str], ...]]] = {}
    catalog_dir = _pi_ai_catalog_dir()
    if not catalog_dir.is_dir():
        return {}, {}
    files = sorted(catalog_dir.glob("*.json"))
    files.sort(
        key=lambda path: (
            _CATALOG_PROVIDER_PRIORITY.index(path.stem)
            if path.stem in _CATALOG_PROVIDER_PRIORITY
            else len(_CATALOG_PROVIDER_PRIORITY)
        )
    )
    for path in files:
        priority = (
            _CATALOG_PROVIDER_PRIORITY.index(path.stem)
            if path.stem in _CATALOG_PROVIDER_PRIORITY
            else len(_CATALOG_PROVIDER_PRIORITY)
        )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for model_id, thinking_map in _walk_catalog_models(data):
            levels = _supported_reasoning_levels(thinking_map)
            if not levels:
                continue
            for key, bucket in (
                (model_id.casefold(), exact),
                (model_id.rsplit("/", 1)[-1].casefold(), tails),
            ):
                current = bucket.get(key)
                if current is None or priority < current[0]:
                    bucket[key] = (priority, levels)
    return (
        {key: levels for key, (_priority, levels) in exact.items()},
        {key: levels for key, (_priority, levels) in tails.items()},
    )


def catalog_reasoning_levels(model_id: str) -> tuple[tuple[str, str], ...] | None:
    """(level, wire) pairs from the installed pi-ai catalog, if this id is known."""
    exact, tails = _catalog_reasoning_index()
    key = (model_id or "").strip().casefold()
    if not key:
        return None
    found = exact.get(key)
    if found is None:
        found = tails.get(key.rsplit("/", 1)[-1])
    return found


def reasoning_levels_for_entry(provider: dict, model: dict) -> list[str]:
    """Levels the report-check form can offer for one settings model.

    An explicit reasoningEfforts map in settings wins. Otherwise the installed
    pi-ai catalog supplies the model's own scale. Qwen routes can always turn
    thinking off; a route with neither a map nor a catalog entry can only
    choose off or low.
    """
    efforts = model.get("reasoningEfforts", None)
    if efforts is False:
        return ["off"]
    if isinstance(efforts, dict) and efforts:
        declared = [level for level in REASONING_LEVEL_ORDER if level in efforts]
        if "off" not in declared:
            declared.insert(0, "off")
        return declared or ["off"]
    thinking = str((provider.get("compat") or {}).get("thinkingFormat") or "")
    catalog = catalog_reasoning_levels(str(model.get("id") or ""))
    if catalog:
        levels = [level for level, _wire in catalog]
        if thinking in _QWEN_THINKING_FORMATS and "off" not in levels:
            levels.insert(0, "off")
        return levels or ["off"]
    if thinking in _QWEN_THINKING_FORMATS:
        return ["off", "low"]
    return ["off"]


def parse_reasoning_level(raw: str) -> str:
    value = (raw or "").strip()
    if value in REASONING_LEVEL_LABELS:
        return value
    folded = value.casefold().rstrip(".")
    if folded == "выкл":
        return "off"
    for code, label in REASONING_LEVEL_LABELS.items():
        if folded == label.casefold().rstrip("."):
            return code
    return value


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


def _providers_from_catalog() -> dict:
    for path in _model_yaml_paths():
        providers = ((_load_yaml(path).get("llm-pi-ai") or {}).get("providers") or {})
        if isinstance(providers, dict) and providers:
            return providers
    return {}


def list_dsh_model_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    """Prefer live DSH settings.yaml; fall back to the bundled SiliconFlow catalog."""
    for path in _model_yaml_paths():
        groups = _models_from_yaml(path)
        if groups:
            return groups
    return []


def reasoning_levels_by_model() -> dict[str, list[str]]:
    """Map each catalog model id to the reasoning levels its route can request."""
    levels: dict[str, list[str]] = {}
    for provider in _providers_from_catalog().values():
        if not isinstance(provider, dict):
            continue
        for item in provider.get("models") or []:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if model_id and model_id not in levels:
                levels[model_id] = reasoning_levels_for_entry(provider, item)
    return levels


def list_dsh_models() -> list[tuple[str, str]]:
    """Flat (id, label) pairs in catalog order, grouped by provider in the form."""
    return [
        (model_id, label)
        for _provider, models in list_dsh_model_groups()
        for model_id, label in models
    ]


def dsh_model_labels() -> dict[str, str]:
    return {model_id: label for model_id, label in list_dsh_models()}
