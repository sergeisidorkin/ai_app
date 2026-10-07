from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path

import yaml
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.dsh_run import DshRunError, run_headless

from .docx_comments import insert_comments, strip_comments
from .models import (
    ReportCheckChunk,
    ReportCheckFinding,
    ReportCheckRun,
    ReportModelThrottle,
)
from .report_document_pipeline import (
    build_document_snapshot,
    chunk_document,
    validate_chunk_finding,
)

log = logging.getLogger(__name__)
LOCAL_CHUNKS = "local_chunks"
SUPPORTED_EXECUTION_MODES = {
    LOCAL_CHUNKS,
    "whole_document",
    "hierarchical_map_reduce",
    "claim_index_compare",
}
IMPLEMENTED_EXECUTION_MODES = {LOCAL_CHUNKS}


class ChunkSkillError(RuntimeError):
    pass


class EmptyChunkObject(ChunkSkillError):
    """Модель вернула пустой объект {} вместо объекта с массивом findings."""


_SKILL_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def _skill_directory_name(skill_name: str) -> str:
    name = str(skill_name or "").strip()
    if not name or name != Path(name).name or "/" in name or "\\" in name:
        raise ChunkSkillError("Некорректное имя навыка DSH.")
    return name


def _bundled_skill_dir(skill_name: str) -> Path:
    return (
        Path(settings.BASE_DIR)
        / "deploy"
        / "dsh"
        / "skills"
        / _skill_directory_name(skill_name)
    )


def resolve_skill_markdown(skill_name: str) -> Path:
    """SKILL.md, который видит интерфейс DSH, иначе копия в репозитории.

    На сервере интерфейс пишет в каталог навыков рядом с compose-стеком
    (`/opt/dsh/skills`). Локально правка в интерфейсе при проверке заменяется
    файлом из репозитория, поэтому здесь читается репозиторная копия.
    """
    name = _skill_directory_name(skill_name)
    compose = (getattr(settings, "DSH_COMPOSE_DIR", "") or "").strip()
    if compose:
        live = Path(compose).expanduser() / "skills" / name / "SKILL.md"
        if live.is_file():
            return live
    return _bundled_skill_dir(name) / "SKILL.md"


def load_skill_instructions(skill_name: str) -> str:
    """Тело SKILL.md после фронтматтера — тот же текст, который DSH вставляет в сессию.

    Читает файл процесс приложения. Модели для этого не нужен инструмент.
    """
    path = resolve_skill_markdown(skill_name)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ChunkSkillError(f"Не найден контракт навыка «{skill_name}».") from exc
    body = _SKILL_FRONTMATTER_RE.sub("", raw, count=1).strip()
    if not body:
        raise ChunkSkillError(f"Контракт навыка «{skill_name}» пуст.")
    return body


def load_skill_manifest(skill_name: str) -> dict | None:
    path = (
        Path(settings.BASE_DIR)
        / "deploy"
        / "dsh"
        / "skills"
        / str(skill_name or "").strip()
        / "pipeline.yaml"
    )
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ChunkSkillError(f"Некорректный pipeline.yaml навыка «{skill_name}»: {exc}") from exc
    if not isinstance(raw, dict):
        raise ChunkSkillError(f"pipeline.yaml навыка «{skill_name}» должен быть объектом.")
    raw.pop("categories", None)
    markdown_path = resolve_skill_markdown(skill_name)
    if markdown_path.is_file():
        categories = parse_skill_categories(markdown_path.read_text(encoding="utf-8"))
        if categories is not None:
            raw["categories"] = categories
    mode = str(raw.get("execution_mode") or "").strip()
    if mode not in SUPPORTED_EXECUTION_MODES:
        raise ChunkSkillError(f"Навык «{skill_name}» задаёт неизвестный режим «{mode}».")
    if mode not in IMPLEMENTED_EXECUTION_MODES:
        raise ChunkSkillError(
            f"Режим «{mode}» навыка «{skill_name}» пока не реализован."
        )
    return raw


def is_chunk_skill(skill_name: str) -> bool:
    return load_skill_manifest(skill_name) is not None


def run_chunked_skill_lines(upload, file_bytes: bytes, lines: list, *, skip_clear_rule_ids=()) -> bytes:
    from .report_macro_runner import (
        ReportCheckAborted,
        store_report_macro_progress,
        touch_report_check_heartbeat,
    )
    from .report_skill_runner import (
        _prepare_model_runtime,
        _sync_local_bundled_skill,
    )

    if not lines:
        return file_bytes
    manifests = []
    for line in lines:
        manifest = load_skill_manifest(line.macro.skill_name)
        if manifest is None:
            raise ChunkSkillError(
                f"Навык «{line.macro.skill_name}» не поддерживает chunk-контракт."
            )
        manifests.append(manifest)

    skipped_clear_rules = set(skip_clear_rule_ids or ())
    clear_comments = any(
        bool(line.rule.clear_comments) and line.rule_id not in skipped_clear_rules
        for line in lines
    )
    base_bytes = strip_comments(file_bytes) if clear_comments else file_bytes
    source_sha256 = hashlib.sha256(base_bytes).hexdigest()
    config_payload = [
        line_config_entry(line, manifest)
        for line, manifest in zip(lines, manifests)
    ]
    config_sha256 = hashlib.sha256(
        json.dumps(config_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    run = _resume_or_create_run(
        upload,
        source_sha256,
        config_sha256,
        clear_comments,
    )
    run.status = ReportCheckRun.Status.EXTRACTING
    run.strategy = LOCAL_CHUNKS
    run.error = ""
    run.save(update_fields=["status", "strategy", "error", "updated_at"])
    snapshot = build_document_snapshot(base_bytes)

    all_jobs = []
    for line, manifest in zip(lines, manifests):
        chunks = chunk_document(
            snapshot,
            max_core_chars=int(manifest.get("max_core_chars") or 12_000),
            overlap_chars=int(manifest.get("overlap_chars") or 1_500),
        )
        all_jobs.extend((line, manifest, chunk) for chunk in chunks)
    total = len(all_jobs)
    run.status = ReportCheckRun.Status.RUNNING
    run.save(update_fields=["status", "updated_at"])

    accepted: list[tuple[ReportCheckFinding, dict]] = []
    try:
        for job_index, (line, manifest, chunk) in enumerate(all_jobs, start=1):
            label = f"{line.macro.display_label}: фрагмент {job_index}/{total}"
            if not store_report_macro_progress(upload, job_index, total, label):
                raise ReportCheckAborted()
            payload = chunk.as_payload(snapshot.source_sha256)
            payload["skill"] = {
                "name": line.macro.skill_name,
                "version": str(manifest.get("version") or "1"),
                "allowed_rule_ids": list(manifest.get("allowed_rule_ids") or []),
                "comment_requirements": manifest.get("comment_requirements") or {},
            }
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            payload_sha = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            task, _created = ReportCheckChunk.objects.get_or_create(
                run=run,
                line=line,
                chunk_id=chunk.chunk_id,
                defaults={
                    "skill_name": line.macro.skill_name,
                    "skill_version": str(manifest.get("version") or "1"),
                    "model_id": line.macro.model_id,
                    "ordinal": job_index,
                    "total": total,
                    "payload_sha256": payload_sha,
                    "payload": payload,
                },
            )
            if task.payload_sha256 != payload_sha:
                task.findings.all().delete()
                task.payload_sha256 = payload_sha
                task.payload = payload
                task.skill_name = line.macro.skill_name
                task.skill_version = str(manifest.get("version") or "1")
                task.model_id = line.macro.model_id
                task.ordinal = job_index
                task.total = total
                task.response = {}
                task.status = ReportCheckChunk.Status.PENDING
                task.attempts = 0
                task.error = ""
                task.save()
            if task.status != ReportCheckChunk.Status.DONE:
                _execute_chunk(
                    upload,
                    task,
                    line.macro.skill_name,
                    line.macro.model_id,
                    line.macro.reasoning_effort,
                    bool(line.macro.disable_tools),
                    line.macro.temperature,
                    manifest,
                    _prepare_model_runtime,
                    _sync_local_bundled_skill,
                    touch_report_check_heartbeat,
                )
            accepted.extend(
                _validate_and_store_findings(
                    task,
                    snapshot,
                    chunk,
                    manifest,
                    line.macro.display_label,
                )
            )
        run.status = ReportCheckRun.Status.VALIDATING
        run.save(update_fields=["status", "updated_at"])
        accepted = _apply_category_validation(
            upload,
            accepted,
            _prepare_model_runtime,
            touch_report_check_heartbeat,
        )
        rendered = _consolidate_findings(accepted)
        run.status = ReportCheckRun.Status.RENDERING
        run.save(update_fields=["status", "updated_at"])
        unplaced: list[str] = []
        result = insert_comments(
            base_bytes,
            [item for _finding, item in rendered],
            unplaced=unplaced,
            progress=lambda: touch_report_check_heartbeat(upload),
        )
        if rendered and result == base_bytes:
            if touch_report_check_heartbeat(upload) is False:
                raise ReportCheckAborted()
            raise ChunkSkillError("Не удалось вставить принятые замечания в DOCX.")
        if unplaced:
            raise ChunkSkillError("\n".join(unplaced))
        if touch_report_check_heartbeat(upload) is False:
            raise ReportCheckAborted()
        placed_ids = [finding.pk for finding, _item in rendered]
        ReportCheckFinding.objects.filter(pk__in=placed_ids).update(
            status=ReportCheckFinding.Status.PLACED
        )
        run.status = ReportCheckRun.Status.DONE
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
        return result
    except ReportCheckAborted:
        raise
    except Exception as exc:
        run.status = ReportCheckRun.Status.ERROR
        run.error = str(exc)
        run.save(update_fields=["status", "error", "updated_at"])
        raise


def line_config_entry(line, manifest) -> dict:
    return {
        "line_id": line.pk,
        "skill": line.macro.skill_name,
        "model": line.macro.model_id,
        "reasoning": line.macro.reasoning_effort,
        "disable_tools": bool(line.macro.disable_tools),
        "processing_mode": line.macro.processing_mode,
        "temperature": line.macro.temperature,
        "validation_model": getattr(line.macro, "validation_model_id", "") or "",
        "validation_reasoning": getattr(line.macro, "validation_reasoning_effort", "") or "",
        "validation_temperature": getattr(line.macro, "validation_temperature", "") or "",
        "manifest": manifest,
    }


def _resume_or_create_run(
    upload,
    source_sha256: str,
    config_sha256: str,
    clear_comments: bool,
) -> ReportCheckRun:
    run = (
        ReportCheckRun.objects.filter(
            upload=upload,
            source_sha256=source_sha256,
            config_sha256=config_sha256,
        )
        .exclude(status=ReportCheckRun.Status.DONE)
        .order_by("-created_at", "-id")
        .first()
    )
    if run is not None:
        if run.status == ReportCheckRun.Status.ERROR:
            run.chunks.filter(status=ReportCheckChunk.Status.ERROR).update(
                status=ReportCheckChunk.Status.PENDING,
                attempts=0,
                retry_at=None,
                error="",
                started_at=None,
                finished_at=None,
            )
        return run
    return ReportCheckRun.objects.create(
        upload=upload,
        source_sha256=source_sha256,
        config_sha256=config_sha256,
        clear_comments=clear_comments,
        status=ReportCheckRun.Status.QUEUED,
    )


def _execute_chunk(
    upload,
    task: ReportCheckChunk,
    skill_name: str,
    model_id: str,
    reasoning_effort: str,
    disable_tools: bool,
    temperature: str,
    manifest: dict,
    prepare_profile,
    sync_skill,
    heartbeat,
) -> None:
    from .report_macro_runner import ReportCheckAborted

    workspace_value = str(getattr(settings, "DSH_SORT_WORKSPACE", "") or "").strip()
    if not workspace_value:
        raise ChunkSkillError("Не задан DSH_SORT_WORKSPACE для проверки отчётов.")
    task_root = (
        Path(workspace_value).expanduser()
        / "report-checks"
        / "chunks"
        / f"run-{task.run_id}"
        / f"task-{task.pk}"
    )
    max_attempts = max(int(manifest.get("max_attempts") or 3), 1)
    retry_delays = list(manifest.get("retry_delays_seconds") or [30, 60, 120])
    if task.retry_at and task.retry_at > timezone.now():
        _heartbeat_sleep(
            int((task.retry_at - timezone.now()).total_seconds()) + 1,
            lambda: heartbeat(upload),
        )
    last_exc: Exception | None = None
    for attempt in range(task.attempts + 1, max_attempts + 1):
        if not heartbeat(upload):
            raise ReportCheckAborted()
        shutil.rmtree(task_root, ignore_errors=True)
        input_dir = task_root / "input"
        output_dir = task_root / "output"
        input_dir.mkdir(parents=True)
        output_dir.mkdir(parents=True)
        (input_dir / "chunk.json").write_text(
            json.dumps(task.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        sync_skill(skill_name)
        profile = prepare_profile(
            task_root,
            model_id,
            reasoning_effort,
            disable_tools,
            temperature,
        )
        task.status = ReportCheckChunk.Status.RUNNING
        task.attempts = attempt
        task.started_at = timezone.now()
        task.error = ""
        task.save(update_fields=["status", "attempts", "started_at", "error", "updated_at"])
        slot = _acquire_model_slot(model_id, heartbeat=lambda: heartbeat(upload))
        try:
            def request_heartbeat():
                alive = heartbeat(upload)
                if alive is not False:
                    _touch_model_slot(slot)
                return alive

            stdout = run_headless(
                _chunk_prompt(
                    skill_name,
                    model_id,
                    task.payload,
                    disable_tools=disable_tools,
                ),
                cwd=task_root,
                profile=profile,
                heartbeat=request_heartbeat,
            )
            if heartbeat(upload) is False:
                raise ReportCheckAborted()
            response = _read_chunk_response(
                output_dir / "findings.json",
                task.chunk_id,
                max_bytes=int(manifest.get("max_response_bytes") or 1_000_000),
                fallback_text=stdout,
            )
        except ReportCheckAborted:
            raise
        except Exception as exc:
            if heartbeat(upload) is False:
                raise ReportCheckAborted() from exc
            if isinstance(exc, EmptyChunkObject) and attempt >= 2:
                log.warning(
                    "Навык «%s», фрагмент %s: модель повторно вернула {}. "
                    "Считаем, что замечаний нет.",
                    skill_name,
                    task.ordinal,
                )
                response = {
                    "schema_version": 1,
                    "chunk_id": task.chunk_id,
                    "findings": [],
                }
            else:
                last_exc = exc
                transient = _is_transient_error(exc)
                if "429" in str(exc) or "rate_limit" in str(exc).casefold():
                    _release_model_slot(slot, cooldown_seconds=_retry_delay(retry_delays, attempt))
                    slot = None
                if not transient or attempt >= max_attempts:
                    task.status = ReportCheckChunk.Status.ERROR
                    task.error = str(exc)
                    task.finished_at = timezone.now()
                    task.save(update_fields=["status", "error", "finished_at", "updated_at"])
                    raise ChunkSkillError(
                        f"Навык «{skill_name}», фрагмент {task.ordinal}: {exc}"
                    ) from exc
                delay = _retry_delay(retry_delays, attempt)
                task.status = ReportCheckChunk.Status.RETRY
                task.error = str(exc)
                task.retry_at = timezone.now() + timedelta(seconds=delay)
                task.save(update_fields=["status", "error", "retry_at", "updated_at"])
                _heartbeat_sleep(delay, lambda: heartbeat(upload))
                continue
        finally:
            if slot is not None:
                _release_model_slot(slot)
        response = _expand_response_anchor_ids(response, task.payload)
        task.response = response
        task.status = ReportCheckChunk.Status.DONE
        task.error = ""
        task.retry_at = None
        task.finished_at = timezone.now()
        task.save(
            update_fields=[
                "response", "status", "error", "retry_at", "finished_at", "updated_at"
            ]
        )
        shutil.rmtree(task_root, ignore_errors=True)
        return
    raise ChunkSkillError(str(last_exc or "Не удалось обработать фрагмент."))


def _chunk_prompt(
    skill_name: str,
    model_id: str,
    payload: dict,
    *,
    disable_tools: bool = False,
) -> str:
    model_note = (
        f"\nНастроенная для правила модель DSH: {model_id}."
        if str(model_id or "").strip()
        else ""
    )
    # С выключенными инструментами плагин tool-skill не подставляет /имя навыка.
    # Контракт читает приложение и кладёт его в то же сообщение, что и фрагмент.
    contract = ""
    if disable_tools:
        instructions = load_skill_instructions(skill_name)
        contract = (
            "Контракт навыка уже находится в этом сообщении. "
            "Читать файлы и вызывать инструменты не нужно.\n\n"
            f"{instructions}\n\n"
        )
    compact, _anchor_map = _compact_chunk_payload(payload)
    return (
        f"/{skill_name}\n\n"
        f"{contract}"
        "Обработай ровно один фрагмент документа ниже. Не вызывай инструменты, "
        "не читай и не записывай файлы. Не открывай и не изменяй DOCX. "
        "Финальный ответ должен содержать только JSON-объект по контракту навыка, "
        "без Markdown. Если ошибок нет, верни пустой массив findings."
        f"{model_note}\n\nDOCUMENT_CHUNK:\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    )


def _compact_chunk_payload(payload: dict) -> tuple[dict, dict[str, str]]:
    by_anchor: dict[str, str] = {}
    anchor_map: dict[str, str] = {}
    blocks = []
    for item in payload.get("blocks") or []:
        full_id = str(item.get("anchor_id") or "")
        short_id = by_anchor.get(full_id)
        if short_id is None:
            short_id = f"a{len(by_anchor) + 1}"
            by_anchor[full_id] = short_id
            anchor_map[short_id] = full_id
        blocks.append({
            "id": short_id,
            "s": item.get("slice_start"),
            "c0": item.get("core_start"),
            "c1": item.get("core_end"),
            "t": item.get("text") or "",
        })
    return {
        "schema_version": 1,
        "chunk_id": payload.get("chunk_id"),
        "block_fields": {
            "id": "anchor_id",
            "s": "slice_start",
            "c0": "core_start",
            "c1": "core_end",
            "t": "text",
        },
        "blocks": blocks,
    }, anchor_map


def _first_finding_text(raw: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return ""


def _coerce_model_finding(raw: dict, anchor_map: dict[str, str]) -> dict:
    """Map a free-form model object onto the comment contract.

    Text-only answers often use block_ids, description and suggested_fix
    instead of anchor_id, explanation and replacement. Without this mapping
    every such finding is rejected and the document receives no comments.
    """
    finding = dict(raw)
    anchor = _first_finding_text(finding, ("anchor_id", "block_id"))
    if not anchor:
        anchor = _first_finding_text(finding, ("block_ids", "anchor_ids"))
    if anchor in anchor_map:
        anchor = anchor_map[anchor]
    if anchor:
        finding["anchor_id"] = anchor
    rule = _first_finding_text(finding, ("rule_id", "rule", "type", "category"))
    if rule:
        finding["rule_id"] = rule
    explanation = _first_finding_text(
        finding, ("explanation", "description", "message", "note")
    )
    if explanation:
        finding["explanation"] = explanation
    replacement = _first_finding_text(
        finding,
        ("replacement", "suggested_fix", "suggestion", "suggested_correction"),
    )
    if replacement:
        finding["replacement"] = replacement
    quote = _first_finding_text(finding, ("quote", "excerpt"))
    if quote:
        finding["quote"] = quote
    return finding


def _expand_response_anchor_ids(response: dict, payload: dict) -> dict:
    _compact, anchor_map = _compact_chunk_payload(payload)
    findings = response.get("findings") or []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        findings[index] = _coerce_model_finding(finding, anchor_map)
    return response


def _read_chunk_response(
    path: Path,
    chunk_id: str,
    *,
    max_bytes: int,
    fallback_text: str = "",
) -> dict:
    try:
        if path.is_file():
            if path.stat().st_size > max(max_bytes, 1):
                raise ChunkSkillError("output/findings.json превышает допустимый размер.")
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            if len(fallback_text.encode("utf-8")) > max(max_bytes, 1):
                raise ChunkSkillError("Ответ модели превышает допустимый размер.")
            raw = _json_object_from_text(fallback_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ChunkSkillError(f"Некорректный JSON результата навыка: {exc}") from exc
    if isinstance(raw, dict) and not raw:
        raise EmptyChunkObject("Модель вернула пустой JSON-объект.")
    if isinstance(raw, list):
        raw = {"schema_version": 1, "chunk_id": chunk_id, "findings": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("findings"), list):
        raise ChunkSkillError("findings.json должен содержать объект с массивом findings.")
    if str(raw.get("chunk_id") or chunk_id) != chunk_id:
        raise ChunkSkillError("Ответ модели относится к другому фрагменту.")
    return raw


def _findings_response(raw) -> dict | None:
    if isinstance(raw, dict) and isinstance(raw.get("findings"), list):
        return raw
    if isinstance(raw, list) and all(isinstance(item, dict) for item in raw):
        return {"findings": raw}
    return None


def _json_object_from_text(text: str) -> dict:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value).strip()
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        loaded = None
    if isinstance(loaded, dict) and not loaded:
        raise EmptyChunkObject("Модель вернула пустой JSON-объект.")
    parsed = _findings_response(loaded) if loaded is not None else None
    if parsed is not None:
        return parsed
    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char not in "{[":
            continue
        try:
            raw, _end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        parsed = _findings_response(raw)
        if parsed is not None:
            return parsed
    raise ChunkSkillError("Модель не вернула JSON-объект с массивом findings.")


def _validate_and_store_findings(
    task: ReportCheckChunk,
    snapshot,
    chunk,
    manifest: dict,
    author: str,
) -> list[tuple[ReportCheckFinding, dict]]:
    max_findings = max(int(manifest.get("max_findings_per_chunk") or 100), 1)
    max_quote = max(int(manifest.get("max_quote_chars") or 500), 1)
    max_message = max(int(manifest.get("max_comment_chars") or 2_000), 1)
    task.findings.all().delete()
    accepted = []
    for raw in list(task.response.get("findings") or [])[:max_findings]:
        if not isinstance(raw, dict):
            continue
        status = ReportCheckFinding.Status.ACCEPTED
        reason = ""
        normalized = None
        try:
            replacement = str(raw.get("replacement") or "")
            if len(replacement) > max_message:
                raw = dict(raw)
                raw["replacement"] = replacement[:max_message].rstrip()
            if len(str(raw.get("quote") or "")) > max_quote:
                raise ValueError("Цитата превышает допустимую длину.")
            if len(str(raw.get("explanation") or "")) > max_message:
                raise ValueError("Объяснение превышает допустимую длину.")
            normalized = validate_chunk_finding(snapshot, chunk, raw)
        except ValueError as exc:
            status = ReportCheckFinding.Status.REJECTED
            reason = str(exc)
        fingerprint = hashlib.sha256(
            json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        message = ""
        if normalized:
            message = normalized["explanation"]
            if normalized["replacement"]:
                message = (
                    f"{message} Корректный вариант: «{normalized['replacement']}»."
                )
        finding, created = ReportCheckFinding.objects.get_or_create(
            chunk=task,
            fingerprint=fingerprint,
            defaults={
                "status": status,
                "rule_id": str(raw.get("rule_id") or ""),
                "anchor_id": str(raw.get("anchor_id") or ""),
                "start": int(normalized["start"] if normalized else 0),
                "end": int(normalized["end"] if normalized else 0),
                "quote": str(raw.get("quote") or ""),
                "message": message,
                "replacement": str(raw.get("replacement") or ""),
                "reason": reason,
                "raw": raw,
            },
        )
        if normalized and created:
            accepted.append((finding, {
                "start": normalized["start"],
                "end": normalized["end"],
                "message": message,
                "author": author,
            }))
    return accepted


def _consolidate_findings(
    accepted: list[tuple[ReportCheckFinding, dict]],
) -> list[tuple[ReportCheckFinding, dict]]:
    ordered = sorted(accepted, key=lambda item: (item[1]["start"], item[1]["end"]))
    result = []
    seen = set()
    for finding, item in ordered:
        key = (item["start"], item["end"], item["message"], item["author"])
        if key in seen:
            finding.status = ReportCheckFinding.Status.SUPPRESSED
            finding.reason = "Дубликат замечания."
            finding.save(update_fields=["status", "reason"])
            continue
        seen.add(key)
        result.append((finding, item))
    return result


_CATEGORY_ITEM_RE = re.compile(
    r"^-\s+(?P<code>[A-Z]{4}-[A-Z]{2}-\d{2}\.\d{2})\s+"
    r"(?P<title>.+?)\s+[—–-]\s+"
    r"(?P<rule>[a-z][a-z0-9]*(?:-[a-z0-9]+)*)\s+[—–-]\s+"
    r"(?P<criteria>.+?)\s*$"
)
_CATEGORY_URL_RE = re.compile(r"^(?:ссылка:\s*)?(?P<url>https?://\S+)\s*$", re.IGNORECASE)
_SENTENCE_CAP = 1000


def parse_skill_categories(text: str) -> list[dict] | None:
    """Раздел «Категории» в SKILL.md. None, если раздела нет."""
    lines = str(text or "").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "## Категории"), None)
    if start is None:
        return None
    items = []
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("- "):
            match = _CATEGORY_ITEM_RE.match(stripped)
            if not match:
                if re.match(r"^-\s+[A-Z]{4}-[A-Z]{2}-\d{2}\.\d{2}\b", stripped):
                    raise ChunkSkillError(
                        "У категории нет привязки rule_id и фиксированного пояснения: "
                        f"{stripped}"
                    )
                raise ChunkSkillError(
                    f"Строка категории в SKILL.md не разобрана: {stripped}"
                )
            items.append({
                "code": match.group("code"),
                "title": match.group("title").strip(),
                "rule_id": match.group("rule"),
                "criteria": match.group("criteria").strip(),
                "course_link": None,
            })
            index += 1
            continue
        link = _CATEGORY_URL_RE.match(stripped)
        absent = stripped.casefold() in {"ссылка: нет", "нет"}
        if items and (link or absent) and (line.startswith("  ") or line.startswith("\t")):
            if link:
                items[-1]["course_link"] = {"url": link.group("url"), "text": ""}
            index += 1
            continue
        index += 1
    if not items:
        raise ChunkSkillError("В разделе «Категории» навыка нет ни одного кода.")
    return normalize_skill_categories(items)


def normalize_skill_categories(raw) -> list[dict]:
    """Код, название и ссылка на курс либо её отсутствие."""
    from .report_macro_code import TITLE_RE

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ChunkSkillError("Список категорий навыка должен быть списком.")
    seen = set()
    seen_rules = set()
    categories = []
    for item in raw:
        if not isinstance(item, dict):
            raise ChunkSkillError("Категория навыка должна быть объектом.")
        code = str(item.get("code") or "").strip()
        title = str(item.get("title") or "").strip()
        rule_id = str(item.get("rule_id") or "").strip()
        criteria = str(item.get("criteria") or "").strip()
        match = TITLE_RE.fullmatch(code)
        if not match or match.group(5):
            raise ChunkSkillError(f"Некорректный код категории «{code}».")
        if not title:
            raise ChunkSkillError(f"У категории {code} нет названия.")
        if not rule_id:
            raise ChunkSkillError(f"У категории {code} нет rule_id.")
        if not criteria:
            raise ChunkSkillError(f"У категории {code} нет фиксированного пояснения.")
        if code in seen:
            raise ChunkSkillError(f"Код категории {code} повторяется.")
        if rule_id in seen_rules:
            raise ChunkSkillError(f"rule_id {rule_id} назначен двум категориям.")
        seen.add(code)
        seen_rules.add(rule_id)
        link = item.get("course_link", None)
        if link is not None and not isinstance(link, dict):
            raise ChunkSkillError(
                f"Ссылка категории {code} должна быть объектом или пустой."
            )
        course_link = None
        if isinstance(link, dict):
            url = str(link.get("url") or "").strip()
            text = str(link.get("text") or "").strip() or "Ссылка на страницу курса"
            if url:
                course_link = {"text": text, "url": url}
        categories.append({
            "code": code,
            "title": _capitalize_leading(title),
            "rule_id": rule_id,
            "criteria": criteria,
            "course_link": course_link,
        })
    return categories


def _capitalize_leading(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return value[0].upper() + value[1:]


def _category_links(category: dict) -> list[dict]:
    link = category.get("course_link")
    if not isinstance(link, dict):
        return []
    url = str(link.get("url") or "").strip()
    if not url:
        return []
    text = str(link.get("text") or "").strip() or "Ссылка на страницу курса"
    return [{"text": text, "url": url}]


def _coded_comment(code: str, title: str, explanation: str, replacement: str) -> tuple[str, str]:
    author = f"{code} {_capitalize_leading(title)}"
    body = _capitalize_leading(explanation or title)
    message = body if body.startswith(f"{code}:") else f"{code}: {body}"
    if replacement and "Корректный вариант:" not in message:
        message = f"{message} Корректный вариант: «{replacement}»."
    return author, message


def _apply_category_validation(upload, accepted, prepare_profile, heartbeat):
    if not accepted:
        return accepted
    grouped: dict[int, list] = {}
    order: list[int] = []
    for pair in accepted:
        line = pair[0].chunk.line
        key = getattr(line, "pk", None)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(pair)
    validated = []
    for key in order:
        pairs = grouped[key]
        line = pairs[0][0].chunk.line
        validated.extend(
            _validate_line_findings(upload, line, pairs, prepare_profile, heartbeat)
        )
    return validated


def _validate_line_findings(upload, line, pairs, prepare_profile, heartbeat):
    from .report_macro_runner import ReportCheckAborted, store_report_macro_progress

    if line is None:
        return pairs
    macro = line.macro
    manifest = load_skill_manifest(macro.skill_name) or {}
    categories = list(manifest.get("categories") or [])
    model_id = str(getattr(macro, "validation_model_id", "") or "").strip()
    reasoning = str(getattr(macro, "validation_reasoning_effort", "") or "").strip()
    temperature = str(getattr(macro, "validation_temperature", "") or "").strip()
    if not categories or not model_id or not reasoning:
        return pairs
    label = f"{macro.display_label}: валидация"
    if not store_report_macro_progress(upload, 0, 0, label):
        raise ReportCheckAborted()
    by_rule = {category["rule_id"]: category for category in categories}
    numbered = []
    for index, pair in enumerate(pairs, start=1):
        finding = pair[0]
        category = by_rule.get(str(finding.rule_id or "").strip())
        if category is None:
            _reject_validated_finding(
                finding,
                "Для rule_id нет фиксированной категории.",
            )
            continue
        numbered.append((f"f{index}", pair, category))
    if not numbered:
        return []
    max_attempts = max(int(manifest.get("max_attempts") or 3), 1)
    retry_delays = list(manifest.get("retry_delays_seconds") or [30, 60, 120])
    payload = None
    for attempt in range(1, max_attempts + 1):
        if heartbeat(upload) is False:
            raise ReportCheckAborted()
        try:
            payload = _run_validation_request(
                upload,
                macro.skill_name,
                model_id,
                reasoning,
                temperature,
                categories,
                numbered,
                prepare_profile,
                heartbeat,
                attempt=attempt,
                retry_delays=retry_delays,
            )
            break
        except ReportCheckAborted:
            raise
        except Exception as exc:
            if heartbeat(upload) is False:
                raise ReportCheckAborted() from exc
            if not _is_validation_retryable(exc) or attempt >= max_attempts:
                log.exception(
                    "Валидация навыка «%s» не выполнена, замечания остаются без кода категории.",
                    macro.skill_name,
                )
                return [pair for _finding_id, pair, _category in numbered]
            delay = _retry_delay(retry_delays, attempt)
            log.warning(
                "Валидация навыка «%s», попытка %s не удалась, повтор через %s с: %s",
                macro.skill_name,
                attempt,
                delay,
                exc,
            )
            _heartbeat_sleep(delay, lambda: heartbeat(upload))
    by_id = {}
    for item in payload:
        if isinstance(item, dict):
            by_id[str(item.get("id") or "").strip()] = item
    by_code = {category["code"]: category for category in categories}
    kept = []
    for finding_id, (finding, comment), category in numbered:
        verdict = by_id.get(finding_id) or {}
        correct = verdict.get("correct")
        if correct is False or correct in (0, "false", "no", ""):
            _reject_validated_finding(finding, "Валидация не подтвердила замечание.")
            continue
        if str(correct).casefold() not in {"true", "1", "yes"} and correct is not True:
            _reject_validated_finding(finding, "Валидация не подтвердила замечание.")
            continue
        chosen = by_code.get(str(verdict.get("code") or "").strip()) or category
        author, message = _coded_comment(
            chosen["code"],
            chosen["title"],
            chosen["criteria"],
            finding.replacement,
        )
        links = _category_links(chosen)
        finding.rule_id = chosen["code"]
        finding.message = message
        finding.reason = ""
        finding.save(update_fields=["rule_id", "message", "reason"])
        comment["author"] = author
        comment["message"] = message
        if links:
            comment["links"] = links
        else:
            comment.pop("links", None)
        kept.append((finding, comment))
    return kept


def _reject_validated_finding(finding: ReportCheckFinding, reason: str) -> None:
    finding.status = ReportCheckFinding.Status.REJECTED
    finding.reason = reason
    finding.save(update_fields=["status", "reason"])


def _run_validation_request(
    upload,
    skill_name: str,
    model_id: str,
    reasoning: str,
    temperature: str,
    categories: list[dict],
    numbered,
    prepare_profile,
    heartbeat,
    attempt: int = 1,
    retry_delays=None,
) -> list:
    workspace_value = str(getattr(settings, "DSH_SORT_WORKSPACE", "") or "").strip()
    if not workspace_value:
        raise ChunkSkillError("Не задан DSH_SORT_WORKSPACE для проверки отчётов.")
    from .report_macro_runner import ReportCheckAborted

    task_root = (
        Path(workspace_value).expanduser()
        / "report-checks"
        / "validation"
        / f"upload-{getattr(upload, 'pk', 'new')}-{uuid.uuid4().hex}"
    )
    task_root.mkdir(parents=True, exist_ok=True)
    slot = None
    try:
        profile = prepare_profile(
            task_root,
            model_id,
            reasoning,
            True,
            temperature,
        )
        slot = _acquire_model_slot(model_id, heartbeat=lambda: heartbeat(upload))

        def request_heartbeat():
            alive = heartbeat(upload)
            if alive is not False:
                _touch_model_slot(slot)
            return alive

        try:
            stdout = run_headless(
                _validation_prompt(skill_name, categories, numbered),
                cwd=task_root,
                profile=profile,
                heartbeat=request_heartbeat,
            )
            return _validation_results(stdout)
        except ReportCheckAborted:
            raise
        except Exception as exc:
            if "429" in str(exc) or "rate_limit" in str(exc).casefold():
                _release_model_slot(
                    slot,
                    cooldown_seconds=_retry_delay(list(retry_delays or [30, 60, 120]), attempt),
                )
                slot = None
            raise
    finally:
        if slot is not None:
            _release_model_slot(slot)
        shutil.rmtree(task_root, ignore_errors=True)


def _is_soft_dot(text: str, index: int) -> bool:
    if text[index] != ".":
        return False
    if (
        index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    ):
        return True
    previous = index - 1
    if previous >= 0 and text[previous].isalpha():
        before = previous - 1
        if before < 0 or not text[before].isalpha():
            return True
    return False


def sentence_around_quote(text: str, start: int, end: int) -> str:
    """Предложение, в которое входит цитата. Граница — .!?… или перевод строки."""
    source = str(text or "")
    left = max(0, min(start, len(source)))
    right = max(left, min(end, len(source)))
    while left > 0:
        prev = source[left - 1]
        if prev in "\n\r":
            break
        if prev in ".!?…" and not _is_soft_dot(source, left - 1):
            break
        left -= 1
    cursor = right
    while cursor < len(source):
        char = source[cursor]
        cursor += 1
        if char in "\n\r":
            cursor -= 1
            break
        if char in ".!?…" and not _is_soft_dot(source, cursor - 1):
            break
    sentence = source[left:cursor].strip()
    if len(sentence) <= _SENTENCE_CAP:
        return sentence
    focus = max(0, min(start, len(source)) - left)
    window_start = max(0, focus - _SENTENCE_CAP // 2)
    window_end = min(len(sentence), window_start + _SENTENCE_CAP)
    return sentence[window_start:window_end].strip()


def quote_context(finding) -> str:
    """Предложение блока, в котором лежит цитата замечания."""
    quote = str(finding.quote or "")
    payload = getattr(finding.chunk, "payload", None) or {}
    anchor_id = str(finding.anchor_id or "")
    blocks = [
        block
        for block in payload.get("blocks") or []
        if not anchor_id or str(block.get("anchor_id") or "") == anchor_id
    ] or list(payload.get("blocks") or [])
    raw = finding.raw if isinstance(finding.raw, dict) else {}
    try:
        raw_start = int(raw.get("start"))
    except (TypeError, ValueError):
        raw_start = None
    for block in blocks:
        text = str(block.get("text") or "")
        if not text or not quote:
            continue
        try:
            slice_start = int(block.get("slice_start") or 0)
        except (TypeError, ValueError):
            slice_start = 0
        local = None
        if raw_start is not None:
            candidate = raw_start - slice_start
            if candidate >= 0 and text[candidate:candidate + len(quote)] == quote:
                local = candidate
        if local is None:
            found = text.find(quote)
            if found < 0:
                continue
            local = found
        return sentence_around_quote(text, local, local + len(quote))
    return quote


def _validation_prompt(skill_name: str, categories: list[dict], numbered) -> str:
    catalog = [
        {
            "code": category["code"],
            "rule_id": category["rule_id"],
            "title": category["title"],
            "explanation": category["criteria"],
        }
        for category in categories
    ]
    findings = []
    for finding_id, (finding, _comment), category in numbered:
        raw = finding.raw if isinstance(finding.raw, dict) else {}
        claim = str(raw.get("explanation") or "").strip()
        findings.append({
            "id": finding_id,
            "rule_id": category["rule_id"],
            "code": category["code"],
            "quote": finding.quote,
            "context": quote_context(finding),
            "explanation": claim,
            "replacement": finding.replacement,
        })
    return (
        "Проверь уже найденные замечания навыка "
        f"«{skill_name}». Новые ошибки не ищи и цитаты не меняй. "
        "Пояснение не пиши: приложение подставит фиксированный текст выбранной категории. "
        "Если по предложению context замечание неверно, верни correct=false и пустой code. "
        "Если замечание верно, верни correct=true и code категории из CATEGORIES, к которой оно относится. "
        "Назначенный code можно заменить другим code из CATEGORIES. "
        "Финальный ответ — только JSON-объект с массивом results, без Markdown.\n\n"
        "CATEGORIES:\n"
        + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
        + "\n\nFINDINGS:\n"
        + json.dumps(findings, ensure_ascii=False, separators=(",", ":"))
        + '\n\nПример: {"results":[{"id":"f1","correct":true,"code":"XXXX-YY-00.00"},{"id":"f2","correct":false,"code":""}]}'
    )


def _validation_results(text: str) -> list:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value).strip()
    candidates = []
    try:
        candidates.append(json.loads(value))
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            raw, _end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(raw)
    for raw in candidates:
        if isinstance(raw, dict) and isinstance(raw.get("results"), list):
            return raw["results"]
    raise ChunkSkillError("Модель валидации не вернула JSON-объект с массивом results.")


def _is_validation_retryable(exc: Exception) -> bool:
    if isinstance(exc, (DshRunError, TimeoutError)):
        return True
    if isinstance(exc, ChunkSkillError) and not isinstance(exc, EmptyChunkObject):
        text = str(exc).casefold()
        return "не задан" not in text
    return False


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, EmptyChunkObject):
        return True
    text = str(exc).casefold()
    if isinstance(exc, ChunkSkillError) and (
        "findings.json" in text
        or "массивом findings" in text
        or "некорректный json" in text
    ):
        return True
    return isinstance(exc, (DshRunError, TimeoutError)) and any(
        marker in text
        for marker in (
            "429",
            "rate_limit",
            "timeout",
            "timed out",
            "не ответил",
            "server",
            "transport",
            "stream ended",
            "пустой ответ",
        )
    )


def _retry_delay(delays: list, attempt: int) -> int:
    if not delays:
        return 30
    try:
        return max(int(delays[min(attempt - 1, len(delays) - 1)]), 1)
    except (TypeError, ValueError):
        return 30


def _heartbeat_sleep(seconds: int, heartbeat) -> None:
    remaining = max(int(seconds), 0)
    while remaining:
        step = min(remaining, 5)
        time.sleep(step)
        remaining -= step
        if heartbeat() is False:
            from .report_macro_runner import ReportCheckAborted
            raise ReportCheckAborted()


def _acquire_model_slot(model_id: str, heartbeat):
    route_key = str(model_id or "default")
    token = uuid.uuid4().hex
    wait_limit = max(int(getattr(settings, "REPORT_MODEL_SLOT_WAIT", 1800) or 1800), 30)
    deadline = time.monotonic() + wait_limit
    while time.monotonic() < deadline:
        now = timezone.now()
        wait_seconds = 5
        with transaction.atomic():
            throttle, _created = ReportModelThrottle.objects.select_for_update().get_or_create(
                route_key=route_key
            )
            min_interval = max(
                float(getattr(settings, "REPORT_MODEL_MIN_INTERVAL", 2) or 0),
                0.0,
            )
            interval_until = (
                throttle.last_started_at + timedelta(seconds=min_interval)
                if throttle.last_started_at is not None and min_interval
                else None
            )
            blocked_until = max(
                [
                    value
                    for value in (
                        throttle.active_until,
                        throttle.cooldown_until,
                        interval_until,
                    )
                    if value is not None
                ],
                default=None,
            )
            if not blocked_until or blocked_until <= now:
                throttle.active_token = token
                throttle.active_until = now + timedelta(
                    seconds=90
                )
                throttle.last_started_at = now
                throttle.save()
                return route_key, token
            wait_seconds = max(
                min(int((blocked_until - now).total_seconds()) + 1, 5),
                1,
            )
        _heartbeat_sleep(wait_seconds, heartbeat)
    raise ChunkSkillError(f"Истекло ожидание свободного слота модели «{route_key}».")


def _touch_model_slot(slot) -> None:
    route_key, token = slot
    ReportModelThrottle.objects.filter(
        route_key=route_key,
        active_token=token,
    ).update(active_until=timezone.now() + timedelta(seconds=90))


def _release_model_slot(slot, *, cooldown_seconds: int = 0) -> None:
    route_key, token = slot
    with transaction.atomic():
        throttle = (
            ReportModelThrottle.objects.select_for_update()
            .filter(route_key=route_key)
            .first()
        )
        if throttle is None or throttle.active_token != token:
            return
        throttle.active_token = ""
        throttle.active_until = None
        if cooldown_seconds:
            throttle.cooldown_until = timezone.now() + timedelta(seconds=cooldown_seconds)
        throttle.save()
