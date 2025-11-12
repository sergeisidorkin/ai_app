# macroops_app/addin_payload.py
import uuid
from typing import List, Tuple, Dict, Any

def _op_name(op: dict) -> str:
    if not isinstance(op, dict):
        return ""
    return (op.get("op") or op.get("kind") or op.get("type") or "").strip()

def _strip_job_marker_tail(ops: List[Dict]) -> Tuple[List[Dict], int]:
    filtered, removed = [], 0
    for o in ops or []:
        if _op_name(o) == "job.marker.tail":
            removed += 1
            continue
        filtered.append(o)
    return filtered, removed

def _ensure_trailing_block_op(ops: List[Dict], job_id: str | None) -> Tuple[List[Dict], bool, int]:
    if not isinstance(ops, list):
        ops = list(ops or [])
    ops, removed = _strip_job_marker_tail(ops)
    appended = False
    if job_id:
        ops.append({"op": "job.marker.tail", "jobId": str(job_id)})
        appended = True
    return ops, appended, removed

# --- сборка client payload ---

def build_payload_from_blocks(
        blocks: List[Dict],
        *,
        doc_url: str = "",
        job_id: str | None = "",
        trace_id: str | None = "",
) -> Dict[str, Any]:
    blocks, _, _ = _ensure_trailing_block_op(blocks, job_id)
    payload: Dict[str, Any] = {"type": "addin.block", "blocks": blocks, "docUrl": doc_url}
    if job_id:
        payload["jobId"] = str(job_id)
    if trace_id:
        payload["traceId"] = str(trace_id)
    return payload

# --- перенос 3: сборка client payload из addin.job ---

def build_payload_from_job(
        job: Dict[str, Any],
        *,
        job_id: str | None = None,
        trace_id: str | None = "",
        doc_url: str = "",
) -> Dict[str, Any]:
    ops = list((job or {}).get("ops") or [])

    # prepend anchor paragraph (как в consumers.addin_job)
    atext = ""
    try:
        atext = ((job.get("anchor") or {}).get("text") or "").strip()
    except Exception:
        atext = ""
    if atext:
        ops = [{"op": "paragraph.insert", "text": atext}] + ops

    # resolve job_id (как в consumers.addin_job)
    job_meta = (job.get("meta") or {})
    job_id = str(job_id or job_meta.get("job_id") or uuid.uuid4())

    return build_payload_from_blocks(
        ops, doc_url=doc_url, job_id=job_id, trace_id=(trace_id or job_meta.get("trace_id") or "")
    )