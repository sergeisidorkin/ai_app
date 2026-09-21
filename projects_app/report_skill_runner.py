from __future__ import annotations

import copy
import json
import logging
import shutil
import uuid
from pathlib import Path

import yaml
from django.conf import settings

from core.dsh_run import DshRunError, run_headless

from .docx_comments import DocxCommentError, count_comments, strip_comments
from .models import PerformerReportUpload, ReportCheckRule
from .report_macro_runner import (
    apply_report_macro_checks,
    list_macros_for_upload,
    matching_check_rules,
    store_report_check_status,
)

log = logging.getLogger(__name__)
REPORT_CHECK_DSH_PROFILE = "report-check"


class ReportSkillRunError(RuntimeError):
    """A DSH report skill did not produce a valid output file."""


def list_skill_rules_for_upload(
    upload: PerformerReportUpload,
) -> list[ReportCheckRule]:
    rules = list(
        ReportCheckRule.objects
        .filter(check_type=ReportCheckRule.CheckType.SKILL)
        .order_by("position", "id")
    )
    return matching_check_rules(upload, rules)


def has_skill_rules_for_upload(upload: PerformerReportUpload) -> bool:
    return bool(list_skill_rules_for_upload(upload))


def apply_report_checks(
    upload: PerformerReportUpload,
    file_bytes: bytes,
) -> bytes:
    """Run matching DSH skills as a file pipeline, then matching macros."""
    skill_rules = list_skill_rules_for_upload(upload)
    if not skill_rules:
        return apply_report_macro_checks(upload, file_bytes)

    store_report_check_status(
        upload,
        PerformerReportUpload.CheckStatus.RUNNING,
        0,
        "",
    )
    try:
        processed = run_report_skill_rules(upload, file_bytes, skill_rules)
    except Exception as exc:
        if not isinstance(exc, (DshRunError, ReportSkillRunError)):
            log.exception("Report skill check failed for upload %s", upload.pk)
        store_report_check_status(
            upload,
            PerformerReportUpload.CheckStatus.ERROR,
            0,
            str(exc),
        )
        return file_bytes

    if list_macros_for_upload(upload):
        return apply_report_macro_checks(upload, processed)

    try:
        finding_count = (
            count_comments(processed)
            if Path(upload.file_name or "").suffix.lower() == ".docx"
            else 0
        )
    except DocxCommentError as exc:
        store_report_check_status(
            upload,
            PerformerReportUpload.CheckStatus.ERROR,
            0,
            f"DSH вернул некорректный DOCX: {exc}",
        )
        return file_bytes

    store_report_check_status(
        upload,
        PerformerReportUpload.CheckStatus.DONE,
        finding_count,
        "",
    )
    return processed


def run_report_skill_rules(
    upload: PerformerReportUpload,
    file_bytes: bytes,
    rules: list[ReportCheckRule] | None = None,
) -> bytes:
    rules = rules if rules is not None else list_skill_rules_for_upload(upload)
    if not rules:
        return file_bytes

    workspace_value = (
        getattr(settings, "DSH_SORT_WORKSPACE", "") or ""
    ).strip()
    if not workspace_value:
        raise ReportSkillRunError(
            "Не задан DSH_SORT_WORKSPACE для проверки отчётов."
        )
    workspace = Path(workspace_value).expanduser()

    input_name = Path(upload.file_name or "report.bin").name or "report.bin"
    extension = Path(input_name).suffix.lower()
    run_root = (
        workspace
        / "report-checks"
        / f"upload-{upload.pk or 'new'}-{uuid.uuid4().hex}"
    )
    current_bytes = file_bytes
    try:
        for index, rule in enumerate(rules, start=1):
            _sync_local_bundled_skill(rule.check_value)
            rule_root = run_root / f"{index:02d}-{rule.pk or 'rule'}"
            input_dir = rule_root / "input"
            output_dir = rule_root / "output"
            input_dir.mkdir(parents=True, exist_ok=False)
            output_dir.mkdir(parents=True, exist_ok=False)
            input_bytes = current_bytes
            if rule.clear_comments and extension == ".docx":
                input_bytes = strip_comments(current_bytes)
            (input_dir / input_name).write_bytes(input_bytes)
            profile = _prepare_model_runtime(rule_root, rule.model_id)

            run_headless(
                _skill_prompt(rule, input_name),
                cwd=rule_root,
                profile=profile,
            )
            result_path = _result_file(output_dir, input_name, extension)
            try:
                current_bytes = result_path.read_bytes()
            except OSError as exc:
                raise ReportSkillRunError(
                    f"Не удалось прочитать результат навыка «{rule.check_value}»: {exc}"
                ) from exc
            if not current_bytes:
                raise ReportSkillRunError(
                    f"Навык «{rule.check_value}» вернул пустой файл."
                )
        return current_bytes
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось подготовить рабочий каталог DSH: {exc}"
        ) from exc
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


def _prepare_model_runtime(rule_root: Path, model_id: str) -> str | None:
    selected_model = (model_id or "").strip()
    if not selected_model:
        return None
    host_home = _dsh_host_home()
    if host_home is None:
        raise ReportSkillRunError(
            "Не найден каталог DSH_HOME для выбора модели проверки."
        )

    provider_id, model_config, provider_config = _find_model_route(
        selected_model,
        host_home,
    )
    runtime_settings = _load_runtime_settings(host_home)
    llm = runtime_settings.setdefault("llm-pi-ai", {})
    providers = llm.setdefault("providers", {})
    if provider_id not in providers:
        providers[provider_id] = copy.deepcopy(provider_config)
    provider = providers[provider_id]
    models = provider.setdefault("models", [])
    if not any(
        isinstance(item, dict)
        and str(item.get("id") or "").strip() == selected_model
        for item in models
    ):
        models.append(copy.deepcopy(model_config))
    runtime_settings["agent-default-model"] = {
        "provider": provider_id,
        "model": selected_model,
    }
    try:
        (rule_root / "settings.yaml").write_text(
            yaml.safe_dump(
                runtime_settings,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        _ensure_report_check_profile(host_home)
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось подготовить модель DSH «{selected_model}»: {exc}"
        ) from exc
    return REPORT_CHECK_DSH_PROFILE


def _dsh_host_home() -> Path | None:
    configured = (getattr(settings, "DSH_HOME", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    compose_dir = (getattr(settings, "DSH_COMPOSE_DIR", "") or "").strip()
    if compose_dir:
        return Path(compose_dir).expanduser() / "home"
    return None


def _model_settings_paths(host_home: Path) -> list[Path]:
    return [
        host_home / "settings.yaml",
        Path(settings.BASE_DIR) / "deploy" / "dsh" / "settings.yaml.example",
    ]


def _load_yaml_mapping(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _find_model_route(
    model_id: str,
    host_home: Path,
) -> tuple[str, dict, dict]:
    for path in _model_settings_paths(host_home):
        data = _load_yaml_mapping(path)
        providers = ((data.get("llm-pi-ai") or {}).get("providers") or {})
        if not isinstance(providers, dict):
            continue
        for provider_id, provider in providers.items():
            if not isinstance(provider, dict):
                continue
            for model in provider.get("models") or []:
                if (
                    isinstance(model, dict)
                    and str(model.get("id") or "").strip() == model_id
                ):
                    return str(provider_id), model, provider
    raise ReportSkillRunError(
        f"Модель DSH «{model_id}» отсутствует в каталоге."
    )


def _load_runtime_settings(host_home: Path) -> dict:
    for path in _model_settings_paths(host_home):
        data = _load_yaml_mapping(path)
        if data:
            return copy.deepcopy(data)
    raise ReportSkillRunError("Не удалось прочитать settings.yaml DSH.")


def _ensure_report_check_profile(host_home: Path) -> None:
    profile_dir = host_home / "profiles" / REPORT_CHECK_DSH_PROFILE
    profile_dir.mkdir(parents=True, exist_ok=True)
    package = {
        "name": "dsh-profile-report-check",
        "private": True,
        "dependencies": {},
        "dsh": {
            "profile": {
                "bundles": [
                    "@deepseek-ai/dsh-base",
                    "@deepseek-ai/dsh-headless",
                ],
                "patchReload": "startup",
            },
        },
    }
    patch = (
        "- id: settings\n"
        "  config:\n"
        "    path: settings.yaml\n"
        "    watch: false\n"
    )
    _write_runtime_file(
        profile_dir / "package.json",
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
    )
    _write_runtime_file(profile_dir / "cordis.patch.yml", patch)


def _write_runtime_file(path: Path, content: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _sync_local_bundled_skill(skill_name: str) -> None:
    """Keep the native development DSH home in sync without a stack restart."""
    name = (skill_name or "").strip()
    if (
        not name
        or name != Path(name).name
        or "/" in name
        or "\\" in name
    ):
        raise ReportSkillRunError("Некорректное имя навыка DSH.")

    dsh_home_value = (getattr(settings, "DSH_HOME", "") or "").strip()
    if not dsh_home_value:
        return
    dsh_home = Path(dsh_home_value).expanduser().resolve()
    local_data = (
        Path(settings.BASE_DIR) / "deploy" / "dsh" / "data"
    ).resolve()
    if not dsh_home.is_relative_to(local_data):
        return

    source = Path(settings.BASE_DIR) / "deploy" / "dsh" / "skills" / name
    if not source.is_dir():
        return
    destination = dsh_home / "skills" / name
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True)
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось обновить локальный навык DSH «{name}»: {exc}"
        ) from exc


def _skill_prompt(rule: ReportCheckRule, input_name: str) -> str:
    model_note = (
        f"\nНастроенная для правила модель DSH: {rule.model_id}."
        if (rule.model_id or "").strip()
        else ""
    )
    return (
        f"/{rule.check_value}\n\n"
        "Обработай ровно один исходный файл этой проверки.\n"
        f"Вход: input/{input_name}\n"
        f"Результат обязательно запиши: output/{input_name}\n"
        "Результатом должен быть обработанный или пересозданный файл, "
        "а не JSON или текст ответа. Не меняй расширение файла."
        f"{model_note}"
    )


def _result_file(
    output_dir: Path,
    input_name: str,
    extension: str,
) -> Path:
    expected = output_dir / input_name
    if expected.is_file():
        return expected
    candidates = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() == extension
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ReportSkillRunError(
            "DSH не создал обработанный файл в каталоге output."
        )
    raise ReportSkillRunError(
        "DSH создал несколько файлов результата; ожидался один."
    )
