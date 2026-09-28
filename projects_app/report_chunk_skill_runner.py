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


def run_chunked_skill_lines(upload, file_bytes: bytes, lines: list) -> bytes:
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

    clear_comments = any(bool(line.rule.clear_comments) for line in lines)
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
                _chunk_prompt(skill_name, model_id, task.payload),
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
            response = _expand_response_anchor_ids(response, task.payload)
        except ReportCheckAborted:
            raise
        except Exception as exc:
            if heartbeat(upload) is False:
                raise ReportCheckAborted() from exc
            last_exc = exc
            transient = _is_transient_error(exc)
            if isinstance(exc, ChunkSkillError) and attempt >= 2:
                transient = False
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


def _chunk_prompt(skill_name: str, model_id: str, payload: dict) -> str:
    model_note = (
        f"\nНастроенная для правила модель DSH: {model_id}."
        if str(model_id or "").strip()
        else ""
    )
    compact, _anchor_map = _compact_chunk_payload(payload)
    return (
        f"/{skill_name}\n\n"
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
        parsed = _findings_response(json.loads(value))
    except json.JSONDecodeError:
        parsed = None
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


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    if isinstance(exc, ChunkSkillError) and (
        "findings.json" in text or "массивом findings" in text
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
