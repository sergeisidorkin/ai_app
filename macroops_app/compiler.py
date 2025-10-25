import uuid

ALLOWED = {"paragraph.insert","list.start","list.item","list.end"}

def compile_docops_to_addin_job(docops: dict, anchor: dict | None = None, meta: dict | None = None) -> dict:
    if not isinstance(docops, dict) or docops.get("type") != "DocOps" or docops.get("version") != "v1":
        raise ValueError("invalid DocOps")

    ops_in = docops.get("ops") or []
    ops = []
    for op in ops_in:
        if isinstance(op, dict) and op.get("op") in ALLOWED:
            ops.append(op)

    if not ops:
        raise ValueError("DocOps has no supported ops")

    job = {
        "kind": "addin.job",
        "version": "v1",
        "id": str(uuid.uuid4()),
        "ops": ops,
    }
    if anchor: job["anchor"] = anchor
    if meta:   job["meta"]   = meta
    return job