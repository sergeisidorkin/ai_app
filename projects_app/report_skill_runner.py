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

from .docx_comments import DocxCommentError, strip_comments
from .models import (
    PerformerReportUpload,
    ReportCheckLine,
    ReportCheckRule,
    ReportMacro,
    report_line_participates,
)
from .report_chunk_skill_runner import run_chunked_skill_lines
from .report_macro_runner import (
    ReportCheckAborted,
    apply_report_macro_checks,
    combined_clear_rule_ids,
    list_macros_for_upload,
    matching_check_rules,
    recount_report_findings,
    store_report_check_status,
    store_report_macro_progress,
    touch_report_check_heartbeat,
)

log = logging.getLogger(__name__)
REPORT_CHECK_DSH_PROFILE = "report-check"
REPORT_CHECK_TEXT_PROFILE = "report-check-text"
REPORT_CHECK_TEMPERATURE_FILE = "report-check-temperature.json"
AGENT_OUTPUT_TOKENS = 32_768
AGENT_TIMEOUT_SECONDS = 45 * 60
_TEXT_ONLY_TOOL_PLUGINS = (
    "tool-bash",
    "tool-pwsh",
    "tool-jobs",
    "tool-fs",
    "tool-fs-search",
    "tool-skill",
    "tool-subagent-control",
    "tool-subagent-list-agents",
    "tool-subagent",
    "tool-subagent-fork",
    "tool-workflow",
    "tool-todo",
    "tool-goal",
    "tool-ralph",
    "tool-web",
)


class ReportSkillRunError(RuntimeError):
    """A DSH report skill did not produce a valid output file."""


def list_skill_rules_for_upload(
    upload: PerformerReportUpload,
) -> list[ReportCheckRule]:
    rules = list(
        ReportCheckRule.objects
        .prefetch_related("lines__macro")
        .order_by("position", "id")
    )
    matched = matching_check_rules(upload, rules)
    return [
        rule
        for rule in matched
        if any(
            report_line_participates(line)
            and line.check_type == ReportCheckRule.CheckType.SKILL
            and line.macro_id
            for line in rule.lines.all()
        )
    ]


def skill_lines_for_rules(rules: list[ReportCheckRule]) -> list[ReportCheckLine]:
    lines: list[ReportCheckLine] = []
    for rule in rules:
        ordered = sorted(rule.lines.all(), key=lambda item: (item.position, item.pk or 0))
        for line in ordered:
            if (
                report_line_participates(line)
                and line.check_type == ReportCheckRule.CheckType.SKILL
                and line.macro_id
            ):
                lines.append(line)
    return lines


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

    if not store_report_check_status(
        upload,
        PerformerReportUpload.CheckStatus.RUNNING,
        0,
        "",
    ):
        raise ReportCheckAborted()
    source_bytes = file_bytes
    skip_clear_rule_ids: set[int] = set()
    combined_ids = combined_clear_rule_ids(skill_rules)
    if combined_ids and Path(upload.file_name or "").suffix.lower() == ".docx":
        try:
            file_bytes = strip_comments(file_bytes)
        except DocxCommentError as exc:
            store_report_check_status(
                upload,
                PerformerReportUpload.CheckStatus.ERROR,
                0,
                str(exc),
            )
            return source_bytes
        skip_clear_rule_ids = combined_ids
    try:
        processed = run_report_skill_rules(
            upload,
            file_bytes,
            skill_rules,
            skip_clear_rule_ids=skip_clear_rule_ids,
        )
    except Exception as exc:
        if not isinstance(exc, (DshRunError, ReportSkillRunError)):
            log.exception("Report skill check failed for upload %s", upload.pk)
        store_report_check_status(
            upload,
            PerformerReportUpload.CheckStatus.ERROR,
            0,
            str(exc),
        )
        return source_bytes

    if list_macros_for_upload(upload):
        return apply_report_macro_checks(
            upload,
            processed,
            skip_clear_rule_ids=skip_clear_rule_ids,
        )

    finding_count = 0
    by_author: dict[str, int] = {}
    try:
        if Path(upload.file_name or "").suffix.lower() == ".docx":
            finding_count, by_author = recount_report_findings(processed)
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
        by_author,
    )
    return processed


def _require_processing_mode(macro) -> str:
    mode = (getattr(macro, "processing_mode", None) or ReportMacro.ProcessingMode.CHUNKS).strip()
    if mode not in PROCESSING_HANDLERS:
        label = (macro.skill_name or macro.name or "").strip() or "навык"
        raise ReportSkillRunError(
            f"Навык «{label}» задаёт неизвестный режим обработки «{mode}»."
        )
    return mode


def _run_chunk_mode(upload, file_bytes: bytes, lines: list, *, skip_clear_rule_ids=()) -> bytes:
    return run_chunked_skill_lines(
        upload,
        file_bytes,
        lines,
        skip_clear_rule_ids=skip_clear_rule_ids,
    )


def _run_agent_mode(
    upload,
    file_bytes: bytes,
    line,
    *,
    run_root: Path,
    index: int,
    input_name: str,
    extension: str,
    skip_clear_rule_ids=(),
) -> bytes:
    macro = line.macro
    skill_name = (macro.skill_name or "").strip()
    if not store_report_macro_progress(upload, 0, 0, macro.display_label or "Навык"):
        raise ReportCheckAborted()
    _sync_local_bundled_skill(skill_name)
    rule_root = run_root / f"{index:02d}-{line.pk or 'line'}"
    input_dir = rule_root / "input"
    output_dir = rule_root / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=False)
    input_bytes = file_bytes
    if (
        line.rule.clear_comments
        and line.rule_id not in set(skip_clear_rule_ids or ())
        and extension == ".docx"
    ):
        input_bytes = strip_comments(file_bytes)
    (input_dir / input_name).write_bytes(input_bytes)
    profile = _prepare_model_runtime(
        rule_root,
        macro.model_id,
        macro.reasoning_effort,
        False,
        macro.temperature,
        max_tokens=AGENT_OUTPUT_TOKENS,
    )
    run_headless(
        _skill_prompt(skill_name, macro.model_id, input_name),
        cwd=rule_root,
        profile=profile,
        timeout=AGENT_TIMEOUT_SECONDS,
        heartbeat=lambda: touch_report_check_heartbeat(upload),
    )
    result_path = _result_file(output_dir, input_name, extension)
    try:
        current_bytes = result_path.read_bytes()
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось прочитать результат навыка «{skill_name}»: {exc}"
        ) from exc
    if not current_bytes:
        raise ReportSkillRunError(
            f"Навык «{skill_name}» вернул пустой файл."
        )
    return current_bytes


PROCESSING_HANDLERS = {
    ReportMacro.ProcessingMode.CHUNKS: _run_chunk_mode,
    ReportMacro.ProcessingMode.AGENT: _run_agent_mode,
}


def run_report_skill_rules(
    upload: PerformerReportUpload,
    file_bytes: bytes,
    rules: list[ReportCheckRule] | None = None,
    *,
    skip_clear_rule_ids=(),
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
    lines = skill_lines_for_rules(rules)
    try:
        pending_chunk_lines = []
        for index, line in enumerate(lines, start=1):
            mode = _require_processing_mode(line.macro)
            if mode == ReportMacro.ProcessingMode.CHUNKS:
                pending_chunk_lines.append(line)
                continue
            if pending_chunk_lines:
                current_bytes = PROCESSING_HANDLERS[ReportMacro.ProcessingMode.CHUNKS](
                    upload,
                    current_bytes,
                    pending_chunk_lines,
                    skip_clear_rule_ids=skip_clear_rule_ids,
                )
                pending_chunk_lines = []
            current_bytes = PROCESSING_HANDLERS[mode](
                upload,
                current_bytes,
                line,
                run_root=run_root,
                index=index,
                input_name=input_name,
                extension=extension,
                skip_clear_rule_ids=skip_clear_rule_ids,
            )
        if pending_chunk_lines:
            current_bytes = PROCESSING_HANDLERS[ReportMacro.ProcessingMode.CHUNKS](
                upload,
                current_bytes,
                pending_chunk_lines,
                skip_clear_rule_ids=skip_clear_rule_ids,
            )
        return current_bytes
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось подготовить рабочий каталог DSH: {exc}"
        ) from exc
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


def _prepare_model_runtime(
    rule_root: Path,
    model_id: str,
    reasoning_effort: str = "off",
    disable_tools: bool = False,
    temperature: str = "",
    max_tokens: int | None = None,
) -> str | None:
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
    _apply_reasoning_effort(provider, selected_model, reasoning_effort)
    if max_tokens:
        for model in provider.get("models") or []:
            if (
                isinstance(model, dict)
                and str(model.get("id") or "").strip() == selected_model
            ):
                current = int(model.get("maxTokens") or 0)
                model["maxTokens"] = max(current, int(max_tokens))
                break
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
        _write_temperature_file(rule_root, temperature)
        _ensure_report_check_profile(host_home, disable_tools=disable_tools)
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не удалось подготовить модель DSH «{selected_model}»: {exc}"
        ) from exc
    if disable_tools:
        return REPORT_CHECK_TEXT_PROFILE
    return REPORT_CHECK_DSH_PROFILE


def _apply_reasoning_effort(provider: dict, model_id: str, reasoning_effort: str) -> None:
    """Pin the report-check request to the skill row's reasoning level.

    Qwen-compatible APIs think unless enable_thinking is false. DSH sends that
    flag only after the model declares a reasoning control, so a model without
    one is given an off/low map. Off omits the effort and disables thinking.
    Any other level is sent as that effort.
    """
    effort = (reasoning_effort or "off").strip() or "off"
    for model in provider.get("models") or []:
        if not isinstance(model, dict) or str(model.get("id") or "").strip() != model_id:
            continue
        efforts = model.get("reasoningEfforts", None)
        if efforts is False:
            if effort != "off":
                raise ReportSkillRunError(
                    f"Модель «{model_id}» не поддерживает уровень рассуждений «{effort}»."
                )
            return
        if not isinstance(efforts, dict):
            efforts = {}
        else:
            efforts = dict(efforts)
        efforts.setdefault("off", None)
        if effort != "off" and not efforts.get(effort):
            from core.dsh_catalog import catalog_reasoning_levels

            catalog = catalog_reasoning_levels(model_id) or ()
            wire = next((value for level, value in catalog if level == effort), "")
            efforts[effort] = wire or effort
        if not any(level != "off" for level in efforts):
            efforts["low"] = "low"
        model["reasoningEfforts"] = efforts
        provider["reasoning"] = effort
        if effort != "off" and efforts.get(effort):
            compat = provider.setdefault("compat", {})
            if isinstance(compat, dict):
                compat["supportsReasoningEffort"] = True
        return


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


def _temperature_number(raw: str) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    allowed = {code for code, _label in ReportMacro.TEMPERATURE_CHOICES if code}
    if value not in allowed:
        raise ReportSkillRunError(f"Некорректная температура «{value}».")
    return float(value)


def _write_temperature_file(rule_root: Path, temperature: str) -> None:
    path = rule_root / REPORT_CHECK_TEMPERATURE_FILE
    number = _temperature_number(temperature)
    if number is None:
        path.unlink(missing_ok=True)
        return
    _write_runtime_file(
        path,
        json.dumps({"temperature": number}, ensure_ascii=False) + "\n",
    )


def _ensure_report_check_profile(host_home: Path, disable_tools: bool = False) -> None:
    profile_name = REPORT_CHECK_TEXT_PROFILE if disable_tools else REPORT_CHECK_DSH_PROFILE
    profile_dir = host_home / "profiles" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    package = {
        "name": f"dsh-profile-{profile_name}",
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
    if disable_tools:
        patch += (
            "- id: system-prompt\n"
            "  config:\n"
            "    personaPrefix: >-\n"
            "      Ты отвечаешь только текстом на сообщение пользователя. Инструментов нет.\n"
            "    personaSuffix: \"\"\n"
        )
        patch += "".join(
            f"- id: {plugin_id}\n  disabled: true\n"
            for plugin_id in _TEXT_ONLY_TOOL_PLUGINS
        )
    patch += (
        "- insert:\n"
        "    - name: ./report-check-temperature.mjs\n"
        "    - name: ./report-check-continue.mjs\n"
    )
    _install_profile_plugin(
        profile_dir,
        "report-check-temperature/index.js",
        "report-check-temperature.mjs",
    )
    _install_profile_plugin(
        profile_dir,
        "report-check-continue/index.mjs",
        "report-check-continue.mjs",
    )
    _write_runtime_file(
        profile_dir / "package.json",
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
    )
    _write_runtime_file(profile_dir / "cordis.patch.yml", patch)


def _install_profile_plugin(profile_dir: Path, source_name: str, dest_name: str) -> None:
    source = Path(settings.BASE_DIR) / "deploy" / "dsh" / "plugins" / source_name
    try:
        plugin_text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReportSkillRunError(
            f"Не найден плагин проверки отчёта «{dest_name}»."
        ) from exc
    _write_runtime_file(profile_dir / dest_name, plugin_text)


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


def _skill_prompt(skill_name: str, model_id: str, input_name: str) -> str:
    model_note = (
        f"\nНастроенная для правила модель DSH: {model_id}."
        if (model_id or "").strip()
        else ""
    )
    return (
        f"/{skill_name}\n\n"
        "Обработай ровно один исходный файл этой проверки.\n"
        f"Вход: input/{input_name}\n"
        f"Результат обязательно запиши последним шагом: output/{input_name}\n"
        "До этого output пуст. Черновик держи отдельно, например в work/. "
        "Проверь текст по частям, дождись находок всех подагентов и запиши "
        "примечания в черновик. Не завершай ответ, пока подагенты ещё работают "
        "и пока готовый файл не лежит в output. "
        "Фраза «соберу результаты позже» не является результатом.\n"
        "Не устанавливай пакеты, не читай settings.yaml, не распаковывай DOCX "
        "и не пиши собственный анализатор. "
        "При вставке примечаний не обрезай пробелы и не копируй w:tab: "
        "лишняя табуляция и потерянные пробелы недопустимы. "
        "Примечания записывай скриптом навыка docx_comments.py annotate. "
        "Сохраняй объявления xmlns, включая вложенные xmlns:a и xmlns:pic, "
        "и части commentsExtended, commentsIds, commentsExtensible: "
        "без них Word не открывает файл. "
        "Результатом должен быть обработанный файл, а не JSON или текст ответа. "
        "Не меняй расширение файла."
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
